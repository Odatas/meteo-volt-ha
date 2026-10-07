// Prueft wiederholung.js: die Regeln aus C3-Spec Abschnitt 2. Spec C8 Abschnitte 6.4 und 7.2.
// Den Vergleich mit termine.py macht tests/test_panel.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  ABSTAND_MIN, ausrollen, monatsregel, ordinalAusTermin, regeldaten, ueberschneiden,
} from '../../custom_components/meteo_volt/frontend/wiederholung.js';
import { zuMs } from '../../custom_components/meteo_volt/frontend/zeit.js';

const TZ = 'Europe/Berlin';

test('einmalig nur am Datum', () => {
  assert.deepEqual(regeldaten('2026-09-16', 'once', '2026-09-14', '2026-09-20'), ['2026-09-16']);
  assert.deepEqual(regeldaten('2026-09-16', 'once', '2026-09-17', '2026-09-20'), []);
});

test('taeglich und werktags', () => {
  assert.deepEqual(regeldaten('2026-09-16', 'daily', '2026-09-17', '2026-09-19'), ['2026-09-17', '2026-09-18', '2026-09-19']);
  assert.deepEqual(regeldaten('2026-09-17', 'weekdays', '2026-09-01', '2026-09-22'),
    ['2026-09-17', '2026-09-18', '2026-09-21', '2026-09-22']);
});

test('werktags ab einem Samstag beginnt am Montag', () => {
  assert.deepEqual(regeldaten('2026-09-19', 'weekdays', '2026-09-19', '2026-09-22'), ['2026-09-21', '2026-09-22']);
});

test('woechentlich am Wochentag der Abfahrt', () => {
  assert.deepEqual(regeldaten('2026-09-16', 'weekly', '2026-09-18', '2026-10-01'), ['2026-09-23', '2026-09-30']);
});

test('monatlich am n-ten Wochentag, ab dem 29. am letzten', () => {
  // 16.09.2026 ist der dritte Mittwoch
  assert.deepEqual(regeldaten('2026-09-16', 'monthly', '2026-09-01', '2026-12-31'),
    ['2026-09-16', '2026-10-21', '2026-11-18', '2026-12-16']);
  // 30.09.2026 ist ein Mittwoch ab dem 29.: der letzte Mittwoch
  assert.deepEqual(regeldaten('2026-09-30', 'monthly', '2026-09-01', '2026-12-31'),
    ['2026-09-30', '2026-10-28', '2026-11-25', '2026-12-30']);
  // 28.09.2026 ist der vierte Montag
  assert.deepEqual(regeldaten('2026-09-28', 'monthly', '2026-09-01', '2026-11-30'),
    ['2026-09-28', '2026-10-26', '2026-11-23']);
  assert.deepEqual(monatsregel('2026-09-30'), { n: 5, wochentag: 3 });
});

test('jaehrlich, der 29. Februar nur im Schaltjahr', () => {
  assert.deepEqual(regeldaten('2028-02-29', 'yearly', '2028-01-01', '2033-12-31'), ['2028-02-29', '2032-02-29']);
  assert.deepEqual(regeldaten('2026-09-16', 'yearly', '2026-09-17', '2028-09-16'), ['2027-09-16', '2028-09-16']);
});

test('eine unbekannte Wiederholung wirft', () => {
  assert.throws(() => regeldaten('2026-09-16', 'hourly', '2026-09-16', '2026-09-17'));
});

test('die Ordinalzahl in der Liste nur, wenn das Datum sie eindeutig macht', () => {
  assert.equal(ordinalAusTermin('2026-09-16'), 3);
  assert.equal(ordinalAusTermin('2026-09-01'), 1);
  assert.equal(ordinalAusTermin('2026-09-30'), 5);
  // 23.09.2026: noch ein Mittwoch am 30. -- also der vierte, nicht der letzte
  assert.equal(ordinalAusTermin('2026-09-23'), 4);
  // 24.09.2026: der letzte Donnerstag, der 31. fehlt dem September
  assert.equal(ordinalAusTermin('2026-09-24'), null);
  // 28.10.2026: der letzte Mittwoch im Oktober -- vierter oder letzter, je nach Serie
  assert.equal(ordinalAusTermin('2026-10-28'), null);
});

test('ausrollen behaelt die Dauer ueber die Umstellung', () => {
  const werte = { abfahrt: '2026-10-24T22:00:00', dauerMin: 480, regel: 'daily' };
  const liste = ausrollen(werte, TZ, zuMs('2026-10-24T00:00', TZ), zuMs('2026-10-26T00:00', TZ));
  assert.deepEqual(liste.map((t) => t.datum), ['2026-10-24', '2026-10-25']);
  assert.equal(liste[0].rueckkehr - liste[0].abfahrt, 480 * 60000);
  assert.equal(liste[0].rueckkehr, Date.UTC(2026, 9, 25, 4, 0));
});

test('ausrollen nimmt einen Termin, der vor dem Fenster beginnt und hinein reicht', () => {
  const werte = { abfahrt: '2026-09-14T20:00:00', dauerMin: 2 * 1440 + 60, regel: 'weekly' };
  const liste = ausrollen(werte, TZ, zuMs('2026-09-16T12:00', TZ), zuMs('2026-09-17T12:00', TZ));
  assert.deepEqual(liste.map((t) => t.datum), ['2026-09-14']);
});

test('Abstaende und Ueberschneidung', () => {
  assert.equal(ABSTAND_MIN.daily, 1440);
  assert.equal(ABSTAND_MIN.monthly, 28 * 1440);
  assert.equal(ueberschneiden({ abfahrt: 0, rueckkehr: 10 }, { abfahrt: 10, rueckkehr: 20 }), false);
  assert.equal(ueberschneiden({ abfahrt: 0, rueckkehr: 11 }, { abfahrt: 10, rueckkehr: 20 }), true);
});
