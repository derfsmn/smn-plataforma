// Pruebas de lib/numeros.ts (revisión de formularios, 26 nov 2026). Correr: npm test
import { test } from "node:test";
import assert from "node:assert/strict";
import { leerNumero, verNumero, teclearNumero, leerCodigoBarras } from "./numeros.ts";

const v = (t, d = 2) => leerNumero(t, d).valor;

test("dinero estilo México y lo que se pega de Excel", () => {
  assert.equal(v("1,234.50"), "1234.50");
  assert.equal(v("1234,50"), "1234.50");
  assert.equal(v("1.234,50"), "1234.50");
  assert.equal(v("$459"), "459");
  assert.equal(v("$ 1,299.00"), "1299.00");
  assert.equal(v("459."), "459");
  assert.equal(v(".5"), "0.5");
  assert.equal(v(" 459.50 "), "459.50");
  assert.equal(v("1 234.50"), "1234.50");
  assert.equal(v("1,234"), "1234");
  assert.equal(v("1,234,567.8"), "1234567.8");
  assert.equal(v("007"), "7");
  assert.equal(v(""), null);
});

test("nunca cambia el número en silencio", () => {
  assert.notEqual(v("459.50"), "45950");
  assert.ok(leerNumero("1,2,3").error);
  assert.ok(leerNumero("459.505").error);
  assert.ok(leerNumero("abc").error);
  assert.ok(leerNumero("1.5E+3").error);
  assert.equal(v("1.2", 3), "1.2");
  assert.ok(leerNumero("1.5", 0).error);
});

test("porcentajes: 31 y 31 % son lo mismo", () => {
  assert.equal(v("31%"), "31");
  assert.equal(v("31 %"), "31");
});

test("ida y vuelta: lo que se ve se vuelve a leer igual", () => {
  for (const x of ["1234.50", "459", "0.5", "1234567.8", "12"]) assert.equal(v(verNumero(x)), x);
  assert.equal(verNumero("1234.5"), "1,234.5");
});

test("al teclear no se mueve nada más que letras", () => {
  assert.equal(teclearNumero("1,234.5a"), "1,234.5");
  // lo pegado de Excel con «E+» no se vuelve otro número en silencio
  assert.ok(leerNumero(teclearNumero("1.5E+3")).error);
});

test("código de barras conserva los ceros y no acepta notación de Excel", () => {
  assert.equal(leerCodigoBarras(" 0075010312345 ").valor, "0075010312345");
  assert.ok(leerCodigoBarras("7.50103E+12").error);
  assert.ok(leerCodigoBarras("12345").error);
  assert.equal(leerCodigoBarras("750 1031 23456").valor, "7501031234 56".replace(" ", ""));
});

test("un número que llega como número (no texto) también se ve bien", () => {
  assert.equal(verNumero(1250), "1,250");
  assert.equal(verNumero(0), "0");
});
