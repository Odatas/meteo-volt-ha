// Was das Panel aus Plan und Terminen ableitet, ohne DOM. Spec C8 Abschnitte 6.2 bis 6.4.
//
// Quelle ist nur die zugesagte Oberflaeche aus C3-Spec Abschnitt 9: der Plan aus
// meteo_volt/plan, die Termine aus meteo_volt/appointments und die Form der IDs.

import { ausIso } from './zeit.js';

// Eine ID aus C3-Spec Abschnitt 4: <eintrag>/<JJJJ-MM-TT>/weg oder ziel. base und alles andere: null.
export function zerlegen(id) {
  if (typeof id !== 'string') return null;
  const teile = id.split('/');
  if (teile.length !== 3) return null;
  const [eintrag, datum, art] = teile;
  if (!eintrag || !/^\d{4}-\d{2}-\d{2}$/.test(datum) || (art !== 'weg' && art !== 'ziel')) return null;
  return { eintrag, datum, art };
}

// Die Termine aus C3 mit ihren Zeitpunkten, nach Abfahrt sortiert.
export function termineAus(liste) {
  return (Array.isArray(liste) ? liste : [])
    .map((t) => ({ ...t, abfahrt: ausIso(t.departure), rueckkehr: ausIso(t.return) }))
    .sort((a, b) => a.abfahrt - b.abfahrt);
}

export const laeuft = (termin, jetzt) => termin.abfahrt <= jetzt && jetzt < termin.rueckkehr;

// Der Plan ab dem laufenden Slot bis horizon_end, oder null ohne Plan (Spec 6.2).
// socJetzt: soc_pct aus site. Ein Slot endet, wo der naechste beginnt, der letzte mit horizon_end.
export function planAbJetzt(plan, jetzt, socJetzt) {
  const ende = ausIso(plan && plan.horizon_end);
  const roh = plan && Array.isArray(plan.slots) ? plan.slots : [];
  if (ende === null || ende <= jetzt || !roh.length) return null;
  const alle = roh.map((s) => ({
    t: ausIso(s.t),
    laden: Boolean(s.charge),
    preis: s.price,
    boerse: s.source === 'epex',
    soc: s.soc_end_pct,
    kw: s.kw ?? null,
    kwh: s.kwh ?? 0,
    kosten: s.cost_eur ?? 0,
    reason: s.reason ?? null,
  }));
  alle.forEach((s, i) => {
    s.ende = i + 1 < alle.length ? alle[i + 1].t : ende;
  });
  const erster = alle.findIndex((s) => s.ende > jetzt);
  if (erster < 0) return null;
  const slots = alle.slice(erster);
  const socStart = erster > 0 ? alle[erster - 1].soc : (socJetzt ?? slots[0].soc);
  return { slots, start: slots[0].t, ende, socStart };
}

// Die Ladebloecke, die nicht vor jetzt enden. Einer, der laeuft, zaehlt ganz (Spec 6.2).
export function bloeckeAbJetzt(plan, jetzt) {
  const roh = plan && Array.isArray(plan.intervals) ? plan.intervals : [];
  return roh
    .map((b) => ({
      von: ausIso(b.from),
      bis: ausIso(b.to),
      kwh: b.kwh,
      kosten: b.cost_eur,
      preis: b.avg_price_eur_kwh,
      socVon: b.soc_from_pct,
      socBis: b.soc_to_pct,
      reason: b.reason,
    }))
    .filter((b) => b.bis > jetzt)
    .sort((a, b) => a.von - b.von);
}

// Geplant und Kosten: die Summen der gezeigten Bloecke. gebuehr ist 0 oder grid_fees.
export function summen(bloecke, gebuehr) {
  return bloecke.reduce(
    (s, b) => ({ kwh: s.kwh + b.kwh, kosten: s.kosten + b.kosten + gebuehr * b.kwh }),
    { kwh: 0, kosten: 0 },
  );
}

// Der Grund eines Ladeblocks (Spec 6.3). termine: die geladenen Termine des Fahrzeugs, sortiert.
// { art: 'ziel', termin } | { art: 'vor', termin } | { art: 'ende' }
export function blockGrund(block, termine) {
  const id = zerlegen(block.reason);
  if (id && id.art === 'ziel') {
    const termin = termine.find((t) => t.entry === id.eintrag && t.date === id.datum);
    if (termin && termin.soc !== null && termin.soc !== undefined) return { art: 'ziel', termin };
  }
  const naechster = termine.find((t) => t.abfahrt >= block.bis);
  return naechster ? { art: 'vor', termin: naechster } : { art: 'ende' };
}

const gesetzt = (x) => x !== null && x !== undefined;

// Eine Warnung eines Termins ist target_missing_kwh oder below_min (Spec 6.4).
export const hatWarnung = (termin) => Boolean(termin.plan && (gesetzt(termin.plan.target_missing_kwh) || termin.plan.below_min));

// Die Planzeile eines Termins, oder null (Spec 6.4).
// { art: 'unterwegs', bis } | { art: 'warnungen', warnungen: [{ art: 'ziel', soc, kwh } | { art: 'min', soc }] }
// | { art: 'abfahrt', soc }
export function planzeile(termin) {
  const p = termin.plan;
  if (!p) return null;
  if (p.running_until) return { art: 'unterwegs', bis: ausIso(p.running_until) };
  const warnungen = [];
  if (gesetzt(p.target_missing_kwh)) warnungen.push({ art: 'ziel', soc: termin.soc, kwh: p.target_missing_kwh });
  if (p.below_min) warnungen.push({ art: 'min', soc: p.soc_after_trip });
  if (warnungen.length) return { art: 'warnungen', warnungen };
  if (gesetzt(p.soc_at_departure)) return { art: 'abfahrt', soc: p.soc_at_departure };
  return null;
}

// Der Status eines Fahrzeugs (Spec 6.3). plan aus meteo_volt/plan, termine des Fahrzeugs,
// mitPlan: planAbJetzt lieferte einen Plan.
// { unterwegsBis, laden: { art: 'jetzt', kw } | { art: 'ab', t } | { art: 'keins' } | { art: 'keinPlan' }, warnungen }
export function status(plan, termine, jetzt, mitPlan) {
  const laufend = termine.filter((t) => laeuft(t, jetzt));
  const unterwegsBis = laufend.length ? Math.max(...laufend.map((t) => t.rueckkehr)) : null;
  let laden;
  if (!mitPlan) laden = { art: 'keinPlan' };
  else if (plan.charge_now) laden = { art: 'jetzt', kw: plan.charge_now_kw ?? null };
  else if (plan.next_charge_start) laden = { art: 'ab', t: ausIso(plan.next_charge_start) };
  else laden = { art: 'keins' };
  return { unterwegsBis, laden, warnungen: termine.filter(hatWarnung).length };
}

// Wann der Plan da ist, fuer "Plan von ..." (Spec 6.1): received_at, nicht
// computed_at. Letzteres ist laut Basiskontrakt der Zeitpunkt der Prognose und
// steht nach einem "Neu planen" unveraendert da. Alle Plaene stammen aus
// derselben Antwort, darum der erste, der einen Wert traegt.
export function erhaltenUm(plaene) {
  for (const plan of plaene) {
    const da = ausIso(plan && plan.received_at);
    if (da !== null) return da;
  }
  return null;
}

// Das Planende aller Plaene, oder null: sie stammen aus derselben Antwort.
export function planende(plaene, jetzt) {
  for (const plan of plaene) {
    const ende = ausIso(plan && plan.horizon_end);
    if (ende !== null && ende > jetzt) return ende;
  }
  return null;
}
