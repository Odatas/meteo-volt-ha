// Prueft die Hinweiszeile unter dem Haken. Spec C10 Abschnitt 5.
// Die uebrigen drei Funktionen haelt die Gegenprobe in tests/test_panel.py
// gegen ladereserve.py; hier steht nur, was keinen Zwilling hat.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { hinweis } from '../../custom_components/meteo_volt/frontend/ladereserve.js';

const AUTO = { soc_min_pct: 15, capacity_kwh: 58, consumption_kwh_per_100km: 19.5 };

test('die Hinweiszeile nennt Ziel, Min-SoC, Fahrt und Strecke', () => {
  assert.deepEqual(hinweis(175, AUTO), { ziel: 74, min: 15, fahrt: 59, km: 175 });
});

test('ohne Strecke gibt es keine Hinweiszeile', () => {
  assert.equal(hinweis(null, AUTO), null);
  assert.equal(hinweis(Number.NaN, AUTO), null);
  assert.equal(hinweis(-1, AUTO), null);
});

test('bei null Kilometern sichert der Haken den Min-SoC', () => {
  assert.deepEqual(hinweis(0, AUTO), { ziel: 15, min: 15, fahrt: 0, km: 0 });
});

test('das Ziel kann ueber der Summe der angezeigten Teile liegen', () => {
  // 15,5 + 58,836 sind 74,336 -- aufgerundet 75, angezeigt als 15,5 plus 59
  const h = hinweis(175, { ...AUTO, soc_min_pct: 15.5 });
  assert.equal(h.ziel, 75);
  assert.equal(h.min + h.fahrt, 74.5);
});
