// Pruebas de lib/alta-fotos.ts (alta con fotos, 26 nov 2026). Correr: npm test
import { test } from "node:test";
import assert from "node:assert/strict";
import { llenarVacios, pendientes } from "./alta-fotos.ts";

test("lo leído solo llena lo vacío; lo escrito por la persona manda", () => {
  const d = { nombre: "", marca: "Mi marca", contenido: "", precio_nuestro: "", costo_estimado: "", lista_margen: "" };
  const { d: y, llenos } = llenarVacios(d, { nombre: "Omega 3", marca: "Vidanat", contenido: "60 cápsulas", inventado: "x" });
  assert.equal(y.nombre, "Omega 3");
  assert.equal(y.marca, "Mi marca");
  assert.equal(y.contenido, "60 cápsulas");
  assert.deepEqual(llenos.sort(), ["contenido", "nombre"]);
  assert.ok(!("inventado" in y));
});

test("te falta capturar: solo lo que no está", () => {
  const d = { nombre: "Omega 3", marca: "Vidanat", contenido: "60 cápsulas", precio_nuestro: "", costo_estimado: "120", lista_margen: "" };
  assert.deepEqual(pendientes(d, true), ["nuestro precio de venta", "tipo de producto", "proveedor (si ya lo sabes)"]);
  assert.deepEqual(pendientes({ ...d, precio_nuestro: "199", lista_margen: "B" }, false), []);
});
