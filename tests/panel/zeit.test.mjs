// Prueft zeit.js: Wanduhr und Umstellung in Europe/Berlin. Spec C8 Abschnitte 7.2 und 9.
// Am 29.03.2026 fehlt 02:00 bis 03:00, am 25.10.2026 gibt es 02:00 bis 03:00 zweimal.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  ausIso, datumVon, naechsteVolleStunde, naiv, plusTage, tageImMonat, tagesbeginn, wanduhr, wochentag, zuMs,
} from '../../custom_components/meteo_volt/frontend/zeit.js';

const TZ = 'Europe/Berlin';

test('eine lokale Zeit im Sommer', () => {
  assert.equal(zuMs('2026-09-21T08:00:00', TZ), Date.UTC(2026, 8, 21, 6, 0));
  assert.equal(zuMs('2026-09-21T08:00', TZ), Date.UTC(2026, 8, 21, 6, 0));
  assert.equal(zuMs('2026-01-10 23:15:00', TZ), Date.UTC(2026, 0, 10, 22, 15));
});

test('eine Uhrzeit, die es nicht gibt, liegt eine Stunde spaeter', () => {
  assert.equal(zuMs('2026-03-29T02:30:00', TZ), Date.UTC(2026, 2, 29, 1, 30));
  assert.equal(naiv(zuMs('2026-03-29T02:30:00', TZ), TZ), '2026-03-29T03:30:00');
});

test('eine doppelte Uhrzeit gilt beim ersten Mal', () => {
  assert.equal(zuMs('2026-10-25T02:30:00', TZ), Date.UTC(2026, 9, 25, 0, 30));
});

test('um die Umstellung herum', () => {
  assert.equal(zuMs('2026-03-29T01:30:00', TZ), Date.UTC(2026, 2, 29, 0, 30));
  assert.equal(zuMs('2026-03-29T04:00:00', TZ), Date.UTC(2026, 2, 29, 2, 0));
  assert.equal(zuMs('2026-10-25T01:30:00', TZ), Date.UTC(2026, 9, 24, 23, 30));
  assert.equal(zuMs('2026-10-25T03:30:00', TZ), Date.UTC(2026, 9, 25, 2, 30));
});

test('keine Zeit ist null', () => {
  assert.equal(zuMs('', TZ), null);
  assert.equal(zuMs(null, TZ), null);
  assert.equal(zuMs('2026-09-21', TZ), null);
});

test('Wanduhr, Datum und naiv', () => {
  const ms = Date.UTC(2026, 8, 16, 12, 35);
  assert.deepEqual(wanduhr(ms, TZ), { jahr: 2026, monat: 9, tag: 16, stunde: 14, minute: 35, sekunde: 0, wochentag: 3 });
  assert.equal(datumVon(ms, TZ), '2026-09-16');
  assert.equal(naiv(ms, TZ), '2026-09-16T14:35:00');
  assert.equal(datumVon(Date.UTC(2026, 8, 16, 22, 30), TZ), '2026-09-17');
  assert.equal(tagesbeginn('2026-09-17', TZ), Date.UTC(2026, 8, 16, 22, 0));
});

test('Tage zaehlen ohne Zeitzone', () => {
  assert.equal(plusTage('2026-12-31', 1), '2027-01-01');
  assert.equal(plusTage('2026-03-01', -1), '2026-02-28');
  assert.equal(plusTage('2028-02-28', 1), '2028-02-29');
  assert.equal(wochentag('2026-09-19'), 6);
  assert.equal(wochentag('2026-09-20'), 0);
  assert.equal(tageImMonat(2028, 2), 29);
  assert.equal(tageImMonat(2026, 2), 28);
});

test('ISO 8601 mit Offset, auch mit Mikrosekunden', () => {
  assert.equal(ausIso('2026-09-16T14:30:00+02:00'), Date.UTC(2026, 8, 16, 12, 30));
  assert.equal(ausIso('2026-09-19T10:00:00.123456+00:00'), Date.UTC(2026, 8, 19, 10, 0, 0, 123));
  assert.equal(ausIso(null), null);
  assert.equal(ausIso('kein Datum'), null);
});

test('die naechste volle Stunde', () => {
  assert.equal(naechsteVolleStunde(Date.UTC(2026, 8, 16, 12, 35), TZ), '2026-09-16T15:00:00');
  assert.equal(naechsteVolleStunde(Date.UTC(2026, 8, 16, 21, 59), TZ), '2026-09-17T00:00:00');
});
