// Prueft ansichten.js, preisansicht.js und diagramme.js als Text: Namen werden escaped,
// die Entscheidungen der Spec stehen im HTML. Spec C8 Abschnitte 4 und 6.
// Wie es aussieht, zeigt die Vorschau unter tests/panel/vorschau.html.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { fahrzeugHtml, uebersichtHtml } from '../../custom_components/meteo_volt/frontend/ansichten.js';
import { planChartSvg } from '../../custom_components/meteo_volt/frontend/diagramme.js';
import { formatierer } from '../../custom_components/meteo_volt/frontend/format.js';
import { planAbJetzt, termineAus } from '../../custom_components/meteo_volt/frontend/plan.js';
import { preiseHtml } from '../../custom_components/meteo_volt/frontend/preisansicht.js';
import { preisSlots } from '../../custom_components/meteo_volt/frontend/preise.js';

const TZ = 'Europe/Berlin';
const MIN = 60000;
const JETZT = Date.UTC(2026, 8, 16, 12, 35); // Mi 16.09.2026 14:35
const START = Date.UTC(2026, 8, 16, 12, 30);
const ENDE = START + 96 * 15 * MIN; // Do 17.09. 14:30
const iso = (ms) => new Date(ms).toISOString();
const BOESE = '<img src=x onerror=alert(1)>';

const fahrzeug = { vehicle: 'dev-1', title: BOESE, soc_min_pct: 15, soc_max_pct: 80, max_charge_kw: 11, soc_pct: 62 };
const plan = {
  slots: Array.from({ length: 96 }, (_, i) => ({ t: iso(START + i * 15 * MIN), charge: false, price: 0.1, source: 'epex', soc_end_pct: 62 })),
  intervals: [], horizon_end: iso(ENDE), computed_at: iso(START), charge_now: false, charge_now_kw: 0, next_charge_start: null,
  soc_end_pct: 62, planning: false, error: null,
};
const termin = (felder) => ({
  entry: 'e1', date: '2026-09-17', vehicle: 'dev-1', departure: '2026-09-17T07:30:00+02:00', return: '2026-09-17T17:30:00+02:00',
  distance_km: 45, driver: 'person.x', soc: null, repeat: 'once', changed: false, plan: null, hints: [], ...felder,
});

function kontext(felder = {}) {
  const termine = termineAus(felder.termine || [termin()]);
  const plaene = new Map([['dev-1', felder.plan === undefined ? plan : felder.plan]]);
  return {
    f: formatierer('de', TZ), jetzt: JETZT, tz: TZ,
    ui: { tab: 'dev-1', filter: 'alle', tageUebersicht: 7, tageFahrzeug: 21, bereich: 'alles', preisart: 'kunde', fensterStunden: 2, alleBloecke: false },
    fahrzeuge: [fahrzeug], personen: [{ entity_id: 'person.x', name: BOESE }], risiko: 2, netzentgelt: null, gebuehr: 0,
    plaene, fenster: new Map([['dev-1', planAbJetzt(plaene.get('dev-1'), JETZT, 62)]]), termine,
    planende: plaene.get('dev-1') ? ENDE : null, preise: [], preiseRoh: {}, planFehler: null, ...felder.z,
  };
}

test('Titel und Namen aus Home Assistant werden escaped', () => {
  for (const text of [String(uebersichtHtml(kontext())), String(fahrzeugHtml(kontext(), fahrzeug))]) {
    assert.ok(!text.includes('<img'), 'roher Name im HTML');
    assert.ok(text.includes('&lt;img src=x onerror=alert(1)&gt;'));
  }
  const z = kontext();
  const { svg } = planChartSvg({ schluessel: 'p0', fz: fahrzeug, name: fahrzeug.title, fenster: z.fenster.get('dev-1'), termine: z.termine, bereich: 'alles' }, 600, false, z.f, 0);
  assert.ok(!String(svg).includes('<img'));
});

test('der Trenner zum Planende und die Planzeile nur davor', () => {
  const z = kontext({ termine: [
    termin({ plan: { soc_at_departure: 80, soc_after_trip: 70, target_missing_kwh: null, below_min: false, running_until: null } }),
    termin({ entry: 'e2', date: '2026-09-18', departure: '2026-09-18T07:30:00+02:00', return: '2026-09-18T17:30:00+02:00' }),
  ] });
  const text = String(fahrzeugHtml(z, fahrzeug));
  assert.ok(text.includes('Abfahrt mit 80 %'));
  assert.ok(text.indexOf('Ab Do 17.09. 14:30 noch nicht geplant') > text.indexOf('Abfahrt mit 80 %'));
});

test('ohne Plan kein Trenner, der Status sagt es', () => {
  const text = String(fahrzeugHtml(kontext({ plan: null }), fahrzeug));
  assert.ok(!text.includes('noch nicht geplant'));
  assert.ok(text.includes('Noch kein Plan'));
});

test('eine leere Liste bietet trotzdem weitere Termine an', () => {
  const text = String(fahrzeugHtml(kontext({ termine: [] }), fahrzeug));
  assert.ok(text.includes('Keine Termine. Ohne Termine plant Meteo-Volt ohne Fahrten.'));
  assert.ok(text.includes('Weitere Termine anzeigen'));
});

test('Wiederholung, einzeln geaendert und Ziel in der Liste', () => {
  const text = String(fahrzeugHtml(kontext({ termine: [
    termin({ repeat: 'monthly', date: '2026-09-24', departure: '2026-09-24T07:30:00+02:00', return: '2026-09-24T09:30:00+02:00', changed: true, soc: 100 }),
  ] }), fahrzeug));
  assert.ok(text.includes('Monatlich, einzeln geändert'));
  assert.ok(text.includes('Ziel 100 %'));
});

test('ein Ziel unter dem Min-SoC steht nicht als Ziel da', () => {
  const text = String(fahrzeugHtml(kontext({ termine: [termin({ soc: 10 })] }), fahrzeug));
  assert.ok(!text.includes('Ziel 10 %'));
});

test('die Hinweise eines Termins stehen in der Liste', () => {
  const z = kontext({ termine: [termin({
    hints: [{ type: 'overlap' }, { type: 'driver_busy', vehicle: 'dev-1' }, { type: 'driver_busy', vehicle: 'dev-weg' }],
  })] });
  const text = String(fahrzeugHtml(z, fahrzeug));
  assert.ok(text.includes('Überschneidet sich mit einem anderen Termin dieses Autos'));
  // Der Fahrer steht mit dem Titel des anderen Fahrzeugs da, escaped
  assert.ok(text.includes('zur selben Zeit mit &lt;img src=x onerror=alert(1)&gt; unterwegs'));
  // Ein Fahrzeug ohne Titel, etwa eines ohne Geraet
  assert.ok(text.includes('zur selben Zeit mit einem anderen Fahrzeug unterwegs'));
  assert.ok(!text.includes('<img'));
});

test('der Planfehler steht als Warnung ueber dem Inhalt', () => {
  const text = String(uebersichtHtml(kontext({ z: { planFehler: 'PlanNichtVerfuegbar: 503' } })));
  assert.ok(text.includes('Der letzte Versuch zu planen ist gescheitert: PlanNichtVerfuegbar: 503'));
});

test('ohne Netzentgelt kein Schalter, mit Netzentgelt die Kosten mit', () => {
  const ohne = String(uebersichtHtml(kontext()));
  assert.ok(ohne.includes('Börsenpreis, kein Netzentgelt angegeben'));
  assert.ok(!ohne.includes('data-aktion="preisart"'));
  const mit = kontext({ z: { netzentgelt: 0.16, gebuehr: 0.16 } });
  assert.ok(String(uebersichtHtml(mit)).includes('Mit Netzentgelt 16,0 ct/kWh'));
  assert.ok(String(fahrzeugHtml(mit, fahrzeug)).includes('data-aktion="preisart"'));
  assert.ok(String(fahrzeugHtml(mit, fahrzeug)).includes('Kosten mit Netzentgelt'));
});

test('der Tab Preise ohne Prognose und mit', () => {
  assert.ok(String(preiseHtml(kontext())).includes('Noch keine Prognose.'));
  const preise = { slots: Array.from({ length: 8 }, (_, i) => ({ t: iso(START + i * 15 * MIN), q10: 0.1, q50: 0.1 + i / 100, q90: 0.1, source: 'epex' })), computed_at: iso(START), model: BOESE };
  const text = String(preiseHtml(kontext({ z: { preise: preisSlots(preise, JETZT), preiseRoh: preise } })));
  assert.ok(text.includes('Preis jetzt'));
  assert.ok(text.includes('Modell &lt;img'));
  assert.ok(!text.includes('<img'));
});

test('C12H: hinter dem Planende steht der dezente Hinweis, davor nicht', () => {
  const z = kontext({ termine: [
    termin({ soc: 95 }),
    termin({ entry: 'e2', date: '2026-09-18', departure: '2026-09-18T07:30:00+02:00', return: '2026-09-18T17:30:00+02:00', soc: 95 }),
  ] });
  const text = String(fahrzeugHtml(z, fahrzeug));
  const hinweis = 'Terminziel liegt mit 95 % über dem Max-SoC von 80 %. Die Planung beachtet dies erst, wenn der Termin im Vorhersagehorizont liegt.';
  assert.equal(text.split(hinweis).length - 1, 1, 'genau einmal, nur am Termin hinter dem Planende');
  assert.ok(text.indexOf(hinweis) > text.indexOf('noch nicht geplant'));
  assert.ok(text.includes('class="info"'));
});

test('C12H: der Hinweis auf Englisch', () => {
  const z = { ...kontext({ termine: [termin({ entry: 'e2', date: '2026-09-18', departure: '2026-09-18T07:30:00+02:00', return: '2026-09-18T17:30:00+02:00', soc: 95 })] }), f: formatierer('en', TZ) };
  assert.ok(String(fahrzeugHtml(z, fahrzeug)).includes('Trip target of 95 % is above the max SoC of 80 %. Planning takes it into account once the trip is within the forecast horizon.'));
});

test('C12H: der Hinweis traegt das Info-Symbol, nicht das Warnsymbol', () => {
  const z = kontext({ termine: [termin({ entry: 'e2', date: '2026-09-18', departure: '2026-09-18T07:30:00+02:00', return: '2026-09-18T17:30:00+02:00', soc: 95 })] });
  const text = String(fahrzeugHtml(z, fahrzeug));
  const info = text.slice(text.indexOf('<span class="info">'));
  assert.ok(info.includes('<circle cx="12" cy="12" r="9"/>'), 'Info-Symbol fehlt');
  assert.ok(!info.slice(0, info.indexOf('</span>')).includes('M12 3L2 20h20L12 3z'), 'Warnsymbol im Hinweis');
});

test('C12H: der Hinweis prueft das Max-SoC seines eigenen Fahrzeugs', () => {
  // Zwei Fahrzeuge, der Termin gehoert dem zweiten mit Max-SoC 100: 95 % liegen darunter.
  const zweites = { vehicle: 'dev-2', title: 'Zweites', soc_min_pct: 15, soc_max_pct: 100, max_charge_kw: 11, soc_pct: 50 };
  const basis = kontext({ termine: [termin({ vehicle: 'dev-2', entry: 'e2', date: '2026-09-18', departure: '2026-09-18T07:30:00+02:00', return: '2026-09-18T17:30:00+02:00', soc: 95 })] });
  const z = { ...basis, fahrzeuge: [fahrzeug, zweites] };
  assert.ok(!String(fahrzeugHtml(z, zweites)).includes('Terminziel liegt'));
});


// --- C9R: einen laufenden Termin ignorieren ---------------------------------------

const laufend = (felder) => termin({ entry: 'e9', date: '2026-09-16', departure: '2026-09-16T08:00:00+02:00', return: '2026-09-16T17:30:00+02:00', ...felder });

test('C9R: ein laufender Termin hat den Knopf, auch ohne Plan; ein kuenftiger nicht', () => {
  for (const mitPlan of [true, false]) {
    const text = String(fahrzeugHtml(kontext({ termine: [laufend(), termin()], plan: mitPlan ? plan : null }), fahrzeug));
    assert.equal((text.match(/data-aktion="ignorieren"/g) || []).length, 1, `mitPlan ${mitPlan}`);
    assert.ok(text.includes('data-entry="e9" data-date="2026-09-16" data-wert="ja"'));
    assert.ok(text.includes('Ist zurück'));
  }
});

test('C9R: ein ignorierter laufender Termin zeigt die gedaempfte Zeile und Beachten', () => {
  const p = { soc_at_departure: null, soc_after_trip: null, target_missing_kwh: null, below_min: false, running_until: '2026-09-16T17:30:00+02:00' };
  const text = String(fahrzeugHtml(kontext({ termine: [laufend({ ignored: true, plan: p })] }), fahrzeug));
  assert.ok(text.includes('Ignoriert, wird nicht geplant'));
  assert.ok(text.includes('data-wert="nein"'));
  assert.ok(text.includes('Beachten'));
  assert.ok(!text.includes('Unterwegs bis'), 'weder Status noch Planzeile sagen unterwegs');
});

test('C9R: der Knopf auf Englisch', () => {
  const z = kontext({ termine: [laufend()], z: { f: formatierer('en', TZ) } });
  assert.ok(String(fahrzeugHtml(z, fahrzeug)).includes('Back home'));
  const zi = kontext({ termine: [laufend({ ignored: true })], z: { f: formatierer('en', TZ) } });
  const text = String(fahrzeugHtml(zi, fahrzeug));
  assert.ok(text.includes('Restore') && text.includes('Ignored, not planned'));
});

test('C9R: das Diagramm schattiert einen ignorierten Termin nicht', () => {
  const z = (ignored) => kontext({ termine: [laufend({ ignored })] });
  const svg = (k) => String(planChartSvg({ schluessel: 'p0', fz: fahrzeug, name: 'x', fenster: k.fenster.get('dev-1'), termine: k.termine, bereich: 'alles' }, 600, false, k.f, 0).svg);
  assert.ok(svg(z(false)).includes('url(#weg-p0)"/>'));
  assert.ok(!svg(z(true)).includes('url(#weg-p0)"/>'));
});

test('C9R: eine veraltete Markierung an einem vergangenen Termin zeigt keine Ignoriert-Zeile', () => {
  const vorbei = termin({ entry: 'e8', date: '2026-09-16', departure: '2026-09-16T08:00:00+02:00', return: '2026-09-16T12:00:00+02:00', ignored: true });
  const text = String(fahrzeugHtml(kontext({ termine: [vorbei] }), fahrzeug));
  assert.ok(!text.includes('Ignoriert, wird nicht geplant'));
  assert.ok(!text.includes('data-aktion="ignorieren"'));
});

test('C13: ein verlaengerter laufender Termin sagt es in der Planzeile', () => {
  const p = { soc_at_departure: null, soc_after_trip: null, target_missing_kwh: null, below_min: false, running_until: '2026-09-16T17:30:00+02:00' };
  const text = String(fahrzeugHtml(kontext({ termine: [laufend({ extended: true, plan: p })] }), fahrzeug));
  assert.ok(text.includes('(verlängert)'));
  const en = String(fahrzeugHtml(kontext({ termine: [laufend({ extended: true, plan: p })], z: { f: formatierer('en', TZ) } }), fahrzeug));
  assert.ok(en.includes('(extended)'));
  const ohne = String(fahrzeugHtml(kontext({ termine: [laufend({ plan: p })] }), fahrzeug));
  assert.ok(!ohne.includes('(verlängert)'));
});
