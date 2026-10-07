// Die Preise ab jetzt und je Tag, ohne DOM. Spec C8 Abschnitte 6.6 und 6.7.
//
// Die Preise aus meteo_volt/prices tragen kein Netzentgelt. Das Panel rechnet
// es selbst dazu: gebuehr ist 0 oder grid_fees in EUR je kWh.

import { MINUTE, ausIso, datumVon } from './zeit.js';

const SLOT = 15 * MINUTE;

// Die Slots ab dem laufenden. epex ist Boerse, alles andere Prognose; fehlt q10 oder q90, gilt q50.
export function preisSlots(preise, jetzt) {
  const roh = preise && Array.isArray(preise.slots) ? preise.slots : [];
  return roh
    .map((s) => ({
      t: ausIso(s.t),
      q50: s.q50,
      q10: s.q10 ?? s.q50,
      q90: s.q90 ?? s.q50,
      boerse: s.source === 'epex',
    }))
    .filter((s) => s.t !== null && Number.isFinite(s.q50))
    .map((s) => ({ ...s, ende: s.t + SLOT }))
    .filter((s) => s.ende > jetzt)
    .sort((a, b) => a.t - b.t);
}

// Je Tag in der Zeitzone von Home Assistant (Spec 6.6). stunden: Laenge des Zeitraums, 1 bis 4.
// { datum, von, bis, quelle: 'boerse' | 'prognose', fenster: { von, bis, mittel } | null,
//   tief, hoch, mittel, spanne } -- tief und hoch sind Slots, spanne ist null ohne Prognose.
export function tageswerte(slots, stunden, tz, gebuehr) {
  const tage = new Map();
  for (const s of slots) {
    const datum = datumVon(s.t, tz);
    if (!tage.has(datum)) tage.set(datum, []);
    tage.get(datum).push(s);
  }
  const k = stunden * 4;
  const preis = (s) => s.q50 + gebuehr;
  return [...tage].map(([datum, liste]) => {
    let fenster = null;
    for (let i = 0; i + k <= liste.length; i += 1) {
      if (liste[i + k - 1].t - liste[i].t !== (k - 1) * SLOT) continue;
      let summe = 0;
      for (let j = i; j < i + k; j += 1) summe += preis(liste[j]);
      const mittel = summe / k;
      if (!fenster || mittel < fenster.mittel - 1e-12) fenster = { von: liste[i].t, bis: liste[i + k - 1].ende, mittel };
    }
    const tief = liste.reduce((a, b) => (preis(b) < preis(a) ? b : a));
    const hoch = liste.reduce((a, b) => (preis(b) > preis(a) ? b : a));
    const prognose = liste.filter((s) => !s.boerse);
    return {
      datum,
      von: liste[0].t,
      bis: liste[liste.length - 1].ende,
      quelle: prognose.length ? 'prognose' : 'boerse',
      fenster,
      tief,
      hoch,
      mittel: liste.reduce((a, s) => a + preis(s), 0) / liste.length,
      spanne: prognose.length ? prognose.reduce((a, s) => a + (s.q90 - s.q10) / 2, 0) / prognose.length : null,
    };
  });
}
