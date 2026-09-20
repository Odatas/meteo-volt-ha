// Prueft plan.js: was das Panel aus Plan und Terminen ableitet. Spec C8 Abschnitte 6.2 bis 6.4.
//
// Der Plan ist erzeugt: 96 Slots ab Mi 16.09.2026 14:30 in Berlin, soc_end_pct im
// Slot i ist 40 + i / 4, geladen wird in den Slots 30 bis 37 (22:00 bis 24:00).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  blockGrund, bloeckeAbJetzt, hatWarnung, laeuft, planAbJetzt, planende, planzeile, status, summen, termineAus, zerlegen,
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

test('der Grund eines Blocks: Ziel, vor der naechsten Abfahrt, bis zum Planende', () => {
  const termine = termineAus([termin(), termin({ entry: 'e1', date: '2026-09-17', soc: null, departure: '2026-09-17T07:30:00+02:00', return: '2026-09-17T17:30:00+02:00' })]);
  const [basis, ziel] = bloeckeAbJetzt(plan(), START);
  assert.deepEqual(blockGrund(ziel, termine), { art: 'ziel', termin: termine[1] });
  const vor = blockGrund(basis, termine);
  assert.equal(vor.art, 'vor');
  assert.equal(vor.termin.entry, 'e1');
  assert.deepEqual(blockGrund(basis, []), { art: 'ende' });
  // Ein Ziel, dessen Termin nicht geladen ist, nennt die naechste Abfahrt.
  assert.equal(blockGrund(ziel, termineAus([termin({ entry: 'e1', date: '2026-09-20', soc: null, departure: '2026-09-20T07:30:00+02:00', return: '2026-09-20T08:30:00+02:00' })])).art, 'vor');
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

test('das Planende und die Reihenfolge der Termine', () => {
  assert.equal(planende([null, plan()], START), START + 96 * 15 * MIN);
  assert.equal(planende([plan()], START + 96 * 15 * MIN), null);
  const t = termineAus([termin({ departure: '2026-09-20T10:00:00+02:00' }), termin({ departure: '2026-09-18T10:00:00+02:00' })]);
  assert.deepEqual(t.map((x) => x.abfahrt), [Date.UTC(2026, 8, 18, 8, 0), Date.UTC(2026, 8, 20, 8, 0)]);
});
