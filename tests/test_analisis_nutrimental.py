"""Cálculos sobre fichas reales archivadas y respuestas IA ficticias; sin red."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from analisis_nutrimental import validar_interpretacion
from revision_nutrimental import evaluar

DATOS=Path(__file__).parent/'nutricional'


def ficha(sku):
    f=json.loads((DATOS/(sku+'.json')).read_text(encoding='utf8'))
    archivo='77755A.jpg' if sku=='77755' else sku+'.jpg'
    f['fuentes']['foto_1']['ruta']=str((DATOS/archivo).resolve())
    if sku=='55527':f['categoria']='suplemento'
    return f


class Analisis(unittest.TestCase):
    def setUp(self):
        self.r=evaluar(ficha('55527'))
        self.a=self.r['analisis_producto']

    def respuesta_ficticia(self):
        escenario=next(h['id'] for h in self.a['hechos'] if h['tipo']=='escenario')
        estudio=next(h['id'] for h in self.a['hechos'] if h['tipo']=='estudio')
        cita={'texto':'Interpretación ficticia: de 16.67 % a 22.58 % en escenarios no asignados al producto.','hechos':[escenario],'referencias':['NIH_MAGNESIO']}
        evidencia={'texto':'El desenlace ISI del estudio mostró un efecto pequeño; no es una prueba de esta marca.','hechos':[estudio],'referencias':['RCT_MG_BISGLICINATO_2025']}
        return {'conclusion':copy.deepcopy(cita),'fortalezas':[copy.deepcopy(cita)],'limitaciones':[copy.deepcopy(cita)],'lectura_evidencia':[evidencia],'siguiente_decision':copy.deepcopy(cita),'prioridades':['H01']}

    def test_escenarios_no_asignan_poblacion_y_calculos_correctos(self):
        self.assertIsNone(self.r['contexto']['poblacion'])
        escenarios=self.a['escenarios_referencia']
        self.assertEqual(len(escenarios),4)
        self.assertFalse(any(e['seleccionado'] for e in escenarios))
        self.assertEqual([e['porcentaje_referencia'] for e in escenarios],[17.5,22.58,16.67,21.88])
        self.assertTrue(any('14.00 %' in h['texto'] for h in self.a['hechos']))
        self.assertTrue(any('41.67 %' in h['texto'] for h in self.a['hechos']))

    def test_estudio_real_se_contrasta_sin_inferir_eficacia(self):
        e=self.a['estudios_contrastados'][0]
        self.assertEqual(e['estudio']['pmid'],'40918053')
        self.assertEqual(e['proporcion_cantidad_estudiada'],28)
        self.assertFalse(e['mismo_producto'])
        self.assertIsNone(e['finalidad_seleccionada'])
        self.assertTrue(any('no demuestra' in h['texto'] for h in self.a['hechos'] if h['tipo']=='estudio'))

    def test_mezcla_sin_elemental_no_recibe_cantidad_de_estudio(self):
        a=evaluar(ficha('55541'))['analisis_producto']
        self.assertEqual(a['escenarios_referencia'],[])
        self.assertIsNone(a['estudios_contrastados'][0]['proporcion_cantidad_estudiada'])
        self.assertTrue(any('39.22 %' in h['texto'] for h in a['hechos']))

    def test_alimento_analiza_100g_sin_convertirlo_en_porcion(self):
        r=evaluar(ficha('77755'));a=r['analisis_producto']
        self.assertIsNone(r['contexto']['consumo_diario']['porciones'])
        self.assertTrue(any(e['base']=='por 100 g' and e['porcentaje_referencia']==20 for e in a['escenarios_referencia']))
        self.assertEqual(a['estudios_contrastados'],[])
        self.assertTrue(any(h['tipo']=='cobertura' for h in a['hechos']))

    def test_rechaza_comparar_compuestos_con_referencia_elemental(self):
        r=evaluar(ficha('55541'));a=r['analisis_producto']
        respuesta=self.respuesta_ficticia()
        respuesta['conclusion']={'texto':'La mezcla alcanza la RDA.', 'hechos':[a['hechos'][0]['id']], 'referencias':['NIH_MAGNESIO']}
        with self.assertRaisesRegex(ValueError,'elemental'):
            validar_interpretacion(respuesta,a,r['hallazgos'])

    def test_no_aplica_y_fuente_invalida_no_reciben_comparaciones(self):
        f=ficha('55527');f['categoria']='shampoo'
        self.assertEqual(evaluar(f)['analisis_producto']['escenarios_referencia'],[])
        f=ficha('55527');f['fuentes']['foto_1']['sha256']='invalida'
        a=evaluar(f)['analisis_producto']
        self.assertEqual(a['escenarios_referencia'],[])
        self.assertEqual(a['estudios_contrastados'],[])

    def test_forma_y_catalogo_no_depende_de_sku(self):
        f=ficha('55527');f['sku']='OTRO-SKU';f['nombre']='Otra marca'
        self.assertEqual(evaluar(f)['analisis_producto']['estudios_contrastados'][0]['estudio']['pmid'],'40918053')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'catalogo.json';p.write_text('{"estudios":[],"version":"ficticia"}',encoding='utf8')
            a=evaluar(f,evidencia_path=p)['analisis_producto']
            self.assertEqual(a['estudios_contrastados'],[])
            p.write_text('{"estudios":[{}]}',encoding='utf8')
            with self.assertRaises(ValueError):evaluar(f,evidencia_path=p)

    def test_interpretacion_con_citas_no_cambia_hechos(self):
        antes=copy.deepcopy(self.a)
        validar_interpretacion(self.respuesta_ficticia(),self.a,self.r['hallazgos'])
        self.assertEqual(self.a,antes)

    def test_rechaza_citas_inexistentes_y_cifras_inventadas(self):
        for cambios in ({'hechos':['NO_EXISTE']},{'referencias':['FUENTE_FALSA']},{'texto':'Dato ficticio de 987654321 mg.'},{'texto':'Dato ficticio de 8 000 kJ.'},{'texto':'El aporte es 70 % de la referencia.'},{'texto':'La cantidad del estudio es 28 % mayor.'}):
            r=self.respuesta_ficticia();r['conclusion'].update(cambios)
            with self.assertRaises(ValueError):validar_interpretacion(r,self.a,self.r['hallazgos'])

    def test_rechaza_contexto_inventado_conclusiones_y_omision_de_resultado(self):
        for texto in ('La dosis no es terapéutica.','No se encontraron estudios.','No se relaciona con la finalidad.','Aumente el consumo.','El producto es seguro.','Es un producto saludable.','No contiene excipientes.','Puede mejorar la biodisponibilidad.'):
            r=self.respuesta_ficticia();r['conclusion']['texto']=texto
            with self.assertRaises(ValueError):validar_interpretacion(r,self.a,self.r['hallazgos'])
        r=self.respuesta_ficticia();r['lectura_evidencia'][0]['texto']='Solo se describe la cantidad, sin desenlace.'
        with self.assertRaises(ValueError):validar_interpretacion(r,self.a,self.r['hallazgos'])


if __name__=='__main__':unittest.main()
