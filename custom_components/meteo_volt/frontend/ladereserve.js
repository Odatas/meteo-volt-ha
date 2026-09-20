// Der gesicherte Ladestand eines Termins. Spec C10 Abschnitte 2 und 5.
//
// Dieselbe Rechnung wie ladereserve.py im Backend, Zeile fuer Zeile. Die
// Gegenprobe in tests/test_panel.py faehrt beide ueber dieselben Faelle und
// vergleicht: zwei Implementierungen derselben Formel driften sonst
// auseinander, ohne dass eine Pruefung rot wird.
//
// v ist ein Fahrzeug aus meteo_volt/site: soc_min_pct, capacity_kwh,
// consumption_kwh_per_100km.

export const FAHRT_ZU_WEIT = 'fahrt_zu_weit';
export const FAHRT_UNTER_MIN = 'fahrt_unter_min';
export const LADESTAND_OFFEN = 'ladestand_offen';

// Was eine Fahrt an Ladestand kostet, in Prozentpunkten. Ohne Wirkungsgrad:
// der gilt beim Laden, nicht beim Fahren.
export const fahrtPct = (km, v) => (km * v.consumption_kwh_per_100km) / v.capacity_kwh;

// Min-SoC plus Fahrt, aufgerundet auf ganze Prozent und bei 100 gedeckelt.
// Nicht bei soc_max_pct: ein Ziel wird nie gekappt (Basiskontrakt 3.3).
export const gesichert = (km, v) => Math.min(100, Math.ceil(v.soc_min_pct + fahrtPct(km, v)));

// Der Schluessel der Warnung zur Fahrt, oder null. soc ist das eigene Ziel
// oder null, sichern der Haken. soc_max_pct ist KEIN Bezugswert: dass der
// Planer heute vor der ersten Fahrt dorthin laedt, faellt mit A6E weg.
export function befund(km, soc, sichern, v) {
  const fahrt = fahrtPct(km, v);
  if (fahrt > 100 - v.soc_min_pct) return FAHRT_ZU_WEIT;
  let bezug;
  if (sichern) bezug = gesichert(km, v);
  else if (soc !== null && soc !== undefined && soc >= v.soc_min_pct) bezug = soc;
  else return LADESTAND_OFFEN;
  return bezug - fahrt < v.soc_min_pct ? FAHRT_UNTER_MIN : null;
}

// Die Platzhalter der Hinweiszeile unter dem Haken, oder null: ohne brauchbare
// Strecke gibt es nichts zu rechnen, und die Zeile bleibt weg.
// Spec C10 Abschnitt 5. Nur fuers Panel -- das Backend zeigt keine Zeile.
//
// voll: die Fahrt liegt ueber der Reichweite, derselbe Fall wie fahrt_zu_weit.
// Die Zeile sagt dann nur, dass voll geladen wird -- Min-SoC plus Fahrt ergaebe
// eine Summe weit ueber dem Deckel, den ziel nennt.
export function hinweis(km, v) {
  if (km === null || !Number.isFinite(km) || km < 0) return null;
  const fahrt = fahrtPct(km, v);
  return {
    ziel: gesichert(km, v), min: v.soc_min_pct, fahrt: Math.round(fahrt), km: Math.round(km),
    voll: fahrt > 100 - v.soc_min_pct,
  };
}
