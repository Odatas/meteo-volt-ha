// Prueft texte.js und format.js: beide Sprachen, dieselben Meldungen wie C3. Spec C8 Abschnitt 9.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { formatierer } from '../../custom_components/meteo_volt/frontend/format.js';
import { TEXTE, WOERTER, sprache, text } from '../../custom_components/meteo_volt/frontend/texte.js';

const TZ = 'Europe/Berlin';
const uebersetzung = (sp) => JSON.parse(readFileSync(
  new URL(`../../custom_components/meteo_volt/translations/${sp}.json`, import.meta.url), 'utf8',
));
const platzhalter = (vorlage) => [...vorlage.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

test('beide Sprachen haben dieselben Texte mit denselben Platzhaltern', () => {
  assert.deepEqual(Object.keys(TEXTE.en).sort(), Object.keys(TEXTE.de).sort());
  for (const schluessel of Object.keys(TEXTE.de)) {
    assert.deepEqual(platzhalter(TEXTE.en[schluessel]), platzhalter(TEXTE.de[schluessel]), schluessel);
  }
  for (const liste of Object.keys(WOERTER.de)) assert.equal(WOERTER.en[liste].length, WOERTER.de[liste].length, liste);
});

test('die Meldungen aus C3-Spec 2.3 stehen wortgleich wie in den Uebersetzungen', () => {
  for (const sp of ['de', 'en']) {
    const meldungen = uebersetzung(sp).exceptions;
    assert.equal(Object.keys(meldungen).length, 19);
    for (const [schluessel, { message }] of Object.entries(meldungen)) {
      assert.equal(TEXTE[sp][schluessel], message, `${sp}.${schluessel}`);
    }
  }
});

test('Deutsch nur fuer Deutsch', () => {
  assert.equal(sprache('de'), 'de');
  assert.equal(sprache('de-CH'), 'de');
  assert.equal(sprache('en-GB'), 'en');
  assert.equal(sprache('fr'), 'en');
  assert.equal(sprache(undefined), 'en');
});

test('Platzhalter werden ersetzt, ein fehlender bleibt stehen, ein fehlender Text wirft', () => {
  assert.equal(text('de', 'plan_von', { zeit: '14:32' }), 'Plan von 14:32');
  assert.equal(text('de', 'plan_von'), 'Plan von {zeit}');
  assert.throws(() => text('de', 'gibt_es_nicht'));
});

test('Datum und Tageskoepfe', () => {
  const jetzt = Date.UTC(2026, 8, 16, 12, 35);
  const de = formatierer('de', TZ);
  const en = formatierer('en', TZ);
  assert.equal(de.tag(jetzt), 'Mi 16.09.');
  assert.equal(en.tag(jetzt), 'Wed 16 Sep');
  assert.equal(de.tagKopf('2026-09-16', jetzt), 'Heute, Mi 16.09.');
  assert.equal(de.tagKopf('2026-09-17', jetzt), 'Morgen, Do 17.09.');
  assert.equal(de.tagKopf('2026-09-18', jetzt), 'Freitag, 18.09.');
  assert.equal(en.tagKopf('2026-09-16', jetzt), 'Today, Wed 16 Sep');
  assert.equal(en.tagKopf('2026-09-17', jetzt), 'Tomorrow, Thu 17 Sep');
  assert.equal(en.tagKopf('2026-09-18', jetzt), 'Friday, 18 Sep');
  assert.equal(de.tagZeit(Date.UTC(2026, 8, 23, 12, 30)), 'Mi 23.09. 14:30');
  assert.equal(de.wochentagZeit(Date.UTC(2026, 8, 19, 8, 0)), 'Sa 10:00');
});

test('Uhrzeit mit Tag: heute ohne, morgen mit morgen, danach mit Wochentag', () => {
  const jetzt = Date.UTC(2026, 8, 16, 12, 35);
  const de = formatierer('de', TZ);
  const en = formatierer('en', TZ);
  assert.equal(de.zeitMitTag(Date.UTC(2026, 8, 16, 15, 30), jetzt), '17:30');
  assert.equal(de.zeitMitTag(Date.UTC(2026, 8, 17, 15, 30), jetzt), 'morgen 17:30');
  assert.equal(de.zeitMitTag(Date.UTC(2026, 8, 18, 15, 30), jetzt), 'Fr 17:30');
  assert.equal(en.zeitMitTag(Date.UTC(2026, 8, 17, 15, 30), jetzt), 'tomorrow 17:30');
});

test('Zahlen je Sprache', () => {
  const de = formatierer('de', TZ);
  const en = formatierer('en', TZ);
  assert.equal(de.kwh(13.44), '13,4 kWh');
  assert.equal(en.kwh(13.44), '13.4 kWh');
  assert.equal(de.kw(11), '11 kW');
  assert.equal(de.kw(3.7), '3,7 kW');
  assert.equal(de.ct(0.16), '16,0 ct/kWh');
  assert.equal(de.ctKurz(0.0525), '5,3 ct');
  assert.equal(de.eur(3.2), '3,20 €');
  assert.equal(en.eur(3.2), '€3.20');
  assert.equal(en.eur(-0.5), '-€0.50');
  assert.equal(de.prozent(79.6), '80 %');
  assert.equal(de.zahlKurz(15), '15');
  assert.equal(de.zahlKurz(15.5), '15,5');
});

test('die Wiederholung im Formular', () => {
  const de = formatierer('de', TZ);
  const en = formatierer('en', TZ);
  assert.equal(de.regelLang('once', '2026-09-16'), 'Einmalig');
  assert.equal(de.regelLang('weekdays', '2026-09-16'), 'Jeden Werktag (Mo–Fr)');
  assert.equal(de.regelLang('weekly', '2026-09-16'), 'Wöchentlich am Mittwoch');
  assert.equal(de.regelLang('monthly', '2026-09-16'), 'Monatlich am dritten Mittwoch');
  assert.equal(de.regelLang('monthly', '2026-09-30'), 'Monatlich am letzten Mittwoch');
  assert.equal(de.regelLang('yearly', '2026-09-16'), 'Jährlich am 16. September');
  assert.equal(en.regelLang('monthly', '2026-09-16'), 'Monthly on the third Wednesday');
  assert.equal(en.regelLang('yearly', '2026-09-16'), 'Annually on 16 September');
});

test('die Wiederholung in der Liste', () => {
  const de = formatierer('de', TZ);
  assert.equal(de.regelKurz('once', '2026-09-16'), '');
  assert.equal(de.regelKurz('daily', '2026-09-16'), 'Täglich');
  assert.equal(de.regelKurz('weekdays', '2026-09-16'), 'Mo–Fr');
  assert.equal(de.regelKurz('weekly', '2026-09-16'), 'Jeden Mittwoch');
  assert.equal(de.regelKurz('monthly', '2026-09-16'), 'Monatlich am dritten Mittwoch');
  assert.equal(de.regelKurz('monthly', '2026-10-28'), 'Monatlich');
  assert.equal(de.regelKurz('monthly', '2026-10-29'), 'Monatlich am letzten Donnerstag');
});
