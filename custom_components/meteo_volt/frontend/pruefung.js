// Die Pruefungen beim Eingeben, ohne DOM. Spec C8 Abschnitt 7.2.
//
// Dieselben Faelle, Schluessel und Texte wie C3-Spec 2.3, in derselben
// Reihenfolge. C3 prueft beim Speichern dasselbe noch einmal; was das Panel
// hier meldet, haelt nur das Formular auf.

import { ABSTAND_MIN, ausrollen, ueberschneiden } from './wiederholung.js';
import { MINUTE, TAG, ausIso, zuMs } from './zeit.js';

// Wo eine Meldung im Formular steht, je Schluessel.
export const ORT = {
  zeit_fehlt: 'rueckkehr',
  rueckkehr_vor_abfahrt: 'rueckkehr',
  rueckkehr_vorbei: 'rueckkehr',
  dauer_zu_lang: 'wiederholung',
  strecke_fehlt: 'strecke',
  strecke_negativ: 'strecke',
  ladestand_bereich: 'ladestand',
  ladestand_unter_min: 'ladestand',
  fahrer_doppelt: 'fahrer',
};

// Die Orte, an denen ein Fehler im Formular stehen kann. Die Warnungen stehen woanders.
export const FEHLERORTE = ['rueckkehr', 'wiederholung', 'strecke', 'ladestand'];

// Wo ein Fehler des Dienstes im Formular steht, oder null: dann als Meldung unten (Spec 7.3).
export const fehlerOrt = (key) => (FEHLERORTE.includes(ORT[key]) ? ORT[key] : null);

// So weit voraus prueft C3 den Fahrer.
export const FAHRER_VORAUS = 56 * TAG;

const zahlOderNull = (x) => (x === null || x === undefined || x === '' || !Number.isFinite(Number(x)) ? null : Number(x));

// f: { abfahrt, rueckkehr (lokal ohne Offset oder null), regel, km, soc }
// k: { jetzt, tz, socMin, versucht } -- versucht: einmal auf Speichern gedrueckt
// Liefert { meldungen: [{ key, ort, art, platzhalter }], ok, werte }. werte ist
// { abfahrt, dauerMin, regel }, wenn die Zeiten gelten, sonst null.
export function pruefen(f, k) {
  const meldungen = [];
  const melden = (key, art = 'fehler', platzhalter = {}) => meldungen.push({ key, ort: ORT[key], art, platzhalter });
  const abfahrt = zuMs(f.abfahrt, k.tz);
  const rueckkehr = zuMs(f.rueckkehr, k.tz);
  let werte = null;
  if (abfahrt === null || rueckkehr === null) {
    melden('zeit_fehlt');
  } else {
    const dauerMin = Math.floor((rueckkehr - abfahrt) / MINUTE);
    if (dauerMin <= 0) melden('rueckkehr_vor_abfahrt');
    else if (f.regel === 'once' && rueckkehr <= k.jetzt) melden('rueckkehr_vorbei');
    else if (f.regel !== 'once' && dauerMin >= ABSTAND_MIN[f.regel]) melden('dauer_zu_lang');
    else werte = { abfahrt: f.abfahrt, dauerMin, regel: f.regel };
  }
  const km = zahlOderNull(f.km);
  if (km === null) {
    if (k.versucht) melden('strecke_fehlt');
  } else if (km < 0) {
    melden('strecke_negativ');
  }
  const soc = zahlOderNull(f.soc);
  if (soc !== null) {
    if (soc < 0 || soc > 100) melden('ladestand_bereich');
    else if (soc < k.socMin) melden('ladestand_unter_min', 'warnung', { min: k.socMin });
  }
  const ok = km !== null && !meldungen.some((m) => m.art === 'fehler');
  return { meldungen, ok, werte };
}

// Der erste eigene Termin, dessen Fahrer zur selben Zeit mit einem anderen Fahrzeug
// unterwegs ist, oder null. werte aus pruefen; termine aus meteo_volt/appointments,
// ab jetzt acht Wochen; eintrag ist der bearbeitete Eintrag oder null.
// Liefert { eigen: { datum, abfahrt, rueckkehr }, anderer: <Termin aus C3> }.
export function fahrerKonflikt(werte, fahrer, fahrzeug, termine, eintrag, jetzt, tz) {
  if (!werte || !fahrer) return null;
  const andere = termine
    .filter((t) => t.driver === fahrer && t.vehicle !== fahrzeug && t.entry !== eintrag)
    .map((t) => ({ termin: t, abfahrt: ausIso(t.departure), rueckkehr: ausIso(t.return) }));
  for (const eigen of ausrollen(werte, tz, jetzt, jetzt + FAHRER_VORAUS)) {
    const treffer = andere.find((a) => ueberschneiden(eigen, a));
    if (treffer) return { eigen, anderer: treffer.termin };
  }
  return null;
}
