// Zeit in der Zeitzone von Home Assistant, ohne DOM. Spec C8 Abschnitte 7.2 und 9.
//
// Das Panel rechnet mit Zeitpunkten in Millisekunden seit 1970. Die Wanduhr
// ist Datum und Uhrzeit in der Zeitzone von Home Assistant, nicht in der des
// Browsers: In ihr liest C3 die Eingaben. Eine lokale Zeit ohne Offset
// ('2026-09-21T08:00:00') gilt wie termine.lokal in C3 mit fold=0: Eine
// Uhrzeit, die es wegen der Umstellung nicht gibt, liegt eine Stunde spaeter,
// eine doppelte gilt beim ersten Mal.

export const MINUTE = 60 * 1000;
export const STUNDE = 60 * MINUTE;
export const TAG = 24 * STUNDE;

export const zwei = (n) => String(n).padStart(2, '0');

const FORMATE = new Map();
const WOCHENTAG = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

function format(tz) {
  let f = FORMATE.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hourCycle: 'h23',
      weekday: 'short',
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      second: 'numeric',
    });
    FORMATE.set(tz, f);
  }
  return f;
}

// Die Wanduhr zu einem Zeitpunkt. wochentag: 0 Sonntag bis 6 Samstag.
export function wanduhr(ms, tz) {
  const teile = {};
  for (const { type, value } of format(tz).formatToParts(new Date(ms))) teile[type] = value;
  return {
    jahr: Number(teile.year),
    monat: Number(teile.month),
    tag: Number(teile.day),
    stunde: Number(teile.hour),
    minute: Number(teile.minute),
    sekunde: Number(teile.second),
    wochentag: WOCHENTAG[teile.weekday],
  };
}

// Der Versatz der Zeitzone zu einem Zeitpunkt, in Millisekunden.
function versatz(ms, tz) {
  const w = wanduhr(ms, tz);
  return Date.UTC(w.jahr, w.monat - 1, w.tag, w.stunde, w.minute, w.sekunde) - Math.floor(ms / 1000) * 1000;
}

const NAIV = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?$/;

// Eine lokale Zeit ohne Offset als Zeitpunkt, oder null, wenn sie keine ist.
export function zuMs(text, tz) {
  const m = NAIV.exec(text || '');
  if (!m) return null;
  const wand = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
  const vorher = versatz(wand - TAG, tz);
  const nachher = versatz(wand + TAG, tz);
  const frueh = wand - vorher;
  if (vorher === nachher) return frueh;
  const spaet = wand - nachher;
  // fold=0: doppelt gilt das erste Mal, fehlend der Versatz davor, also eine Stunde spaeter.
  if (versatz(frueh, tz) === vorher || versatz(spaet, tz) !== nachher) return frueh;
  return spaet;
}

const datumText = (w) => `${w.jahr}-${zwei(w.monat)}-${zwei(w.tag)}`;

// Ein Zeitpunkt als lokale Zeit ohne Offset, auf die Minute.
export function naiv(ms, tz) {
  const w = wanduhr(ms, tz);
  return `${datumText(w)}T${zwei(w.stunde)}:${zwei(w.minute)}:00`;
}

// Das lokale Datum eines Zeitpunkts: '2026-09-21'.
export const datumVon = (ms, tz) => datumText(wanduhr(ms, tz));

// Der Beginn eines lokalen Tages.
export const tagesbeginn = (datum, tz) => zuMs(`${datum}T00:00`, tz);

const utcDatum = (datum) => {
  const [j, m, t] = datum.split('-').map(Number);
  return new Date(Date.UTC(j, m - 1, t));
};
const alsDatum = (d) => `${d.getUTCFullYear()}-${zwei(d.getUTCMonth() + 1)}-${zwei(d.getUTCDate())}`;

// Datum plus n Tage.
export function plusTage(datum, n) {
  const d = utcDatum(datum);
  d.setUTCDate(d.getUTCDate() + n);
  return alsDatum(d);
}

// 0 Sonntag bis 6 Samstag.
export const wochentag = (datum) => utcDatum(datum).getUTCDay();

// monat 1 bis 12.
export const tageImMonat = (jahr, monat) => new Date(Date.UTC(jahr, monat, 0)).getUTCDate();

// Ein Zeitpunkt aus C3, ISO 8601 mit Offset. Mehr als drei Nachkommastellen
// der Sekunde liest nicht jeder Browser.
export function ausIso(text) {
  if (!text) return null;
  const ms = Date.parse(String(text).replace(/(\.\d{3})\d+/, '$1'));
  return Number.isNaN(ms) ? null : ms;
}

// Ein Zeitpunkt fuer C3, ISO 8601 in UTC.
export const iso = (ms) => new Date(ms).toISOString();

// Die naechste volle Stunde als lokale Zeit ohne Offset.
export function naechsteVolleStunde(jetzt, tz) {
  const w = wanduhr(jetzt, tz);
  const d = new Date(Date.UTC(w.jahr, w.monat - 1, w.tag, w.stunde + 1));
  return `${alsDatum(d)}T${zwei(d.getUTCHours())}:00:00`;
}
