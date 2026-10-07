// Wiederholung und Ausrollen, ohne DOM. Spec C8 Abschnitte 6.4 und 7.2.
//
// Die Regeln sind die aus C3-Spec Abschnitt 2, wie termine.py sie rechnet.
// Das Panel rollt nur die Werte im Formular aus, fuer die Warnung zum Fahrer;
// alle gespeicherten Termine rollt C3 aus. tests/test_panel.py laesst
// termine.py und dieses Modul dieselben Faelle rechnen.

import { MINUTE, datumVon, plusTage, tageImMonat, wochentag, zuMs, zwei } from './zeit.js';

export const REGELN = ['once', 'daily', 'weekdays', 'weekly', 'monthly', 'yearly'];

// Der Abstand einer Serie in Minuten. Dauert ein Termin so lange oder laenger: dauer_zu_lang.
export const ABSTAND_MIN = { daily: 1440, weekdays: 1440, weekly: 7 * 1440, monthly: 28 * 1440, yearly: 365 * 1440 };

// Monatlich am n-ten Wochentag, n = ceil(Tag / 7). 5 heisst: am letzten.
export function monatsregel(datum) {
  return { n: Math.ceil(Number(datum.slice(8, 10)) / 7), wochentag: wochentag(datum) };
}

// Die Ordinalzahl in der Liste, wenn das Datum eines Termins sie eindeutig macht, sonst null.
// Vom 22. bis 28. entscheidet sonst der Beginn der Serie zwischen "vierten" und "letzten".
export function ordinalAusTermin(datum) {
  const tag = Number(datum.slice(8, 10));
  if (tag <= 21) return Math.ceil(tag / 7);
  if (tag >= 29) return 5;
  return tag + 7 > tageImMonat(Number(datum.slice(0, 4)), Number(datum.slice(5, 7))) ? null : 4;
}

function nterWochentag(jahr, monat, wt, n) {
  const vorn = `${jahr}-${zwei(monat)}-`;
  if (n >= 5) {
    const letzter = tageImMonat(jahr, monat);
    return vorn + zwei(letzter - ((wochentag(vorn + zwei(letzter)) - wt + 7) % 7));
  }
  return vorn + zwei(1 + ((wt - wochentag(`${vorn}01`) + 7) % 7) + 7 * (n - 1));
}

// Die Daten der regulaeren Termine von ab bis bis, beide eingeschlossen. Wie termine.regeldaten.
export function regeldaten(start, regel, ab, bis) {
  const aus = [];
  if (regel === 'once') {
    if (ab <= start && start <= bis) aus.push(start);
    return aus;
  }
  let tag = start > ab ? start : ab;
  if (regel === 'daily' || regel === 'weekdays') {
    for (; tag <= bis; tag = plusTage(tag, 1)) {
      const wt = wochentag(tag);
      if (regel === 'daily' || (wt >= 1 && wt <= 5)) aus.push(tag);
    }
  } else if (regel === 'weekly') {
    for (tag = plusTage(tag, (wochentag(start) - wochentag(tag) + 7) % 7); tag <= bis; tag = plusTage(tag, 7)) {
      aus.push(tag);
    }
  } else if (regel === 'monthly') {
    const { n, wochentag: wt } = monatsregel(start);
    let jahr = Number(tag.slice(0, 4));
    let monat = Number(tag.slice(5, 7));
    for (;;) {
      const kandidat = nterWochentag(jahr, monat, wt, n);
      if (kandidat > bis) break;
      if (kandidat >= tag) aus.push(kandidat);
      if (monat === 12) {
        jahr += 1;
        monat = 1;
      } else {
        monat += 1;
      }
    }
  } else if (regel === 'yearly') {
    const monatTag = start.slice(5);
    for (let jahr = Number(tag.slice(0, 4)); jahr <= Number(bis.slice(0, 4)); jahr += 1) {
      if (monatTag === '02-29' && tageImMonat(jahr, 2) < 29) continue;
      const kandidat = `${jahr}-${monatTag}`;
      if (tag <= kandidat && kandidat <= bis) aus.push(kandidat);
    }
  } else {
    throw new Error(`unbekannte Wiederholung: ${regel}`);
  }
  return aus;
}

// Die Termine der Werte { abfahrt, dauerMin, regel }, deren Rueckkehr nach von und deren
// Abfahrt vor bis liegt. abfahrt ist lokal ohne Offset. Wie termine.termine_von, ohne Ausnahmen.
export function ausrollen(werte, tz, von, bis) {
  const start = werte.abfahrt.slice(0, 10);
  const uhrzeit = werte.abfahrt.slice(10);
  const ab = plusTage(datumVon(von, tz), -(Math.floor(werte.dauerMin / 1440) + 1));
  const liste = [];
  for (const datum of regeldaten(start, werte.regel, ab, datumVon(bis, tz))) {
    const abfahrt = zuMs(datum + uhrzeit, tz);
    const rueckkehr = abfahrt + werte.dauerMin * MINUTE;
    if (rueckkehr > von && abfahrt < bis) liste.push({ datum, abfahrt, rueckkehr });
  }
  return liste;
}

// Zwei Termine liegen zur selben Zeit. Halboffen: Rueckkehr gleich Abfahrt nicht.
export const ueberschneiden = (a, b) => a.abfahrt < b.rueckkehr && b.abfahrt < a.rueckkehr;
