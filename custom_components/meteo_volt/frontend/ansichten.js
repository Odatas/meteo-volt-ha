// Uebersicht und Fahrzeug-Tab als HTML, ohne DOM. Spec C8 Abschnitte 6.1 bis 6.5 und 6.7.
//
// z ist der Kontext aus meteo-volt-panel.js: Formatierer, jetzt, die Daten aus
// C3 und der Zustand der Oberflaeche. Die Diagramme zeichnet das Panel danach
// in die Platzhalter .planchart, .h-strip und .h-achse.

import { html } from './html.js';
import { blockGrund, bloeckeAbJetzt, planzeile, status, summen } from './plan.js';
import { symbol } from './symbole.js';
import { datumVon, plusTage, tagesbeginn } from './zeit.js';

export const fahrzeugTitel = (z, geraet) => (z.fahrzeuge.find((v) => v.vehicle === geraet) || {}).title ?? null;
export const personName = (z, id) => (z.personen.find((p) => p.entity_id === id) || {}).name ?? null;
const socMin = (z, geraet) => (z.fahrzeuge.find((v) => v.vehicle === geraet) || {}).soc_min_pct ?? 0;
const gesetzt = (x) => x !== null && x !== undefined;

export function preisHinweis(z) {
  if (z.netzentgelt === null) return z.f.t('hinweis_kein_netzentgelt');
  return z.gebuehr ? z.f.t('hinweis_mit_netzentgelt', { ct: z.f.ct(z.netzentgelt) }) : z.f.t('hinweis_nur_boerse');
}

export function preisSchalterHtml(z) {
  if (z.netzentgelt === null) return '';
  const knopf = (wert, schluessel) => html`<button type="button" data-aktion="preisart" data-wert="${wert}" aria-pressed="${z.ui.preisart === wert}">${z.f.t(schluessel)}</button>`;
  return html`<div class="seg klein" role="group" aria-label="${z.f.t('preisart')}">${knopf('boerse', 'boerse')}${knopf('kunde', 'mit_netzentgelt')}</div>`;
}

export function bereichSchalterHtml(z, ende) {
  const knopf = (wert, text) => html`<button type="button" data-aktion="bereich" data-wert="${wert}" aria-pressed="${z.ui.bereich === wert}">${text}</button>`;
  return html`<div class="seg klein" role="group" aria-label="${z.f.t('zeitraum')}">${knopf('48h', z.f.t('h48'))}${knopf('alles', z.f.t('bis_tag', { tag: z.f.tag(ende) }))}</div>`;
}

export function legendeHtml(f) {
  return html`<div class="legende"><span><i class="sw sw-soc"></i>${f.t('leg_ladestand')}</span><span><i class="sw sw-laden"></i>${f.t('leg_laden')}</span>
    <span><i class="sw sw-weg"></i>${f.t('leg_unterwegs')}</span><span><i class="sw sw-preis"></i>${f.t('leg_preis')}</span><span><i class="sw sw-prognose"></i>${f.t('leg_prognose')}</span></div>`;
}

export function warnzeileHtml(z) {
  if (!z.planFehler) return '';
  return html`<div class="warnzeile">${symbol('warnung')}<span>${z.f.t('plan_gescheitert', { fehler: z.planFehler })}</span></div>`;
}

export function statusHtml(z, fz) {
  const { f, jetzt } = z;
  const termine = z.termine.filter((t) => t.vehicle === fz.vehicle);
  const s = status(z.plaene.get(fz.vehicle), termine, jetzt, Boolean(z.fenster.get(fz.vehicle)));
  const teile = [];
  if (s.unterwegsBis !== null) teile.push(html`<span>${f.t('st_unterwegs_bis', { zeit: f.zeitMitTag(s.unterwegsBis, jetzt) })}</span>`);
  if (s.laden.art === 'jetzt') {
    teile.push(html`<span>${gesetzt(s.laden.kw) ? f.t('st_laedt_jetzt', { kw: f.kw(s.laden.kw) }) : f.t('st_laedt_jetzt_ohne')}</span>`);
  } else if (s.laden.art === 'ab') {
    teile.push(html`<span>${f.t('st_laedt_ab', { zeit: f.zeitMitTag(s.laden.t, jetzt) })}</span>`);
  } else {
    teile.push(html`<span>${f.t(s.laden.art === 'keins' ? 'st_kein_laden' : 'kein_plan')}</span>`);
  }
  if (s.warnungen) {
    teile.push(html`<span class="warnung">${s.warnungen === 1 ? f.t('st_warnung_1') : f.t('st_warnung_n', { n: s.warnungen })}</span>`);
  }
  return html`<div class="status num">${teile}</div>`;
}

const warnHtml = (text) => html`<span class="warn">${symbol('warnung')}<span>${text}</span></span>`;

export function terminHtml(z, termin, mitFahrzeug, kopfDatum) {
  const { f } = z;
  const zeitText = (ms) => (datumVon(ms, z.tz) === kopfDatum ? f.zeit(ms) : f.wochentagZeit(ms));
  const min = socMin(z, termin.vehicle);
  const z1 = [];
  if (mitFahrzeug) z1.push(html`<span class="fzname">${fahrzeugTitel(z, termin.vehicle) ?? ''}</span>`);
  const fahrer = termin.driver ? personName(z, termin.driver) : null;
  if (fahrer) z1.push(html`<span class="meta">${symbol('person')}${fahrer}</span>`);
  if (termin.repeat !== 'once') {
    const regel = f.regelKurz(termin.repeat, termin.date);
    z1.push(html`<span class="meta">${symbol('wiederholung')}${termin.changed ? `${regel}, ${f.t('einzeln_geaendert')}` : regel}</span>`);
  }
  if (gesetzt(termin.soc) && termin.soc >= min) z1.push(html`<span class="meta">${f.t('ziel_soc', { soc: f.prozent(termin.soc) })}</span>`);
  const zeilen = [];
  const zeile = planzeile(termin);
  if (zeile && zeile.art === 'unterwegs') {
    zeilen.push(html`<span class="plan">${f.t('st_unterwegs_bis', { zeit: f.zeitMitTag(zeile.bis, z.jetzt) })}</span>`);
  } else if (zeile && zeile.art === 'abfahrt') {
    zeilen.push(html`<span class="plan num">${f.t('abfahrt_mit', { soc: f.prozent(zeile.soc) })}</span>`);
  } else if (zeile) {
    for (const w of zeile.warnungen) {
      zeilen.push(warnHtml(w.art === 'ziel'
        ? f.t('ziel_unerreichbar', { soc: f.prozent(w.soc), kwh: f.kwh(w.kwh) })
        : f.t('unter_min', { soc: f.prozent(w.soc), min: f.prozent(min) })));
    }
  }
  for (const hinweis of termin.hints || []) {
    if (hinweis.type === 'overlap') zeilen.push(warnHtml(f.t('hinweis_overlap')));
    else if (hinweis.type === 'driver_busy') {
      zeilen.push(warnHtml(f.t('hinweis_fahrer', {
        fahrer: fahrer ?? '', fahrzeug: fahrzeugTitel(z, hinweis.vehicle) ?? f.t('anderes_fahrzeug'),
      })));
    }
  }
  return html`<button type="button" class="termin" data-aktion="termin" data-entry="${termin.entry}" data-date="${termin.date}">
    <span class="zeit num"><b>${zeitText(termin.abfahrt)}</b><span>${zeitText(termin.rueckkehr)}</span></span>
    <span class="mitte"><span class="z1">${z1}</span>${zeilen}</span>
    <span class="km num">${f.t('km', { km: termin.distance_km })}</span></button>`;
}

export function listeHtml(z, liste, mitFahrzeug, mehrWas, leerText) {
  const { f } = z;
  const mehr = html`<button type="button" class="mehr" data-aktion="mehr" data-was="${mehrWas}">${f.t('mehr_termine')}</button>`;
  if (!liste.length) return html`<div class="karte"><div class="leer">${leerText}</div>${mehr}</div>`;
  const heute = datumVon(z.jetzt, z.tz);
  const teile = [];
  let kopf = null;
  let grenze = false;
  for (const termin of liste) {
    if (!grenze && z.planende !== null && termin.abfahrt >= z.planende) {
      teile.push(html`<div class="grenze">${f.t('noch_nicht_geplant', { tag: f.tag(z.planende), zeit: f.zeit(z.planende) })}</div>`);
      grenze = true;
      kopf = null;
    }
    const datum = datumVon(Math.max(termin.abfahrt, z.jetzt), z.tz);
    if (datum !== kopf) {
      kopf = datum;
      teile.push(html`<div class="tag${datum === heute ? ' heute' : ''}">${f.tagKopf(datum, z.jetzt)}</div>`);
    }
    teile.push(terminHtml(z, termin, mitFahrzeug, kopf));
  }
  return html`<div class="karte agenda">${teile}${mehr}</div>`;
}

export function bloeckeHtml(z, fz, bloecke) {
  const { f } = z;
  if (!bloecke.length) return html`<p class="hinweis">${f.t('kein_laden_bis_ende')}</p>`;
  const termine = z.termine.filter((t) => t.vehicle === fz.vehicle);
  const grund = (b) => {
    const g = blockGrund(b, termine);
    if (g.art === 'ziel') return f.t('grund_ziel', { abfahrt: f.wochentagZeit(g.termin.abfahrt), soc: f.prozent(g.termin.soc) });
    if (g.art === 'vor') return f.t('grund_vor', { abfahrt: f.wochentagZeit(g.termin.abfahrt) });
    return f.t('grund_ende');
  };
  const zeigen = z.ui.alleBloecke ? bloecke : bloecke.slice(0, 4);
  const mehr = bloecke.length > 4
    ? html`<button type="button" class="mehr" data-aktion="bloecke">${z.ui.alleBloecke ? f.t('weniger') : f.t('alle_bloecke', { n: bloecke.length })}</button>`
    : '';
  return html`<div class="bloecke"><div class="bloecke-kopf">${f.t('ladebloecke')} <span class="hinweis">${preisHinweis(z)}</span></div>
    ${zeigen.map((b) => html`<div class="block">
      <span class="num"><b>${f.tag(b.von)}</b> ${f.t('von_bis', { von: f.zeit(b.von), bis: f.zeit(b.bis) })}</span>
      <span class="num b-soc">${f.t('soc_von_bis', { von: f.prozent(b.socVon), bis: f.prozent(b.socBis) })}</span>
      <span class="b-info num">${f.t('block_werte', { kwh: f.kwh(b.kwh), preis: f.ct(b.preis + z.gebuehr), eur: f.eur(b.kosten + z.gebuehr * b.kwh), grund: grund(b) })}</span>
    </div>`)}${mehr}</div>`;
}

export function plankarteHtml(z, fz) {
  const { f } = z;
  const plan = z.plaene.get(fz.vehicle);
  const fenster = z.fenster.get(fz.vehicle);
  const bloecke = fenster ? bloeckeAbJetzt(plan, z.jetzt) : [];
  const s = summen(bloecke, z.gebuehr);
  const ohne = f.t('ohne_wert');
  const kz = (wert, label) => html`<div class="kz"><b class="num">${wert}</b><span>${label}</span></div>`;
  const kennzahlen = html`<div class="kennzahlen">
    ${kz(gesetzt(fz.soc_pct) ? f.prozent(fz.soc_pct) : ohne, f.t('kz_ladestand'))}
    ${kz(fenster ? f.kwh(s.kwh) : ohne, f.t('kz_geplant'))}
    ${kz(fenster ? f.eur(s.kosten) : ohne, f.t(z.gebuehr ? 'kz_kosten_mit' : 'kz_kosten_ohne'))}
    ${kz(fenster && gesetzt(plan.soc_end_pct) ? f.prozent(plan.soc_end_pct) : ohne, f.t('kz_planende'))}</div>`;
  if (!fenster) return html`<div class="karte plankarte">${kennzahlen}${statusHtml(z, fz)}</div>`;
  return html`<div class="karte plankarte">${kennzahlen}${statusHtml(z, fz)}
    <div class="chartkopf">${legendeHtml(f)}<div class="steuerung">${preisSchalterHtml(z)}${bereichSchalterHtml(z, fenster.ende)}</div></div>
    <div class="planchart" data-fz="${fz.vehicle}"></div>
    ${bloeckeHtml(z, fz, bloecke)}</div>`;
}

export function fahrzeugHtml(z, fz) {
  const bis = tagesbeginn(plusTage(datumVon(z.jetzt, z.tz), z.ui.tageFahrzeug), z.tz);
  const liste = z.termine.filter((t) => t.vehicle === fz.vehicle && t.abfahrt < bis);
  return html`<div class="spalte">${warnzeileHtml(z)}${plankarteHtml(z, fz)}
    ${listeHtml(z, liste, false, 'fahrzeug', z.f.t('keine_termine'))}</div>`;
}

export function uebersichtHtml(z) {
  const { f } = z;
  const risiko = html`<div class="karte risiko">
    <div class="zeile"><strong>${f.t('risiko')}</strong>
      <div class="seg" role="group" aria-label="${f.t('risiko')}">${[1, 2, 3].map((wert) => html`<button type="button" data-aktion="risiko" data-wert="${wert}" aria-pressed="${z.risiko === wert}">${f.t(`risiko_${wert}`)}</button>`)}</div></div>
    <p class="hinweis">${f.t(`risiko_satz_${z.risiko}`)} ${f.t('risiko_alle')}</p></div>`;
  const erster = z.fahrzeuge.map((v) => z.fenster.get(v.vehicle)).find(Boolean) || null;
  const zeilen = z.fahrzeuge.map((fz) => html`<button type="button" class="h-zeile" data-aktion="tab" data-id="${fz.vehicle}">
    <div class="h-label"><b>${fz.title} <span class="num h-soc">${gesetzt(fz.soc_pct) ? f.prozent(fz.soc_pct) : ''}</span></b>${statusHtml(z, fz)}</div>
    ${z.fenster.get(fz.vehicle) ? html`<div class="h-strip" data-art="fz" data-fz="${fz.vehicle}"></div>` : html`<div></div>`}</button>`);
  const horizont = html`<div class="karte horizont">
    ${erster ? html`<div class="h-zeile"><div class="h-label"><b>${f.t('strompreis')}</b><span class="hinweis">${preisHinweis(z)}</span>${preisSchalterHtml(z)}</div><div class="h-strip" data-art="preis"></div></div>` : ''}
    ${zeilen}
    ${erster ? html`<div class="h-zeile h-achsenzeile"><div class="h-label"></div><div class="h-achse"></div></div>` : ''}
    <div class="h-fuss">${legendeHtml(f)}</div></div>`;
  const bis = tagesbeginn(plusTage(datumVon(z.jetzt, z.tz), z.ui.tageUebersicht), z.tz);
  const liste = z.termine.filter((t) => t.abfahrt < bis && (z.ui.filter === 'alle'
    || (z.ui.filter === 'ohne' ? !t.driver : t.driver === z.ui.filter)));
  const chip = (id, name, mitSymbol) => html`<button type="button" class="chip" data-aktion="filter" data-id="${id}" aria-pressed="${z.ui.filter === id}">${mitSymbol ? symbol('person') : ''}${name}</button>`;
  const chips = [chip('alle', f.t('filter_alle'), false), ...z.personen.map((p) => chip(p.entity_id, p.name, true)), chip('ohne', f.t('filter_ohne'), false)];
  return html`<div class="spalte">${warnzeileHtml(z)}${risiko}
    <div class="abschnitt">${z.planende !== null ? f.t('ladeplan_bis', { tag: f.tag(z.planende), zeit: f.zeit(z.planende) }) : f.t('ladeplan')}</div>
    ${horizont}
    <div class="abschnitt">${f.t('termine_aller')}</div>
    <div class="chips" role="group" aria-label="${f.t('filter_fahrer')}">${chips}</div>
    ${listeHtml(z, liste, true, 'uebersicht', f.t('keine_termine_tage'))}</div>`;
}
