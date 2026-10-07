// Zahlen, Zeiten und Wiederholungen als Text, ohne DOM. Spec C8 Abschnitt 9.
//
// Uhrzeiten mit 24 Stunden in beiden Sprachen, in der Zeitzone von Home
// Assistant. Das Datum wie die Platzhalter aus C3: 'Mi 16.09.' und 'Wed 16 Sep'.

import { WOERTER, text } from './texte.js';
import { monatsregel, ordinalAusTermin } from './wiederholung.js';
import { datumVon, plusTage, wanduhr, wochentag, zwei } from './zeit.js';

export function formatierer(sp, tz) {
  const w = WOERTER[sp];
  const t = (schluessel, platzhalter) => text(sp, schluessel, platzhalter);
  const komma = (s) => (sp === 'de' ? s.replace('.', ',') : s);
  const zahl = (x, stellen) => komma(Number(x).toFixed(stellen));
  // Wie zahl_text in C3: 15 -> '15', 15.5 -> '15,5'
  const zahlKurz = (x) => komma(String(Number(Number(x).toPrecision(6))));
  const zehntel = (x) => komma(String(Math.round(Number(x) * 10) / 10));

  const zeit = (ms) => {
    const u = wanduhr(ms, tz);
    return `${zwei(u.stunde)}:${zwei(u.minute)}`;
  };
  const tagMonat = (datum) => (sp === 'de'
    ? `${datum.slice(8, 10)}.${datum.slice(5, 7)}.`
    : `${Number(datum.slice(8, 10))} ${w.monateKurz[Number(datum.slice(5, 7)) - 1]}`);
  const tagAusDatum = (datum) => `${w.wochentageKurz[wochentag(datum)]} ${tagMonat(datum)}`;
  const jahrestag = (datum) => (sp === 'de'
    ? `${Number(datum.slice(8, 10))}. ${w.monate[Number(datum.slice(5, 7)) - 1]}`
    : `${Number(datum.slice(8, 10))} ${w.monate[Number(datum.slice(5, 7)) - 1]}`);

  return {
    sp,
    tz,
    t,
    zahl,
    zahlKurz,
    zeit,
    tagAusDatum,
    // 'Mi 16.09.'
    tag: (ms) => tagAusDatum(datumVon(ms, tz)),
    // 'Mi 16.09. 14:30'
    tagZeit: (ms) => `${tagAusDatum(datumVon(ms, tz))} ${zeit(ms)}`,
    // 'Sa 10:00'
    wochentagZeit: (ms) => `${w.wochentageKurz[wochentag(datumVon(ms, tz))]} ${zeit(ms)}`,
    // 'Heute, Mi 16.09.', 'Morgen, Do 17.09.', 'Freitag, 18.09.'
    tagKopf: (datum, jetzt) => {
      const heute = datumVon(jetzt, tz);
      if (datum === heute) return t('kopf_heute', { tag: tagAusDatum(datum) });
      if (datum === plusTage(heute, 1)) return t('kopf_morgen', { tag: tagAusDatum(datum) });
      return `${w.wochentage[wochentag(datum)]}, ${tagMonat(datum)}`;
    },
    // '17:30', 'morgen 17:30', 'Fr 17:30'
    zeitMitTag: (ms, jetzt) => {
      const datum = datumVon(ms, tz);
      const heute = datumVon(jetzt, tz);
      if (datum === heute) return zeit(ms);
      if (datum === plusTage(heute, 1)) return t('morgen_zeit', { zeit: zeit(ms) });
      return `${w.wochentageKurz[wochentag(datum)]} ${zeit(ms)}`;
    },
    prozent: (x) => `${Math.round(x)} %`,
    kwh: (x) => `${zahl(x, 1)} kWh`,
    kw: (x) => `${zehntel(x)} kW`,
    ct: (eurKwh) => `${zahl(eurKwh * 100, 1)} ct/kWh`,
    ctKurz: (eurKwh) => `${zahl(eurKwh * 100, 1)} ct`,
    eur: (x) => (sp === 'de'
      ? t('eur_betrag', { betrag: zahl(x, 2) })
      : `${x < 0 ? '-' : ''}${t('eur_betrag', { betrag: zahl(Math.abs(x), 2) })}`),
    // Im Formular: 'Woechentlich am Mittwoch', 'Monatlich am dritten Mittwoch'
    regelLang: (regel, datum) => {
      const wt = w.wochentage[wochentag(datum)];
      if (regel === 'weekly') return t('regel_weekly', { wochentag: wt });
      if (regel === 'monthly') return t('regel_monthly', { ordinal: w.ordinal[monatsregel(datum).n - 1], wochentag: wt });
      if (regel === 'yearly') return t('regel_yearly', { datum: jahrestag(datum) });
      return t(`regel_${regel}`);
    },
    // In der Liste, aus dem Datum eines Termins: 'Mo-Fr', 'Jeden Mittwoch', 'Monatlich'
    regelKurz: (regel, datum) => {
      const wt = w.wochentage[wochentag(datum)];
      if (regel === 'once') return '';
      if (regel === 'weekdays') return t('regel_weekdays_kurz');
      if (regel === 'weekly') return t('regel_weekly_kurz', { wochentag: wt });
      if (regel === 'monthly') {
        const n = ordinalAusTermin(datum);
        return n === null ? t('regel_monthly_kurz') : t('regel_monthly', { ordinal: w.ordinal[n - 1], wochentag: wt });
      }
      if (regel === 'yearly') return t('regel_yearly', { datum: jahrestag(datum) });
      return t(`regel_${regel}`);
    },
  };
}
