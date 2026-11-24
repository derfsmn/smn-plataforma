import copy
import unittest
from prueba_nutricional import validar_extraccion, validar_ficha, revisar, reconstruir_tablas, normalizar_encabezados, reconstruir_textos

# Respuestas ficticias: estas pruebas NO ejecutan inferencia.
def ficha():
 return dict(nombre=None,categoria=None,ingredientes=[],advertencias=[],pendientes=[],equivalencias=[],datos=[])
def dato(valor=0,unidad='mg',estado='declarado',id='d1',tipo='nutrimento'):
 return dict(id=id,nombre='Ejemplo ficticio',tipo=tipo,valor=valor,unidad=unidad,base='por porción',estado=estado,foto='foto_1',evidencia=f'Ejemplo ficticio {valor} {unidad}')

class Regresion(unittest.TestCase):
 def test_content_vacio_length(self):
  for tokens in (72,2872):
   with self.assertRaisesRegex(ValueError,'vacía o truncada') as e:
    validar_extraccion(dict(message=dict(content='',thinking='NO IMPRIMIR'),done_reason='length',eval_count=tokens,prompt_eval_count=3884))
   self.assertNotIn('NO IMPRIMIR',str(e.exception))
 def test_json_parcial_aunque_parseable(self):
  with self.assertRaises(ValueError): validar_extraccion(dict(message=dict(content='{}'),done_reason='length'))
 def test_cero_y_ausencia(self):
  f=ficha();f['datos']=[dato(),dato(None,None,'no declarado',id='d2')]
  validar_ficha(f,{'foto_1'})
  self.assertEqual(f['datos'][0]['valor'],0);self.assertIsNone(f['datos'][1]['valor'])
 def test_rechaza_valores_unidades_y_fuentes(self):
  for cambios in ({'valor':True},{'valor':float('nan')},{'valor':-1},{'unidad':'mg inventados'},{'foto':'foto_inexistente'},{'base':'por tableta'},{'estado':'ilegible'}):
   with self.subTest(cambios=cambios):
    f=ficha();d=dato();d.update(cambios);f['datos']=[d]
    with self.assertRaises(ValueError):validar_ficha(f,{'foto_1'})
 def test_suma_decimal_y_bases_separadas(self):
  f=ficha();f['datos']=[dict(dato(50,id=f'd{i}',tipo='compuesto'),nombre=f'Compuesto ficticio {i}') for i in range(8)]
  f['datos'].append(dict(dato(4902,id='otro',tipo='compuesto'),base='por 100 g'))
  r=revisar(validar_ficha(f,{'foto_1'}),'suplemento')
  self.assertEqual([x['resultado'] for x in r if x['regla']=='suma_compuestos'],['400','4902'])
 def test_no_infiere_elemental(self):
  f=ficha();f['datos']=[dict(dato(50,tipo='compuesto'),nombre='Citrato de magnesio')]
  revisar(f,'suplemento');self.assertTrue(any('Magnesio elemental' in p for p in f['pendientes']))
  self.assertEqual(len(f['datos']),1)
 def test_shampoo_y_categoria_pendiente(self):
  self.assertEqual(revisar(ficha(),'shampoo')[1]['resultado'],'no aplica')
  self.assertEqual(revisar(ficha(),None)[1]['resultado'],'pendiente')
 def test_equivalencia_conserva_dos_masas(self):
  f=ficha();f['datos']=[dict(dato(500,tipo='compuesto'),nombre='Compuesto ficticio'),dict(dato(70,id='d2'),nombre='Nutrimento ficticio')]
  f['equivalencias']=[dict(compuesto_id='d1',nutrimento_id='d2',foto='foto_1',evidencia='Equivalente a Magnesio 70 mg')]
  validar_ficha(f,{'foto_1'});self.assertEqual([d['valor'] for d in f['datos']],[500,70])
  f['equivalencias'][0]['nutrimento_id']='no_existe'
  with self.assertRaises(ValueError):validar_ficha(f,{'foto_1'})
 def test_no_suma_columnas_con_base_duplicada(self):
  f=ficha();f['datos']=[dato(500,tipo='compuesto'),dato(41667,id='d2',tipo='compuesto')]
  with self.assertRaisesRegex(ValueError,'revisar columnas'):validar_ficha(f,{'foto_1'})
 def test_escala_masa_porcion_y_revisa_discrepancia(self):
  f=ficha();f['datos']=[dict(dato(1200,id='p',tipo='porcion'),nombre='Masa ficticia de porción'),dato(500,id='c',tipo='compuesto'),dict(dato(41667,id='c100',tipo='compuesto'),base='por 100 g')]
  validar_ficha(f,{'foto_1'})
  self.assertEqual([r['resultado'] for r in revisar(f,'suplemento') if r['regla']=='coherencia_porcion_100g'],['correcto'])
  f['datos'][2]['valor']=400
  self.assertEqual([r['resultado'] for r in revisar(f,'suplemento') if r['regla']=='coherencia_porcion_100g'],['revisar'])
 def test_unidad_debe_aparecer_en_evidencia(self):
  f=ficha();f['datos']=[dict(dato(70,'g'),evidencia='Ejemplo ficticio 70 mg')]
  with self.assertRaisesRegex(ValueError,'no contiene la unidad'):validar_ficha(f,{'foto_1'})
 def test_tabla_generica_desde_ocr_ficticio(self):
  f=ficha();f['datos']=[dict(dato(20,tipo='compuesto'),nombre='Compuesto ficticio')]
  lecturas=[dict(foto='foto_1',transcripcion='Tamaño de porción\n3 tabletas (1500 mg)\nPorciones por envase\n20\nPorción\n100 g\nCompuesto ficticio\n20 mg\n1333.3 mg\nProteínas\n0 g\n0 g\nINGREDIENTES: ejemplo ficticio')]
  f=validar_ficha(normalizar_encabezados(reconstruir_tablas(f,lecturas)),{'foto_1'})
  self.assertEqual([d['valor'] for d in f['datos'] if d['tipo']=='porcion'],[3,1500])
  self.assertEqual([(d['valor'],d['base']) for d in f['datos'] if d['tipo']=='compuesto'],[(20,'por porción'),(1333.3,'por 100 g')])
  self.assertEqual(len([d for d in f['datos'] if d['nombre']=='Proteínas' and d['valor']==0]),2)
 def test_tabla_incompleta_no_reconstruye_valores(self):
  f=ficha();lecturas=[dict(foto='foto_1',transcripcion='Porción\n100 g\nProteínas\n10 g')]
  self.assertEqual(reconstruir_tablas(f,lecturas)['datos'],[])
 def test_tabla_simple_otro_producto_y_miles_con_espacio(self):
  f=ficha();l=[dict(foto='foto_1',transcripcion='Declaración nutrimental\nContenido energético Por 100 g\n123,4 kcal / 1 234,5 kJ\nProteínas 7,8 g\nSodio 90 mg\nContenido energético Por envase\n246,8 kcal / 2 469,0 kJ\nIngredientes: ejemplo ficticio')]
  f=validar_ficha(normalizar_encabezados(reconstruir_tablas(f,l)),{'foto_1'})
  self.assertEqual([(d['valor'],d['base']) for d in f['datos'] if d['unidad']=='kJ'],[(1234.5,'por 100 g'),(2469,'por envase')])
 def test_secciones_no_confunden_toda_la_foto_con_ingredientes(self):
  f=ficha();f['ingredientes']=[dict(texto='Nombre ficticio y toda la etiqueta',foto='foto_1')]
  l=[dict(foto='foto_1',transcripcion='Nombre ficticio\nIngredientes: harina ficticia, agua.\nMODO DE EMPLEO: ejemplo. No exceder la porción indicada.')]
  f=reconstruir_textos(f,l)
  self.assertEqual(f['ingredientes'],[dict(texto='Ingredientes: harina ficticia, agua.',foto='foto_1')])
  self.assertEqual(f['advertencias'][0]['texto'],'No exceder la porción indicada.')
 def test_dos_fotos_conservan_fuentes_separadas(self):
  l=[dict(foto=foto,transcripcion=f'Porción\n100 g\nProteínas\n{valor} g\n{valor*10} g') for foto,valor in [('foto_1',1),('foto_2',2)]]
  f=validar_ficha(normalizar_encabezados(reconstruir_tablas(ficha(),l)),{'foto_1','foto_2'})
  self.assertEqual([d['valor'] for d in f['datos'] if d['foto']=='foto_1'],[1,10])
  self.assertEqual([d['valor'] for d in f['datos'] if d['foto']=='foto_2'],[2,20])

if __name__=='__main__':unittest.main()
