"""Datos ficticios y respuestas simuladas: no se llama a Ollama ni a internet."""
import copy
import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
from pathlib import Path

from revision_nutrimental import evaluar, consumo_diario, priorizar_con_ollama


class Revision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        ruta = Path(self.tmp.name) / 'fuente_ficticia.txt'
        ruta.write_bytes(b'Fuente ficticia para pruebas de integridad, no una etiqueta real')
        def dato(id, nombre, tipo, valor, unidad):
            return {'id':id,'nombre':nombre,'tipo':tipo,'valor':valor,'unidad':unidad,'base':'por porción','estado':'declarado','foto':'foto_1','evidencia':f'{nombre} {valor} {unidad}'}
        self.f = {'datos_ficticios':True, 'nombre':'Producto ficticio', 'categoria':'suplemento', 'ingredientes':[{'texto':'Compuesto de magnesio ficticio','foto':'foto_1'}], 'advertencias':[], 'pendientes':[], 'equivalencias':[], 'fuentes':{'foto_1':{'ruta':str(ruta),'sha256':hashlib.sha256(ruta.read_bytes()).hexdigest()}}, 'lecturas':[{'foto':'foto_1','transcripcion':'Tamaño de porción: 2 tabletas. MODO DE EMPLEO: Tomar 4 tabletas al día.'}], 'datos':[dato('p','Tamaño de porción','porcion',2,'tabletas'),dato('masa','Masa de porción','porcion',1500,'mg'),dato('comp','Compuesto ficticio de magnesio','compuesto',600,'mg'),dato('elem','Equivalente a Magnesio','nutrimento',80,'mg')]}

    def test_pendientes_no_inventa_poblacion_finalidad_o_adecuacion(self):
        r = evaluar(self.f)
        self.assertIsNone(r['contexto']['finalidad'])
        self.assertIsNone(r['contexto']['poblacion'])
        self.assertEqual(r['estado_general'],'informacion_insuficiente')
        self.assertFalse(any('RDA:' in h['motivo'] for h in r['hallazgos']))
        self.assertTrue(r['preguntas_proveedor'])

    def test_consumo_etiqueta_y_aritmetica_sin_confundir_compuesto(self):
        r = evaluar(self.f)
        self.assertEqual(r['contexto']['consumo_diario']['porciones'],2)
        self.assertEqual([a['valor_diario'] for a in r['aportes'] if a['tipo']=='nutrimento'],[160])
        self.assertEqual([a['valor_diario'] for a in r['aportes'] if a['tipo']=='compuesto'],[1200])
        self.assertEqual(self.f['datos'][-1]['valor'],80)

    def test_no_suposicion_de_una_porcion_diaria(self):
        self.f['lecturas']=[]
        self.assertIsNone(consumo_diario(self.f)['porciones'])
        self.assertTrue(all(a['valor_diario'] is None for a in evaluar(self.f)['aportes']))

    def test_dos_instrucciones_distintas_quedan_pendientes(self):
        self.f['lecturas'].append({'foto':'foto_1','transcripcion':'Tomar 6 tabletas al día'})
        self.assertIsNone(consumo_diario(self.f)['porciones'])

    def test_escenario_usuario_no_se_presenta_como_etiqueta(self):
        r = evaluar(self.f,porciones_dia=3)
        self.assertEqual(r['contexto']['consumo_diario']['origen'],'escenario_usuario')
        self.assertEqual(r['aportes'][-1]['valor_diario'],240)
        for v in (0,-1,True,float('nan'),float('inf')):
            with self.assertRaises(ValueError):evaluar(self.f,porciones_dia=v)

    def test_sin_elemental_no_calcula_desde_masas(self):
        self.f['datos'].pop()
        r = evaluar(self.f,perfil='hombres_19_30')
        self.assertFalse(any(a['tipo']=='nutrimento' for a in r['aportes']))
        self.assertTrue(any('elemental' in h['criterio'] and h['resultado']=='informacion_insuficiente' for h in r['hallazgos']))
        self.assertFalse(any('RDA:' in h['motivo'] for h in r['hallazgos']))

    def test_cero_declarado_no_equivale_a_ausente(self):
        self.f['datos'][-1]['valor']=0
        self.f['datos'][-1]['evidencia']='Equivalente a Magnesio 0 mg'
        r = evaluar(self.f)
        self.assertEqual(r['aportes'][-1]['valor_diario'],0)
        self.assertFalse(any(h['criterio']=='Magnesio elemental declarado por porción' for h in r['hallazgos']))

    def test_perfil_explicito_compara_sin_recomendar_dosis(self):
        r = evaluar(self.f,perfil='hombres_19_30',finalidad='Finalidad ficticia de prueba')
        h = next(h for h in r['hallazgos'] if 'RDA:' in h['motivo'])
        self.assertIn('40.00 %',h['motivo'])
        self.assertEqual(h['resultado'],'observacion')
        self.assertIn('no aumentar dosis',h['accion_recomendada'])
        self.assertEqual(h['referencias'],['NIH_MAGNESIO'])
        with self.assertRaises(ValueError):evaluar(self.f,perfil='hombres_19_30',poblacion='Niños ficticios')

    def test_conversion_masa_no_conversion_quimica(self):
        self.f['datos'][-1].update(valor=0.08,unidad='g',evidencia='Equivalente a Magnesio 0.08 g')
        r = evaluar(self.f,perfil='hombres_19_30')
        self.assertTrue(any('40.00 %' in h['motivo'] for h in r['hallazgos']))

    def test_comparacion_superior_nunca_dice_seguro_o_aprobado(self):
        self.f['datos'][-1].update(valor=200,evidencia='Equivalente a Magnesio 200 mg')
        r=evaluar(self.f,perfil='hombres_19_30')
        h=next(h for h in r['hallazgos'] if h['criterio'].startswith('Referencia superior'))
        self.assertEqual(h['resultado'],'revision_profesional')
        self.assertIn('rebasa',h['motivo'])
        self.assertIn('seguridad individual',h['motivo'])

    def test_fotos_duplicadas_no_duplican_aporte_y_conflictos_no_se_promedian(self):
        self.f['fuentes']['foto_2']=copy.deepcopy(self.f['fuentes']['foto_1'])
        nuevos=[{**d,'id':d['id']+'_2','foto':'foto_2'} for d in self.f['datos']]
        self.f['datos'].extend(nuevos)
        r=evaluar(self.f)
        self.assertEqual(len(r['aportes']),2)
        self.assertEqual(r['aportes'][-1]['valor_diario'],160)
        self.f['datos'][-1]['valor']=90
        r=evaluar(self.f,perfil='hombres_19_30')
        self.assertFalse(any('RDA:' in h['motivo'] for h in r['hallazgos']))
        self.assertTrue(any('contradictorios' in h['motivo'] for h in r['hallazgos']))

    def test_shampoo_no_aplica(self):
        self.f['categoria']='shampoo'
        r=evaluar(self.f)
        self.assertEqual(r['estado_general'],'no_aplica')
        self.assertEqual(r['aportes'],[])
        self.assertEqual(r['preguntas_proveedor'],[])

    def test_alimento_100g_no_se_presenta_como_porcion(self):
        self.f.update(categoria='alimento',ingredientes=[],lecturas=[])
        self.f['datos']=[{**self.f['datos'][-1],'nombre':'Sodio','valor':400,'base':'por 100 g'}]
        r=evaluar(self.f,perfil='hombres_19_30')
        self.assertIsNone(r['aportes'][0]['valor_diario'])
        self.assertFalse(any('valor diario FDA' in h['motivo'] for h in r['hallazgos']))
        self.assertFalse(any(ref['id'].startswith('COFEPRIS') for ref in r['referencias']))

    def test_foto_modificada_y_estudios_no_aportados(self):
        Path(self.f['fuentes']['foto_1']['ruta']).write_text('Cambio ficticio')
        r=evaluar(self.f)
        self.assertEqual(r['integridad_fuentes'][0]['estado'],'no_coincide')
        self.assertEqual(next(h for h in r['hallazgos'] if h['bloque']=='sustento_cientifico')['resultado'],'informacion_insuficiente')

    def test_proteina_no_recibe_porcentaje_de_etiquetado_sin_evaluacion(self):
        self.f['categoria']='alimento'
        self.f['datos'][-1].update(nombre='Proteínas',valor=10,unidad='g')
        r=evaluar(self.f,perfil='hombres_19_30')
        h=next(h for h in r['hallazgos'] if h['criterio']=='Evaluación de proteína')
        self.assertEqual(h['resultado'],'informacion_insuficiente')
        self.assertFalse(any('valor diario FDA por porción' in h['motivo'] for h in r['hallazgos']))

    def test_ia_solo_prioriza_sin_eliminar_hallazgos(self):
        r=evaluar(self.f);antes=copy.deepcopy(r['hallazgos'])
        priorizar_con_ollama(r,'modelo_ficticio',lambda req:{'message':{'content':json.dumps({'prioridades':['H01','H02']})},'done_reason':'stop'})
        self.assertEqual(r['ia']['estado'],'correcto')
        self.assertEqual(r['hallazgos'],antes)

    def test_ia_fallida_o_inyeccion_no_inventa_criterios(self):
        respuestas=[{'prioridades':['NO_EXISTE']},{'prioridades':['H01','H01']},{'prioridades':['H01'],'dictamen':'seguro'},[]]
        for salida in respuestas:
            r=evaluar(self.f);antes=copy.deepcopy(r['hallazgos'])
            priorizar_con_ollama(r,'modelo_ficticio',lambda req:{'message':{'content':json.dumps(salida)},'done_reason':'stop'})
            self.assertEqual(r['ia']['estado'],'no_disponible')
            self.assertEqual(r['hallazgos'],antes)
        r=evaluar(self.f)
        priorizar_con_ollama(r,'modelo_ficticio',lambda req:{'message':{'content':'','thinking':'SECRETO_FICTICIO'},'done_reason':'length','eval_count':1024})
        self.assertEqual(r['ia']['estado'],'no_disponible')
        self.assertNotIn('SECRETO_FICTICIO',str(r['ia']))

    def test_cli_reutiliza_ficha_sin_repetir_ocr(self):
        from prueba_nutricional import main
        entrada=Path(self.tmp.name)/'ficha_ficticia.json'
        salida=Path(self.tmp.name)/'revision_ficticia.json'
        entrada.write_text(json.dumps(self.f),encoding='utf8')
        argv=['prueba_nutricional.py','--ficha',str(entrada),'--salida',str(salida),'--sin-ia-revision']
        with patch('sys.argv',argv),patch('prueba_nutricional.consultar_ollama') as ollama,redirect_stdout(StringIO()):
            self.assertEqual(main(),0)
        ollama.assert_not_called()
        resultado=json.loads(salida.read_text(encoding='utf8'))
        self.assertEqual(resultado['revision_nutrimental']['estado_general'],'informacion_insuficiente')
        self.assertIsNone(resultado['revision_nutrimental']['contexto']['poblacion'])
        self.assertEqual(json.loads(entrada.read_text(encoding='utf8')),self.f)

    def test_cli_imagen_agrega_revision_sin_cambiar_extraccion(self):
        from prueba_nutricional import main
        salida=Path(self.tmp.name)/'revision_ficticia.json'
        f=copy.deepcopy(self.f);f['sku']='FICTICIO'
        argv=['prueba_nutricional.py','--imagen','foto_ficticia.jpg','--evaluar','--sin-ia-revision','--salida',str(salida)]
        with patch('sys.argv',argv),patch('prueba_nutricional.extraer_imagenes',return_value=f),patch('prueba_nutricional.mostrar_resumen'),redirect_stdout(StringIO()):
            self.assertEqual(main(),0)
        self.assertEqual(json.loads(salida.read_text(encoding='utf8'))['datos'],self.f['datos'])


if __name__=='__main__':unittest.main()
