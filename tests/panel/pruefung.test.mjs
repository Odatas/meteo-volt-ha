// Prueft pruefung.js: die Faelle aus C3-Spec 2.3 beim Eingeben. Spec C8 Abschnitt 7.2.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ORT, fahrerKonflikt, pruefen } from '../../custom_components/meteo_volt/frontend/pruefung.js';

const TZ = 'Europe/Berlin';
const JETZT = Date.UTC(2026, 8, 16, 12, 35); // Mi 16.09.2026 14:35 in Berlin
const K = { jetzt: JETZT, tz: TZ, socMin: 15, versucht: false };

const formular = (felder = {}) => ({
  abfahrt: '2026-09-17T08:00:00', rueckkehr: '2026-09-17T18:00:00', regel: 'once', km: 45, soc: null, ...felder,
});
const schluessel = (ergebnis) => ergebnis.meldungen.map((m) => m.key);

test('ein gueltiger Termin', () => {
  const e = pruefen(formular(), K);
  assert.deepEqual(e.meldungen, []);
  assert.equal(e.ok, true);
  assert.deepEqual(e.werte, { abfahrt: '2026-09-17T08:00:00', dauerMin: 600, regel: 'once' });
});

test('Datum oder Uhrzeit fehlt', () => {
  assert.deepEqual(schluessel(pruefen(formular({ abfahrt: null }), K)), ['zeit_fehlt']);
  assert.deepEqual(schluessel(pruefen(formular({ rueckkehr: '' }), K)), ['zeit_fehlt']);
  assert.equal(pruefen(formular({ abfahrt: null }), K).werte, null);
});

test('die Rueckkehr nicht nach der Abfahrt', () => {
  const e = pruefen(formular({ rueckkehr: '2026-09-17T08:00:00' }), K);
  assert.deepEqual(schluessel(e), ['rueckkehr_vor_abfahrt']);
  assert.equal(e.meldungen[0].ort, 'rueckkehr');
});

test('einmalig und die Rueckkehr vorbei, bei einer Serie nicht', () => {
  const vorbei = { abfahrt: '2026-09-16T08:00:00', rueckkehr: '2026-09-16T14:00:00' };
  assert.deepEqual(schluessel(pruefen(formular(vorbei), K)), ['rueckkehr_vorbei']);
  assert.deepEqual(schluessel(pruefen(formular({ ...vorbei, regel: 'daily' }), K)), []);
});

test('ein laufender Termin ist erlaubt', () => {
  assert.equal(pruefen(formular({ abfahrt: '2026-09-16T08:00:00', rueckkehr: '2026-09-16T18:00:00' }), K).ok, true);
});

test('eine Serie dauert so lange wie ihr Abstand', () => {
  const lang = { abfahrt: '2026-09-17T08:00:00', rueckkehr: '2026-09-18T08:00:00' };
  const e = pruefen(formular({ ...lang, regel: 'daily' }), K);
  assert.deepEqual(schluessel(e), ['dauer_zu_lang']);
  assert.equal(e.meldungen[0].ort, 'wiederholung');
  assert.deepEqual(schluessel(pruefen(formular({ ...lang, regel: 'weekly' }), K)), []);
});

test('die Dauer ist verstrichene Zeit: ueber die Umstellung 24 h auf der Uhr sind 25 h', () => {
  const ueber = { abfahrt: '2026-10-24T12:00:00', rueckkehr: '2026-10-25T11:30:00', regel: 'daily' };
  assert.deepEqual(schluessel(pruefen(formular(ueber), K)), ['dauer_zu_lang']);
});

test('die Strecke fehlt erst nach dem ersten Speichern', () => {
  const ohne = pruefen(formular({ km: null }), K);
  assert.deepEqual(schluessel(ohne), []);
  assert.equal(ohne.ok, false);
  assert.deepEqual(schluessel(pruefen(formular({ km: '' }), { ...K, versucht: true })), ['strecke_fehlt']);
  assert.deepEqual(schluessel(pruefen(formular({ km: -3 }), K)), ['strecke_negativ']);
});

test('der Ladestand: Bereich ist ein Fehler, unter dem Min-SoC eine Warnung', () => {
  assert.deepEqual(schluessel(pruefen(formular({ soc: 101 }), K)), ['ladestand_bereich']);
  const unter = pruefen(formular({ soc: 10 }), K);
  assert.deepEqual(unter.meldungen, [{ key: 'ladestand_unter_min', ort: 'ladestand', art: 'warnung', platzhalter: { min: 15 } }]);
  assert.equal(unter.ok, true);
});

test('die Reihenfolge der Tabelle 2.3', () => {
  const e = pruefen(formular({ rueckkehr: '2026-09-17T07:00:00', km: -1, soc: 200 }), K);
  assert.deepEqual(schluessel(e), ['rueckkehr_vor_abfahrt', 'strecke_negativ', 'ladestand_bereich']);
  assert.deepEqual(Object.keys(ORT), [
    'zeit_fehlt', 'rueckkehr_vor_abfahrt', 'rueckkehr_vorbei', 'dauer_zu_lang', 'strecke_fehlt', 'strecke_negativ',
    'ladestand_bereich', 'ladestand_unter_min', 'fahrer_doppelt',
  ]);
});

// --- Die Warnung zum Fahrer --------------------------------------------------------

const termin = (felder) => ({
  entry: 'e9', date: '2026-09-19', vehicle: 'dev-zoe', departure: '2026-09-19T09:00:00+02:00',
  return: '2026-09-19T12:00:00+02:00', driver: 'person.anna', ...felder,
});
const werte = (abfahrt, dauerMin, regel = 'once') => ({ abfahrt, dauerMin, regel });

test('der Fahrer ist zur selben Zeit mit einem anderen Fahrzeug unterwegs', () => {
  const k = fahrerKonflikt(werte('2026-09-19T10:00:00', 120), 'person.anna', 'dev-buzz', [termin()], null, JETZT, TZ);
  assert.equal(k.eigen.datum, '2026-09-19');
  assert.equal(k.anderer.vehicle, 'dev-zoe');
});

test('der erste eigene Termin einer Serie mit Ueberschneidung', () => {
  const k = fahrerKonflikt(werte('2026-09-17T10:00:00', 120, 'daily'), 'person.anna', 'dev-buzz', [termin()], null, JETZT, TZ);
  assert.equal(k.eigen.datum, '2026-09-19');
});

test('kein Konflikt: anderes Fahrzeug frei, dasselbe Fahrzeug, anderer Fahrer, der bearbeitete Eintrag', () => {
  const w = werte('2026-09-19T10:00:00', 120);
  assert.equal(fahrerKonflikt(w, 'person.anna', 'dev-buzz', [termin({ departure: '2026-09-19T12:00:00+02:00', return: '2026-09-19T13:00:00+02:00' })], null, JETZT, TZ), null);
  assert.equal(fahrerKonflikt(w, 'person.anna', 'dev-zoe', [termin()], null, JETZT, TZ), null);
  assert.equal(fahrerKonflikt(w, 'person.patrick', 'dev-buzz', [termin()], null, JETZT, TZ), null);
  assert.equal(fahrerKonflikt(w, 'person.anna', 'dev-buzz', [termin()], 'e9', JETZT, TZ), null);
  assert.equal(fahrerKonflikt(w, null, 'dev-buzz', [termin()], null, JETZT, TZ), null);
  assert.equal(fahrerKonflikt(null, 'person.anna', 'dev-buzz', [termin()], null, JETZT, TZ), null);
});

test('der Fahrer wird acht Wochen voraus geprueft', () => {
  const spaet = termin({ departure: '2026-11-11T10:00:00+01:00', return: '2026-11-11T12:00:00+01:00' });
  const w = werte('2026-09-16T10:00:00', 120, 'daily');
  assert.equal(fahrerKonflikt(w, 'person.anna', 'dev-buzz', [spaet], null, JETZT, TZ).eigen.datum, '2026-11-11');
  const zuSpaet = termin({ departure: '2026-11-12T10:00:00+01:00', return: '2026-11-12T12:00:00+01:00' });
  assert.equal(fahrerKonflikt(w, 'person.anna', 'dev-buzz', [zuSpaet], null, JETZT, TZ), null);
});
