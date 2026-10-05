// Prueft plan.js: was das Panel aus Plan und Terminen ableitet. Spec C8 Abschnitte 6.2 bis 6.4.
//
// Der Plan ist erzeugt: 96 Slots ab Mi 16.09.2026 14:30 in Berlin, soc_end_pct im
// Slot i ist 40 + i / 4, geladen wird in den Slots 30 bis 37 (22:00 bis 24:00).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  blockGrund, blockZiel, bloeckeAbJetzt, erhaltenUm, hatWarnung, laeuft, planAbJetzt, planende, planzeile, status, summen,
  termineAus, zerlegen,
} from '../../custom_components/meteo_volt/frontend/plan.js';

const MIN = 60000;
const START = Date.UTC(2026, 8, 16, 12, 30);
const iso = (ms) => new Date(ms).toISOString();

function plan(felder = {}) {
  const slots = Array.from({ length: 96 }, (_, i) => {
    const laden = i >= 30 && i < 38;
    return {
      t: iso(START + i * 15 * MIN), charge: laden, price: 0.1 + i / 1000, source: i < 38 ? 'epex' : 'forecast',
      soc_end_pct: 40 + i / 4, ...(laden ? { kw: 11, kwh: 2.75, cost_eur: 0.275, reason: 'e2/2026-09-19/ziel' } : {}),
    };
  });
  return {
    slots,
    intervals: [
      { from: iso(START + 2 * 15 * MIN), to: iso(START + 4 * 15 * MIN), kwh: 5, cost_eur: 0.5, avg_price_eur_kwh: 0.1, soc_from_pct: 40, soc_to_pct: 45, reason: 'base' },
      { from: iso(START + 30 * 15 * MIN), to: iso(START + 38 * 15 * MIN), kwh: 22, cost_eur: 2.2, avg_price_eur_kwh: 0.1, soc_from_pct: 47, soc_to_pct: 49, reason: 'e2/2026-09-19/ziel' },
    ],
    horizon_end: iso(START + 96 * 15 * MIN),
    computed_at: iso(START + 2 * MIN),
    charge_now: false,
    charge_now_kw: 0,
    next_charge_start: iso(START + 30 * 15 * MIN),
    ...felder,
  };
}

const termin = (felder = {}) => ({
  entry: 'e2', date: '2026-09-19', vehicle: 'dev-buzz', departure: '2026-09-19T10:00:00+02:00',
  return: '2026-09-20T20:00:00+02:00', distance_km: 320, driver: null, soc: 100, repeat: 'once', changed: false,
  plan: null, hints: [], ...felder,
});

test('IDs zerlegen', () => {
  assert.deepEqual(zerlegen('e2/2026-09-19/ziel'), { eintrag: 'e2', datum: '2026-09-19', art: 'ziel' });
  assert.deepEqual(zerlegen('abc123/2026-09-19/weg'), { eintrag: 'abc123', datum: '2026-09-19', art: 'weg' });
  for (const kein of ['base', null, 'e2/2026-9-19/ziel', 'e2/2026-09-19/fahrt', '/2026-09-19/ziel', 'a/b/c/d']) {
    assert.equal(zerlegen(kein), null, String(kein));
  }
});

test('der Plan beginnt mit dem laufenden Slot', () => {
  const jetzt = START + 5 * 15 * MIN + 7 * MIN;
  const p = planAbJetzt(plan(), jetzt, 62);
  assert.equal(p.start, START + 5 * 15 * MIN);
  assert.equal(p.slots.length, 91);
  assert.equal(p.ende, START + 96 * 15 * MIN);
  assert.equal(p.socStart, 41);
  assert.equal(p.slots[0].ende, START + 6 * 15 * MIN);
  assert.equal(p.slots[90].ende, p.ende);
});

test('im ersten Slot beginnt die Kurve mit dem Ladestand jetzt', () => {
  assert.equal(planAbJetzt(plan(), START + 3 * MIN, 62).socStart, 62);
  assert.equal(planAbJetzt(plan(), START + 3 * MIN, null).socStart, 40);
});

test('ohne Plan oder nach seinem Ende gibt es keinen', () => {
  assert.equal(planAbJetzt(null, START, 50), null);
  assert.equal(planAbJetzt({ slots: [], horizon_end: null }, START, 50), null);
  assert.equal(planAbJetzt(plan(), START + 96 * 15 * MIN, 50), null);
});

test('Ladebloecke: vorbei fehlt, laufend zaehlt ganz, dazu die Summen', () => {
  assert.equal(bloeckeAbJetzt(plan(), START).length, 2);
  const laufend = bloeckeAbJetzt(plan(), START + 3 * 15 * MIN);
  assert.equal(laufend.length, 2);
  const spaeter = bloeckeAbJetzt(plan(), START + 4 * 15 * MIN);
  assert.equal(spaeter.length, 1);
  assert.deepEqual(summen(spaeter, 0), { kwh: 22, kosten: 2.2 });
  const mit = summen(spaeter, 0.16);
  assert.equal(mit.kwh, 22);
  assert.ok(Math.abs(mit.kosten - (2.2 + 22 * 0.16)) < 1e-9);
});

// Drei lueckenlose Intervalle mit wechselndem reason, dahinter eine Luecke und ein viertes.
function zerteilt() {
  const iv = (von, bis, kwh, preis, socVon, socBis, reason) => ({
    from: iso(START + von * 15 * MIN), to: iso(START + bis * 15 * MIN), kwh, cost_eur: kwh * preis,
    avg_price_eur_kwh: preis, soc_from_pct: socVon, soc_to_pct: socBis, reason,
  });
  return plan({
    intervals: [
      iv(2, 3, 2, 0.3, 40, 43, 'e3/2026-09-18/ziel'),
      iv(3, 4, 3, 0.2, 43, 47, 'base'),
      iv(4, 6, 5, 0.1, 47, 53, 'e2/2026-09-19/ziel'),
      iv(8, 9, 2, 0.2, 53, 56, 'base'),
    ],
  });
}

test('Ladebloecke: lueckenlose Intervalle sind ein Block', () => {
  const [eins, zwei, ...rest] = bloeckeAbJetzt(zerteilt(), START);
  assert.equal(rest.length, 0);
  assert.equal(eins.von, START + 2 * 15 * MIN);
  assert.equal(eins.bis, START + 6 * 15 * MIN);
  assert.equal(eins.kwh, 10);
  assert.ok(Math.abs(eins.kosten - 1.7) < 1e-9);
  assert.ok(Math.abs(eins.preis - 0.17) < 1e-9);
  assert.equal(eins.socVon, 40);
  assert.equal(eins.socBis, 53);
  assert.deepEqual(eins.reasons, ['e3/2026-09-18/ziel', 'base', 'e2/2026-09-19/ziel']);
  assert.equal(zwei.von, START + 8 * 15 * MIN);
  // Laeuft der letzte Teil noch, zaehlt der ganze Block.
  assert.equal(bloeckeAbJetzt(zerteilt(), START + 5 * 15 * MIN)[0].von, START + 2 * 15 * MIN);
});

test('der Grund eines Blocks: der frueheste geladene Ziel-Termin, sonst keiner', () => {
  const e2 = termin();
  const e3 = termin({ entry: 'e3', date: '2026-09-18', soc: null, departure: '2026-09-18T07:30:00+02:00', return: '2026-09-18T17:30:00+02:00' });
  const [block, basis] = bloeckeAbJetzt(zerteilt(), START);
  assert.equal(blockGrund(block, termineAus([e2, e3])).entry, 'e3');
  // Ist der frueheste nicht geladen, nennt er den naechsten.
  assert.equal(blockGrund(block, termineAus([e2])).entry, 'e2');
  assert.equal(blockGrund(block, []), null);
  // base ist kein Grund, auch vor einer Abfahrt nicht.
  assert.equal(blockGrund(basis, termineAus([e2, e3])), null);
  // Nur die Art ziel nennt einen Termin.
  assert.equal(blockGrund({ ...basis, reasons: ['e2/2026-09-19/weg'] }, termineAus([e2, e3])), null);
});

test('das Ziel eines Blocks: nur das eigene, wenn es genau das geplante ist', () => {
  // 320 km bei 20 kWh/100 km und 80 kWh sind 80 %, gesichert also 10 + 80 = 90 %.
  const v = { soc_min_pct: 10, capacity_kwh: 80, consumption_kwh_per_100km: 20 };
  assert.equal(blockZiel(termin({ soc: 100 }), v), 100);
  assert.equal(blockZiel(termin({ soc: null }), v), null);
  assert.equal(blockZiel(termin({ soc: 5 }), v), null);
  assert.equal(blockZiel(termin({ soc: 10 }), v), 10);
  // Der Haken hebt 60 auf 90: geplant sind 90, nicht 60.
  assert.equal(blockZiel(termin({ soc: 60, keep_min_soc: true }), v), null);
  assert.equal(blockZiel(termin({ soc: 90, keep_min_soc: true }), v), 90);
  assert.equal(blockZiel(termin({ soc: 60, keep_min_soc: false }), v), 60);
});

test('die Planzeile eines Termins', () => {
  assert.equal(planzeile(termin()), null);
  assert.deepEqual(planzeile(termin({ plan: { running_until: '2026-09-16T17:30:00+02:00', soc_at_departure: null } })),
    { art: 'unterwegs', bis: Date.UTC(2026, 8, 16, 15, 30) });
  assert.deepEqual(planzeile(termin({ plan: { soc_at_departure: 80, soc_after_trip: 50, target_missing_kwh: null, below_min: false, running_until: null } })),
    { art: 'abfahrt', soc: 80 });
  assert.deepEqual(planzeile(termin({ plan: { soc_at_departure: 86, soc_after_trip: 13, target_missing_kwh: 13.4, below_min: true, running_until: null } })),
    { art: 'warnungen', warnungen: [{ art: 'ziel', soc: 100, kwh: 13.4 }, { art: 'min', soc: 13 }] });
  assert.equal(planzeile(termin({ plan: { soc_at_departure: null, soc_after_trip: null, target_missing_kwh: null, below_min: false, running_until: null } })), null);
});

test('Warnungen und Status eines Fahrzeugs', () => {
  const jetzt = START + 7 * MIN;
  const warn = termin({ plan: { soc_at_departure: 86, soc_after_trip: 50, target_missing_kwh: 3, below_min: false, running_until: null } });
  const unterwegs = termin({ entry: 'e3', departure: '2026-09-16T12:00:00+02:00', return: '2026-09-16T17:30:00+02:00' });
  assert.equal(hatWarnung(warn), true);
  assert.equal(hatWarnung(termin()), false);
  const termine = termineAus([warn, unterwegs]);
  assert.equal(laeuft(termine[0], jetzt), true);
  const s = status(plan(), termine, jetzt, true);
  assert.equal(s.unterwegsBis, Date.UTC(2026, 8, 16, 15, 30));
  assert.deepEqual(s.laden, { art: 'ab', t: START + 30 * 15 * MIN });
  assert.equal(s.warnungen, 1);
  assert.deepEqual(status(plan({ charge_now: true, charge_now_kw: 11 }), [], jetzt, true).laden, { art: 'jetzt', kw: 11 });
  assert.deepEqual(status(plan({ next_charge_start: null }), [], jetzt, true).laden, { art: 'keins' });
  assert.deepEqual(status(plan(), [], jetzt, false).laden, { art: 'keinPlan' });
});

test('C9R: ein ignorierter Termin zaehlt im Status nicht als unterwegs', () => {
  const jetzt = START + 7 * MIN;
  const unterwegs = termin({ entry: 'e3', departure: '2026-09-16T12:00:00+02:00', return: '2026-09-16T17:30:00+02:00', ignored: true });
  assert.equal(status(plan(), termineAus([unterwegs]), jetzt, true).unterwegsBis, null);
});

test('"Plan von" kommt aus received_at, nicht aus computed_at', () => {
  // computed_at ist der Zeitpunkt der Prognose (Basiskontrakt) und bliebe nach
  // einem Neu planen stehen. Erwartet wird der Zeitpunkt der Antwort.
  const p = plan({ received_at: iso(START + 5 * MIN), computed_at: iso(START - 60 * MIN) });
  assert.equal(erhaltenUm([null, p]), START + 5 * MIN);
  assert.equal(erhaltenUm([plan({ received_at: null })]), null);
  assert.equal(erhaltenUm([]), null);
});

test('das Planende und die Reihenfolge der Termine', () => {
  assert.equal(planende([null, plan()], START), START + 96 * 15 * MIN);
  assert.equal(planende([plan()], START + 96 * 15 * MIN), null);
  const t = termineAus([termin({ departure: '2026-09-20T10:00:00+02:00' }), termin({ departure: '2026-09-18T10:00:00+02:00' })]);
  assert.deepEqual(t.map((x) => x.abfahrt), [Date.UTC(2026, 8, 18, 8, 0), Date.UTC(2026, 8, 20, 8, 0)]);
});

// --- horizontHinweis: Spec C12H Abschnitt 2 ---------------------------------
import { horizontHinweis } from '../../custom_components/meteo_volt/frontend/plan.js';

const H_ENDE = Date.UTC(2026, 9, 17, 0, 0);
const H_TAG = 24 * 3600 * 1000;
const H_AUTO = { soc_min_pct: 15, soc_max_pct: 80, capacity_kwh: 58, consumption_kwh_per_100km: 19.5 };
const hTermin = (abfahrt, felder = {}) => ({ abfahrt, distance_km: 175, soc: 95, keep_min_soc: false, ...felder });

test('horizontHinweis: genau auf dem Planende und genau eine Woche danach ja, danach nicht', () => {
  assert.deepEqual(horizontHinweis(hTermin(H_ENDE), H_AUTO, H_ENDE), { soc: 95, max: 80 });
  assert.deepEqual(horizontHinweis(hTermin(H_ENDE + 7 * H_TAG), H_AUTO, H_ENDE), { soc: 95, max: 80 });
  assert.equal(horizontHinweis(hTermin(H_ENDE + 7 * H_TAG + 60000), H_AUTO, H_ENDE), null);
});

test('horizontHinweis: vor dem Planende nie -- dort plant der Planer selbst', () => {
  assert.equal(horizontHinweis(hTermin(H_ENDE - 60000), H_AUTO, H_ENDE), null);
});

test('horizontHinweis: nur ueber Max-SoC, Gleichstand reicht nicht', () => {
  assert.equal(horizontHinweis(hTermin(H_ENDE + H_TAG, { soc: 80 }), H_AUTO, H_ENDE), null);
  assert.deepEqual(horizontHinweis(hTermin(H_ENDE + H_TAG, { soc: 81 }), H_AUTO, H_ENDE), { soc: 81, max: 80 });
});

test('horizontHinweis: der Haken zaehlt mit, der hoehere Wert gilt', () => {
  // 600 km kosten 202 Prozentpunkte: gesichert bei 100 gedeckelt.
  assert.deepEqual(horizontHinweis(hTermin(H_ENDE + H_TAG, { soc: null, keep_min_soc: true, distance_km: 600 }), H_AUTO, H_ENDE), { soc: 100, max: 80 });
  // 175 km gesichert 74 %, unter Max-SoC: kein Hinweis.
  assert.equal(horizontHinweis(hTermin(H_ENDE + H_TAG, { soc: null, keep_min_soc: true }), H_AUTO, H_ENDE), null);
});

test('horizontHinweis: ohne Plan kein Hinweis', () => {
  assert.equal(horizontHinweis(hTermin(H_ENDE + H_TAG), H_AUTO, null), null);
});

