// Prueft preise.js: Preise ab jetzt und je Tag. Spec C8 Abschnitte 6.6 und 6.7.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { preisSlots, tageswerte } from '../../custom_components/meteo_volt/frontend/preise.js';

const TZ = 'Europe/Berlin';
const MIN = 60000;
// Mi 16.09.2026 22:00 in Berlin
const START = Date.UTC(2026, 8, 16, 20, 0);
const iso = (ms) => new Date(ms).toISOString();

// 16 Slots bis Mitternacht Boerse, danach 8 Prognose.
function preise(q50 = (i) => 0.2 - i / 100) {
  return {
    slots: Array.from({ length: 24 }, (_, i) => {
      const boerse = i < 8;
      return { t: iso(START + i * 15 * MIN), q50: q50(i), q10: boerse ? q50(i) : q50(i) - 0.02, q90: boerse ? q50(i) : q50(i) + 0.04, source: boerse ? 'epex' : 'forecast' };
    }),
    prices_known_until: iso(START + 7 * 15 * MIN),
  };
}

test('Slots ab dem laufenden, q10 und q90 fehlen: q50', () => {
  const s = preisSlots(preise(), START + 20 * MIN);
  assert.equal(s.length, 23);
  assert.equal(s[0].t, START + 15 * MIN);
  assert.equal(s[0].ende, START + 30 * MIN);
  assert.equal(s[0].boerse, true);
  const ohne = preisSlots({ slots: [{ t: iso(START), q50: 0.1, source: 'forecast' }] }, START);
  assert.deepEqual([ohne[0].q10, ohne[0].q90, ohne[0].boerse], [0.1, 0.1, false]);
  assert.deepEqual(preisSlots(null, START), []);
});

test('je Tag: Quelle, Tief, Hoch, Mittel, Spanne', () => {
  const tage = tageswerte(preisSlots(preise(), START), 1, TZ, 0);
  assert.deepEqual(tage.map((t) => t.datum), ['2026-09-16', '2026-09-17']);
  const [heute, morgen] = tage;
  assert.equal(heute.quelle, 'boerse');
  assert.equal(heute.spanne, null);
  assert.equal(heute.von, START);
  assert.equal(heute.bis, START + 8 * 15 * MIN);
  assert.equal(heute.hoch.t, START);
  assert.equal(heute.tief.t, START + 7 * 15 * MIN);
  assert.ok(Math.abs(heute.mittel - (0.2 - 3.5 / 100)) < 1e-9);
  assert.equal(morgen.quelle, 'prognose');
  assert.ok(Math.abs(morgen.spanne - 0.03) < 1e-9);
});

test('der guenstigste Zeitraum liegt ganz im Tag, bei Gleichstand der frueheste', () => {
  const [heute, morgen] = tageswerte(preisSlots(preise(), START), 1, TZ, 0);
  assert.equal(heute.fenster.von, START + 4 * 15 * MIN);
  assert.equal(heute.fenster.bis, START + 8 * 15 * MIN);
  assert.equal(morgen.fenster.von, START + 20 * 15 * MIN);
  const flach = tageswerte(preisSlots(preise(() => 0.1), START), 1, TZ, 0);
  assert.equal(flach[0].fenster.von, START);
  assert.equal(flach[0].tief.t, START);
});

test('ein Tag mit weniger Slots als der Zeitraum ist zu kurz', () => {
  // heute 8 Slots, morgen 16: 3 h passen nur morgen, als die letzten 12 Slots
  const tage = tageswerte(preisSlots(preise(), START), 3, TZ, 0);
  assert.equal(tage[0].fenster, null);
  assert.equal(tage[1].fenster.von, START + 12 * 15 * MIN);
  assert.equal(tage[1].fenster.bis, START + 24 * 15 * MIN);
});

test('ein Zeitraum ueberspringt keine Luecke in den Slots', () => {
  // Der guenstigste Slot ist der letzte vor der Luecke; ein Fenster darf sie nicht ueberbruecken.
  const roh = preise();
  roh.slots = roh.slots.filter((_, i) => i !== 5).slice(0, 8);
  // Ohne die Luecke laege das guenstigste Fenster ueber ihr, bei START + 3 Slots.
  const [heute] = tageswerte(preisSlots(roh, START), 1, TZ, 0);
  assert.equal(heute.fenster.von, START + 15 * MIN);
  assert.equal(heute.fenster.bis, START + 5 * 15 * MIN);
  assert.equal(heute.tief.t, START + 7 * 15 * MIN);
});

test('mit Netzentgelt kommt es auf jeden Preis, die Spanne bleibt', () => {
  const ohne = tageswerte(preisSlots(preise(), START), 1, TZ, 0);
  const mit = tageswerte(preisSlots(preise(), START), 1, TZ, 0.16);
  assert.ok(Math.abs(mit[0].mittel - ohne[0].mittel - 0.16) < 1e-9);
  assert.ok(Math.abs(mit[0].fenster.mittel - ohne[0].fenster.mittel - 0.16) < 1e-9);
  assert.equal(mit[1].spanne, ohne[1].spanne);
});
