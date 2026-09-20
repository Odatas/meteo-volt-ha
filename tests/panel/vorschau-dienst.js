// Ein nachgebautes C3 fuer die Vorschau. Geht nicht an Nutzer. Spec C8 Abschnitt 11.
//
// Antwortet auf die Websocket-Befehle und Actions aus C3-Spec Abschnitte 5 und 6
// in deren Form, mit Beispieldaten relativ zu jetzt. Die Planwerte sind grob
// simuliert wie im Entwurf, nicht vom Planer. Serien, Absagen und Rueckgaengig
// folgen C3-Spec 2.1 und 2.2 vereinfacht: genug, um jeden Klickweg zu sehen.

import { pruefen } from '../../custom_components/meteo_volt/frontend/pruefung.js';
import { regeldaten } from '../../custom_components/meteo_volt/frontend/wiederholung.js';
import {
  MINUTE, STUNDE, TAG, ausIso, datumVon, iso, naiv, plusTage, tagesbeginn, zuMs,
} from '../../custom_components/meteo_volt/frontend/zeit.js';

const TZ = 'Europe/Berlin';
const SLOT = 15 * MINUTE;
const warte = (ms) => new Promise((ok) => setTimeout(ok, ms));
const kopie = (x) => JSON.parse(JSON.stringify(x));

const FAHRZEUGE = [
  { id: 'buzz', geraet: 'dev-buzz', title: 'ID. Buzz', kapazitaet: 77, kw: 11, eta: 0.92, verbrauch: 21, min: 15, max: 80, soc: 62 },
  { id: 'zoe', geraet: 'dev-zoe', title: 'Zoe', kapazitaet: 52, kw: 3.7, eta: 0.9, verbrauch: 17, min: 20, max: 90, soc: 48 },
];
const PERSONEN = [{ entity_id: 'person.anna', name: 'Anna' }, { entity_id: 'person.patrick', name: 'Patrick' }];

export function dienst(optionen = {}) {
  const jetzt0 = Date.now();
  const heute = datumVon(jetzt0, TZ);
  const tag = (n, uhrzeit) => `${plusTage(heute, n)}T${uhrzeit}:00`;
  const fahrzeuge = optionen.ohneFahrzeug ? [] : FAHRZEUGE;
  let risiko = 2;
  let naechsteId = 10;
  let schrittNr = 1;
  const schritte = new Map();
  let planung = false;
  let berechnet = jetzt0 - 3 * MINUTE;
  const abos = new Set();

  // Wie der Store aus C3-Spec Abschnitt 3.
  let eintraege = optionen.ohneFahrzeug ? [] : [
    { id: 'e1', vehicle: 'buzz', departure: tag(-9, '07:30'), duration_min: 600, repeat: 'weekdays', distance_km: 45,
      driver: 'person.patrick', soc: null, until: null,
      exceptions: { [plusTage(heute, 2)]: { departure: tag(2, '07:30'), duration_min: 690, distance_km: 120, driver: 'person.patrick', soc: null }, [plusTage(heute, 6)]: null } },
    { id: 'e2', vehicle: 'buzz', departure: tag(3, '10:00'), duration_min: 34 * 60, repeat: 'once', distance_km: 320,
      driver: 'person.anna', soc: 100, until: null, exceptions: {} },
    { id: 'e3', vehicle: 'zoe', departure: tag(0, '19:00'), duration_min: 270, repeat: 'once', distance_km: 90,
      driver: 'person.anna', soc: 100, until: null, exceptions: {} },
    { id: 'e4', vehicle: 'zoe', departure: tag(-8, '18:30'), duration_min: 150, repeat: 'weekly', distance_km: 25,
      driver: 'person.anna', soc: null, until: null, exceptions: {} },
    { id: 'e5', vehicle: 'zoe', departure: tag(3, '09:00'), duration_min: 180, repeat: 'once', distance_km: 30,
      driver: 'person.anna', soc: null, until: null, exceptions: {} },
  ];

  const fz = (id) => fahrzeuge.find((f) => f.id === id);
  const fzGeraet = (geraet) => fahrzeuge.find((f) => f.geraet === geraet);

  // --- Ausrollen wie termine.py -----------------------------------------------------

  function vorkommen(von, bis, filter = () => true) {
    const liste = [];
    for (const e of eintraege) {
      if (!filter(e)) continue;
      const start = e.departure.slice(0, 10);
      let ende = datumVon(bis, TZ);
      if (e.until && plusTage(e.until, -1) < ende) ende = plusTage(e.until, -1);
      const daten = new Set(regeldaten(start, e.repeat, plusTage(datumVon(von, TZ), -3), ende));
      for (const [datum, werte] of Object.entries(e.exceptions)) if (werte) daten.add(datum);
      for (const datum of [...daten].sort()) {
        const ausnahme = e.exceptions[datum];
        if (ausnahme === null) continue;
        if (!regeldaten(start, e.repeat, datum, datum).length && !ausnahme) continue;
        const w = ausnahme || { departure: datum + e.departure.slice(10), duration_min: e.duration_min, distance_km: e.distance_km, driver: e.driver, soc: e.soc };
        const abfahrt = zuMs(w.departure, TZ);
        const rueckkehr = abfahrt + w.duration_min * MINUTE;
        if (rueckkehr <= von || abfahrt >= bis) continue;
        liste.push({ e, datum, abfahrt, rueckkehr, km: w.distance_km, driver: w.driver, soc: w.soc, changed: Boolean(ausnahme) });
      }
    }
    return liste.sort((a, b) => a.abfahrt - b.abfahrt);
  }
  const ueber = (a, b) => a.abfahrt < b.rueckkehr && b.abfahrt < a.rueckkehr;

  // --- Preise und eine grobe Plansimulation wie im Entwurf ----------------------------------

  const start0 = Math.floor(jetzt0 / SLOT) * SLOT;
  const horizontEnde = start0 + 7 * TAG;
  const bekanntBis = tagesbeginn(plusTage(heute, 2), TZ) - SLOT;
  const preise = (() => {
    let s = 42;
    const zufall = () => {
      s = (s * 16807) % 2147483647;
      return (s - 1) / 2147483646;
    };
    const niveau = [0.105, 0.09, 0.125, 0.115, 0.075, 0.06, 0.1, 0.12];
    const liste = [];
    for (let t = start0; t < horizontEnde; t += SLOT) {
      const n = Math.round((tagesbeginn(datumVon(t, TZ), TZ) - tagesbeginn(heute, TZ)) / TAG);
      const uhr = zuMs(naiv(t, TZ), TZ);
      const h = (uhr - tagesbeginn(datumVon(t, TZ), TZ)) / STUNDE;
      const welle = 0.07 * Math.exp(-((h - 7.5) ** 2) / 3) + 0.1 * Math.exp(-((h - 19) ** 2) / 4)
        - 0.06 * Math.exp(-((h - 13) ** 2) / 6) - 0.035 * Math.exp(-((h - 3) ** 2) / 5);
      const bekannt = t <= bekanntBis;
      const q50 = Math.max(-0.005, (niveau[n] ?? 0.11) + welle + (zufall() - 0.5) * (bekannt ? 0.008 : 0.003));
      const breite = bekannt ? 0 : q50 * (0.1 + 0.3 * Math.min(1, (t - bekanntBis) / TAG / 6));
      liste.push({ t, q10: q50 - breite * 0.8, q50, q90: q50 + breite, source: bekannt ? 'epex' : 'forecast' });
    }
    return liste;
  })();
  const preisMitRisiko = (p) => p[['q10', 'q50', 'q90'][risiko - 1]];

  function simuliere(f) {
    const eigene = vorkommen(start0, horizontEnde, (e) => e.vehicle === f.id);
    const rate = (f.kw * f.eta) / f.kapazitaet * 100 / 4;
    const slots = preise.map((p) => ({ t: p.t, preis: preisMitRisiko(p), source: p.source, weg: false, verbrauch: 0, menge: 0, soc: 0, grund: null }));
    const n = slots.length;
    const index = (t) => Math.max(0, Math.min(n - 1, Math.floor((t - start0) / SLOT)));
    const abfahrten = [];
    for (const v of eigene) {
      const bis = Math.min(n, Math.ceil((v.rueckkehr - start0) / SLOT));
      for (let i = v.abfahrt <= start0 ? 0 : index(v.abfahrt); i < bis; i += 1) slots[i].weg = true;
      if (v.abfahrt <= jetzt0) continue;
      const i = index(v.abfahrt);
      slots[i].verbrauch += (v.km * f.verbrauch) / 100 / f.kapazitaet * 100;
      abfahrten.push({ v, i });
    }
    const decke = slots.map(() => f.max);
    for (const { v, i } of abfahrten) {
      if (v.soc === null || v.soc <= f.max) continue;
      for (let j = i - 1; j >= 0 && !slots[j].weg; j -= 1) decke[j] = Math.max(decke[j], v.soc);
    }
    const verlauf = () => {
      let s = f.soc;
      for (const sl of slots) {
        s += sl.menge - sl.verbrauch;
        sl.soc = s;
      }
    };
    const luftAb = () => {
      const l = new Array(n + 1).fill(Infinity);
      for (let i = n - 1; i >= 0; i -= 1) l[i] = Math.min(l[i + 1], decke[i] - slots[i].soc);
      return l;
    };
    const laden = (bisIndex, bedarf, grund) => {
      const kandidaten = [];
      for (let j = 0; j < bisIndex; j += 1) if (!slots[j].weg && slots[j].menge < rate - 1e-9) kandidaten.push(j);
      kandidaten.sort((a, b) => slots[a].preis - slots[b].preis || b - a);
      let luft = luftAb();
      for (const j of kandidaten) {
        if (bedarf <= 1e-6) break;
        const x = Math.min(rate - slots[j].menge, bedarf, luft[j]);
        if (x <= 1e-6) continue;
        slots[j].menge += x;
        if (!slots[j].grund) slots[j].grund = grund;
        for (let i = j; i < n; i += 1) slots[i].soc += x;
        bedarf -= x;
        luft = luftAb();
      }
    };
    verlauf();
    for (const { v, i } of abfahrten) {
      const vorher = i > 0 ? slots[i - 1].soc : f.soc;
      const ziel = v.soc !== null && v.soc >= f.min ? v.soc : null;
      const bedarf = Math.min(100, Math.max(ziel ?? 0, f.min + slots[i].verbrauch)) - vorher;
      if (bedarf > 1e-6) laden(i, bedarf, ziel !== null ? `${v.e.id}/${v.datum}/ziel` : 'base');
    }
    if (slots[n - 1].soc < f.max) laden(n, f.max - slots[n - 1].soc, 'base');
    const verletzungen = [];
    for (const { v, i } of abfahrten) {
      const vorher = i > 0 ? slots[i - 1].soc : f.soc;
      if (v.soc !== null && v.soc >= f.min && vorher < v.soc - 0.05) {
        verletzungen.push({ type: 'target_unreachable', constraint_id: `${v.e.id}/${v.datum}/ziel`,
          missing_kwh: Math.round(((v.soc - vorher) / 100) * f.kapazitaet / f.eta * 10) / 10, message: 'Ziel nicht erreichbar' });
      }
    }
    const aus = slots.map((sl) => {
      const slot = { t: iso(sl.t), charge: sl.menge > 1e-9, price: sl.preis, source: sl.source, soc_end_pct: Math.round(sl.soc * 10) / 10 };
      if (slot.charge) {
        const kwh = (sl.menge / 100) * f.kapazitaet / f.eta;
        Object.assign(slot, { station_id: 'wb', kw: Math.round(kwh * 4 * 10) / 10, kwh, kwh_battery: kwh * f.eta, cost_eur: kwh * sl.preis, reason: sl.grund });
      }
      return slot;
    });
    const intervals = [];
    aus.forEach((slot, i) => {
      if (!slot.charge) return;
      const letzter = intervals[intervals.length - 1];
      const bis = iso(slots[i].t + SLOT);
      if (letzter && letzter.to === slot.t) {
        Object.assign(letzter, { to: bis, kwh: letzter.kwh + slot.kwh, cost_eur: letzter.cost_eur + slot.cost_eur, soc_to_pct: slot.soc_end_pct });
        letzter.avg_price_eur_kwh = letzter.cost_eur / letzter.kwh;
      } else {
        intervals.push({ station_id: 'wb', from: slot.t, to: bis, kwh: slot.kwh, cost_eur: slot.cost_eur, avg_price_eur_kwh: slot.price,
          soc_from_pct: i > 0 ? aus[i - 1].soc_end_pct : f.soc, soc_to_pct: slot.soc_end_pct, reason: slot.reason });
      }
    });
    const jetzt = Date.now();
    const lauf = aus.findIndex((s) => ausIso(s.t) + SLOT > jetzt);
    const naechster = aus.findIndex((s, i) => i > lauf && s.charge && !aus[i - 1].charge);
    return {
      slots: aus, intervals, total_kwh: intervals.reduce((a, b) => a + b.kwh, 0), total_cost_eur: intervals.reduce((a, b) => a + b.cost_eur, 0),
      soc_end_pct: aus[n - 1].soc_end_pct, violations: verletzungen,
      horizon_end: iso(horizontEnde), prices_known_until: iso(bekanntBis), computed_at: iso(berechnet), received_at: iso(berechnet + 2000),
      charge_now: lauf >= 0 && aus[lauf].charge, charge_now_kw: lauf >= 0 && aus[lauf].charge ? aus[lauf].kw : 0,
      next_charge_start: naechster >= 0 ? aus[naechster].t : null,
      planning: planung, error: optionen.planFehler ? 'PlanNichtVerfuegbar: Der Plan-Dienst antwortet nicht (503)' : null,
    };
  }

  let plaene = new Map();
  const neuRechnen = () => {
    plaene = new Map(fahrzeuge.map((f) => [f.id, simuliere(f)]));
  };
  neuRechnen();

  // --- Lesen, C3-Spec Abschnitt 6 --------------------------------------------------------

  function planwerte(v, jetzt) {
    const plan = plaene.get(v.e.vehicle);
    if (!plan || v.abfahrt >= horizontEnde) return null;
    const f = fz(v.e.vehicle);
    const i = plan.slots.findIndex((s) => ausIso(s.t) <= v.abfahrt && v.abfahrt < ausIso(s.t) + SLOT);
    const nach = i >= 0 ? plan.slots[i].soc_end_pct : null;
    const bei = i > 0 ? plan.slots[i - 1].soc_end_pct : i === 0 ? f.soc : null;
    const fehlt = plan.violations.find((x) => x.constraint_id === `${v.e.id}/${v.datum}/ziel`);
    const laeuft = v.abfahrt <= jetzt && jetzt < v.rueckkehr;
    return {
      soc_at_departure: laeuft ? null : bei, soc_after_trip: laeuft ? null : nach, target_missing_kwh: fehlt ? fehlt.missing_kwh : null,
      below_min: !laeuft && nach !== null && nach < f.min, running_until: laeuft ? iso(v.rueckkehr) : null,
    };
  }

  function termineAntwort(start, ende, geraet) {
    const jetzt = Date.now();
    const filter = geraet ? (e) => fz(e.vehicle).geraet === geraet : () => true;
    const auswahl = vorkommen(start, ende, filter);
    const umfeld = auswahl.length ? vorkommen(auswahl[0].abfahrt - 3 * TAG, auswahl[auswahl.length - 1].rueckkehr + 3 * TAG) : [];
    return auswahl.map((v) => {
      const hints = [];
      if (umfeld.some((o) => o.e.vehicle === v.e.vehicle && (o.e !== v.e || o.datum !== v.datum) && ueber(o, v))) hints.push({ type: 'overlap' });
      const belegt = new Set();
      for (const o of umfeld) {
        if (o.e.vehicle !== v.e.vehicle && v.driver && o.driver === v.driver && ueber(o, v)) belegt.add(fz(o.e.vehicle).geraet);
      }
      belegt.forEach((g) => hints.push({ type: 'driver_busy', vehicle: g }));
      return {
        entry: v.e.id, date: v.datum, vehicle: fz(v.e.vehicle).geraet, departure: iso(v.abfahrt), return: iso(v.rueckkehr),
        distance_km: v.km, driver: v.driver, soc: v.soc, repeat: v.e.repeat, changed: v.changed, plan: planwerte(v, jetzt), hints,
      };
    });
  }

  // --- Schreiben, C3-Spec Abschnitt 5, vereinfacht ------------------------------------------------

  const fehler = (key, placeholders = {}) => Object.assign(new Error(key), {
    code: 'service_validation_error', message: `Validation error: ${key}`, translation_domain: 'meteo_volt', translation_key: key, translation_placeholders: placeholders,
  });
  const merken = (davor = null) => {
    const id = `s${schrittNr += 1}`;
    schritte.set(id, davor || kopie(eintraege));
    return id;
  };
  const werteAus = (d, vorgabe) => {
    const f = fzGeraet(d.vehicle);
    if (!f) throw fehler('fahrzeug_unbekannt');
    const regel = d.repeat || vorgabe;
    const e = pruefen({ abfahrt: d.departure, rueckkehr: d.return, regel, km: d.distance_km, soc: d.soc },
      { jetzt: Date.now(), tz: TZ, socMin: f.min, versucht: true });
    const erster = e.meldungen.find((m) => m.art === 'fehler');
    if (erster) throw fehler(erster.key);
    return { vehicle: f.id, departure: d.departure, duration_min: e.werte.dauerMin, repeat: regel, distance_km: Math.floor(Number(d.distance_km) + 0.5),
      driver: d.driver || null, soc: d.soc ?? null };
  };
  const neu = (w) => {
    const e = { id: `e${naechsteId += 1}`, ...w, until: null, exceptions: {} };
    eintraege.push(e);
    return e;
  };

  function anlegen(d) {
    const w = werteAus(d, 'once');
    const step = merken();
    return { step, entry: neu(w).id, warnings: [] };
  }

  function aendern(d) {
    const e = eintraege.find((x) => x.id === d.entry);
    if (!e) throw fehler('eintrag_unbekannt');
    const w = werteAus(d, e.repeat);
    const step = merken();
    const umfang = e.repeat === 'once' ? 'all' : d.scope || 'this';
    if (umfang === 'this') {
      if (w.repeat !== e.repeat) throw fehler('umfang_unzulaessig');
      if (w.vehicle !== e.vehicle) {
        e.exceptions[d.date] = null;
        return { step, entries: [neu({ ...w, repeat: 'once' }).id, e.id], warnings: [] };
      }
      e.exceptions[d.date] = { departure: w.departure, duration_min: w.duration_min, distance_km: w.distance_km, driver: w.driver, soc: w.soc };
      return { step, entries: [e.id], warnings: [] };
    }
    const erster = d.date <= e.departure.slice(0, 10);
    if (umfang === 'following' && !erster) {
      e.until = d.date;
      return { step, entries: [neu(w).id, e.id], warnings: [] };
    }
    const verschoben = Math.round((tagesbeginn(w.departure.slice(0, 10), TZ) - tagesbeginn(d.date, TZ)) / TAG);
    const tagNeu = verschoben !== 0 || w.repeat !== e.repeat;
    Object.assign(e, w, { departure: plusTage(e.departure.slice(0, 10), verschoben) + w.departure.slice(10) });
    if (tagNeu) e.exceptions = {};
    return { step, entries: [e.id], warnings: [] };
  }

  function loeschen(d) {
    const e = eintraege.find((x) => x.id === d.entry);
    if (!e) throw fehler('eintrag_unbekannt');
    const step = merken();
    const umfang = e.repeat === 'once' ? 'all' : d.scope || 'this';
    if (umfang === 'this') e.exceptions[d.date] = null;
    else if (umfang === 'following' && d.date > e.departure.slice(0, 10)) e.until = d.date;
    else eintraege = eintraege.filter((x) => x !== e);
    return { step };
  }

  function absagen(d) {
    if (!d.appointments || !d.appointments.length) throw fehler('eintrag_unbekannt');
    const step = merken(d.step && schritte.has(d.step) ? schritte.get(d.step) : null);
    for (const { entry, date } of d.appointments) {
      const e = eintraege.find((x) => x.id === entry);
      if (!e) continue;
      if (e.repeat === 'once') eintraege = eintraege.filter((x) => x !== e);
      else e.exceptions[date] = null;
    }
    return { step };
  }

  function rueckgaengig(d) {
    if (!schritte.has(d.step)) throw fehler('rueckgaengig_unmoeglich');
    eintraege = schritte.get(d.step);
    schritte.delete(d.step);
  }

  // --- Meldungen und Neu planen -----------------------------------------------------------

  const melden = (was) => setTimeout(() => abos.forEach((ruf) => ruf(was)), 40);
  let planUhr = null;
  async function planen() {
    planung = true;
    melden('planning');
    await warte(1200);
    berechnet = Date.now();
    planung = false;
    neuRechnen();
    melden('planning');
    melden('plan');
  }
  const baldPlanen = () => {
    clearTimeout(planUhr);
    planUhr = setTimeout(planen, 300);
  };
  let letzterPlan = 0;

  // --- Die Verbindung, wie hass.connection sie anbietet ------------------------------------

  const site = () => ({
    risk: risiko,
    grid_fees: optionen.ohneNetzentgelt ? null : 0.16,
    vehicles: fahrzeuge.map((f) => ({ vehicle: f.geraet, title: f.title, soc_min_pct: f.min, soc_max_pct: f.max, max_charge_kw: f.kw, soc_pct: f.soc })),
    persons: PERSONEN,
  });

  async function nachricht(msg) {
    await warte(60);
    if (optionen.nichtGeladen) throw { code: 'not_found', message: 'Kein Meteo-Volt-Standort mit Terminen' };
    if (msg.type === 'meteo_volt/site') return site();
    if (optionen.leseFehler && msg.type === 'meteo_volt/prices') {
      throw { code: 'unknown_error', message: 'Die Prognose ist gerade nicht lesbar.' };
    }
    if (msg.type === 'meteo_volt/prices') {
      const jetzt = Date.now();
      return {
        slots: preise.filter((p) => p.t + SLOT > jetzt).map((p) => ({ t: iso(p.t), q10: p.q10, q50: p.q50, q90: p.q90, source: p.source })),
        prices_known_until: iso(bekanntBis), computed_at: iso(jetzt0 - 30 * MINUTE), model: 'wx_syslag_2023',
      };
    }
    if (msg.type === 'meteo_volt/plan') {
      const f = fzGeraet(msg.vehicle);
      if (!f) throw { code: 'fahrzeug_unbekannt', message: 'Kein Fahrzeug dieses Standorts' };
      return { ...plaene.get(f.id), planning: planung };
    }
    if (msg.type === 'meteo_volt/appointments') {
      return termineAntwort(ausIso(msg.start), ausIso(msg.end), msg.vehicle);
    }
    if (msg.type === 'call_service' && msg.domain === 'meteo_volt') {
      const d = msg.service_data || {};
      const ablauf = { create_appointment: anlegen, update_appointment: aendern, delete_appointment: loeschen, cancel_appointments: absagen, undo: rueckgaengig }[msg.service];
      if (ablauf) {
        const antwort = ablauf(d);
        melden('appointments');
        baldPlanen();
        return msg.return_response ? { context: {}, response: antwort } : { context: {} };
      }
      if (msg.service === 'set_risk') {
        risiko = Number(d.risk);
        melden('site');
        baldPlanen();
        return { context: {} };
      }
      if (msg.service === 'replan') {
        if (Date.now() - letzterPlan < 10000) throw fehler('plan_pause', { sekunden: String(Math.ceil((10000 - (Date.now() - letzterPlan)) / 1000)) });
        letzterPlan = Date.now();
        await planen();
        return { context: {} };
      }
    }
    throw { code: 'unknown_command', message: `Unbekannt: ${msg.type}` };
  }

  return {
    nachricht,
    async abonnieren(ruf, msg) {
      await warte(30);
      if (msg.type !== 'meteo_volt/subscribe' || optionen.nichtGeladen) throw { code: 'not_found', message: 'nicht geladen' };
      abos.add(ruf);
      return () => abos.delete(ruf);
    },
  };
}
