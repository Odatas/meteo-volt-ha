// Die Diagramme als SVG, gezeichnet vom Panel wie im Entwurf. Spec C8 Abschnitte 6.3, 6.5 und 6.6.
//
// Die ...Svg-Funktionen bauen nur Text und laufen auch unter Node. bindeTooltip
// braucht das DOM und haengt das Antippen an ein gezeichnetes Diagramm.

import { html } from './html.js';
import { hatWarnung } from './plan.js';
import { STUNDE, datumVon, plusTage, tagesbeginn } from './zeit.js';

const r = (n) => Math.round(n * 10) / 10;

// Die lokalen Mitternaechte nach t0 und vor t1.
export function mitternaechte(t0, t1, tz) {
  const aus = [];
  for (let datum = plusTage(datumVon(t0, tz), 1); ; datum = plusTage(datum, 1)) {
    const m = tagesbeginn(datum, tz);
    if (m >= t1) return aus;
    aus.push(m);
  }
}

// Zusammenhaengende Laeufe von Slots, fuer die bedingung gilt, als [von, bis] Index.
function laeufe(slots, bedingung) {
  const aus = [];
  slots.forEach((s, i) => {
    if (!bedingung(s)) return;
    const letzter = aus[aus.length - 1];
    if (letzter && letzter[1] === i - 1) letzter[1] = i;
    else aus.push([i, i]);
  });
  return aus;
}

function tageBeschriften(teile, t0, t1, x, y, breit, f) {
  const grenzen = [t0, ...mitternaechte(t0, t1, f.tz), t1];
  for (let k = 0; k < grenzen.length - 1; k += 1) {
    const a = x(grenzen[k]);
    const b = x(grenzen[k + 1]);
    const tag = f.tag(grenzen[k]);
    const text = b - a > (breit ? 70 : 60) ? tag : b - a > 24 ? tag.split(' ')[0] : '';
    if (text) teile.push(html`<text class="achse" x="${r((a + b) / 2)}" y="${y}" text-anchor="middle">${text}</text>`);
  }
}

const treppe = (slots, x, y) => slots
  .map((s, k) => `${k ? 'L' : 'M'}${r(x(s.t))},${r(y(s))}L${r(x(s.ende))},${r(y(s))}`)
  .join('');

// Ob ein Slot in einem Termin liegt, von Abfahrt bis Rueckkehr.
export const unterwegs = (s, termine) => termine.some((t) => t.abfahrt < s.ende && s.t < t.rueckkehr);

// Die Plankarte eines Fahrzeugs. d: { schluessel, fz, name, fenster, termine, bereich }, fenster aus planAbJetzt.
export function planChartSvg(d, W, schmal, f, gebuehr) {
  const { fz, fenster, termine } = d;
  const grenze = d.bereich === '48h' ? fenster.start + 48 * STUNDE : Infinity;
  const slots = fenster.slots.filter((s) => s.t < grenze);
  const t0 = slots[0].t;
  const t1 = slots[slots.length - 1].ende;
  const L = 44;
  const pw = W - L - 10;
  const hA = schmal ? 150 : 190;
  const hB = schmal ? 70 : 96;
  const yA0 = 12;
  const yA1 = yA0 + hA;
  const yB0 = yA1 + 22;
  const yB1 = yB0 + hB;
  const H = yB1 + 26;
  const x = (t) => L + ((t - t0) / (t1 - t0)) * pw;
  const yS = (soc) => yA1 - (Math.max(-6, Math.min(104, soc)) / 100) * hA;
  const preis = (s) => s.preis + gebuehr;
  const pTop = Math.ceil(Math.max(0.05, ...slots.map(preis)) * 20) / 20;
  const pMin = Math.min(0, ...slots.map(preis));
  const yP = (p) => yB1 - ((p - pMin) / (pTop - pMin)) * hB;
  const id = d.schluessel;
  const t = [];
  t.push(html`<defs>
    <pattern id="weg-${id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--mv-weg)" stroke-width="3"/></pattern>
    <linearGradient id="fl-${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--mv-soc)" stop-opacity=".26"/><stop offset="1" stop-color="var(--mv-soc)" stop-opacity="0"/></linearGradient>
    <clipPath id="min-${id}"><rect x="${L}" y="${r(yS(fz.soc_min_pct - 0.5))}" width="${r(pw)}" height="${hA}"/></clipPath></defs>`);
  mitternaechte(t0, t1, f.tz).forEach((m) => t.push(html`<line class="gitter" x1="${r(x(m))}" x2="${r(x(m))}" y1="${yA0}" y2="${yB1}"/>`));
  tageBeschriften(t, t0, t1, x, H - 8, !schmal, f);

  // Ladestand
  [0, 50, 100].forEach((v) => t.push(html`<text class="achse" x="${L - 8}" y="${r(yS(v) + 4)}" text-anchor="end">${v} %</text>`));
  for (const termin of termine) {
    if (termin.rueckkehr <= t0 || termin.abfahrt >= t1) continue;
    const a = x(Math.max(termin.abfahrt, t0));
    const b = x(Math.min(termin.rueckkehr, t1));
    t.push(html`<rect x="${r(a)}" y="${yA0}" width="${r(b - a)}" height="${hA}" fill="url(#weg-${id})"/>`);
  }
  laeufe(slots, (s) => s.laden).forEach(([a, b]) => {
    const xa = x(slots[a].t);
    const w = Math.max(2, x(slots[b].ende) - xa);
    t.push(html`<rect x="${r(xa)}" y="${yA0}" width="${r(w)}" height="${hA}" fill="var(--mv-laden-soft)"/><rect x="${r(xa)}" y="${yA1 - 6}" width="${r(w)}" height="6" rx="1" fill="var(--mv-laden)"/>`);
  });
  [['diagramm_max', fz.soc_max_pct], ['diagramm_min', fz.soc_min_pct]].forEach(([schluessel, v]) => {
    t.push(html`<line class="grenzlinie" x1="${L}" x2="${r(L + pw)}" y1="${r(yS(v))}" y2="${r(yS(v))}"/>`);
    t.push(html`<text class="achse klein" x="${r(L + pw - 4)}" y="${r(yS(v) - 5)}" text-anchor="end">${f.t(schluessel, { soc: f.prozent(v) })}</text>`);
  });
  t.push(html`<line class="rahmen" x1="${L}" x2="${r(L + pw)}" y1="${yA1}" y2="${yA1}"/>`);
  let pfad = `M${r(x(t0))},${r(yS(fenster.socStart))}`;
  slots.forEach((s) => {
    pfad += `L${r(x(s.ende))},${r(yS(s.soc))}`;
  });
  t.push(html`<path d="${pfad}L${r(x(t1))},${yA1}L${r(x(t0))},${yA1}Z" fill="url(#fl-${id})"/>`);
  t.push(html`<path d="${pfad}" class="soc-linie"/><path d="${pfad}" class="soc-linie warnlinie" clip-path="url(#min-${id})"/>`);
  for (const termin of termine) {
    if (termin.abfahrt < t0 || termin.abfahrt >= t1) continue;
    const xd = x(termin.abfahrt);
    const warn = hatWarnung(termin);
    t.push(html`<path d="M${r(xd - 5)},${yA0 - 8}L${r(xd + 5)},${yA0 - 8}L${r(xd)},${yA0 - 1}Z" fill="${warn ? 'var(--mv-warn-icon)' : 'var(--mv-text2)'}"/>`);
    if (termin.soc !== null && termin.soc !== undefined && termin.soc >= fz.soc_min_pct) {
      const verfehlt = Boolean(termin.plan && termin.plan.target_missing_kwh !== null && termin.plan.target_missing_kwh !== undefined);
      t.push(html`<circle cx="${r(xd)}" cy="${r(yS(termin.soc))}" r="5" class="zielpunkt${verfehlt ? ' verfehlt' : ''}"/>`);
      t.push(html`<text class="achse ziel" x="${r(xd - 9)}" y="${r(yS(termin.soc) + 4)}" text-anchor="end">${f.t('diagramm_ziel', { soc: f.prozent(termin.soc) })}</text>`);
    }
  }

  // Preis
  const nullY = yP(0);
  t.push(html`<text class="achse" x="${L - 8}" y="${r(yP(pTop) + 4)}" text-anchor="end">${Math.round(pTop * 100)} ct</text>`);
  t.push(html`<text class="achse" x="${L - 8}" y="${r(nullY + 4)}" text-anchor="end">0</text>`);
  slots.forEach((s) => {
    if (!s.laden) return;
    t.push(html`<rect x="${r(x(s.t))}" y="${r(Math.min(yP(preis(s)), nullY))}" width="${r(Math.max(1.5, x(s.ende) - x(s.t)))}" height="${r(Math.max(1, Math.abs(nullY - yP(preis(s)))))}" fill="var(--mv-laden)"/>`);
  });
  const yPreis = (s) => yP(preis(s));
  const boerse = slots.filter((s) => s.boerse);
  const prognose = slots.filter((s) => !s.boerse);
  if (boerse.length) t.push(html`<path d="${treppe(boerse, x, yPreis)}" class="preis-linie"/>`);
  if (prognose.length) {
    const xp = x(prognose[0].t);
    t.push(html`<path d="${treppe(prognose, x, yPreis)}" class="preis-linie prognose"/>`);
    t.push(html`<line class="prognose-marke" x1="${r(xp)}" x2="${r(xp)}" y1="${yB0 - 4}" y2="${yB1}"/><text class="achse klein" x="${r(xp + 5)}" y="${yB0 + 6}">${f.t('leg_prognose')}</text>`);
  }
  t.push(html`<line class="rahmen" x1="${L}" x2="${r(L + pw)}" y1="${r(nullY)}" y2="${r(nullY)}"/>`);

  t.push(html`<g class="fadenkreuz" visibility="hidden"><line class="faden" y1="${yA0}" y2="${yB1}"/><circle class="faden-soc" r="4.5"/><circle class="faden-preis" r="4"/></g>`);
  t.push(html`<rect class="fang" x="${L}" y="0" width="${r(pw)}" height="${yB1}" fill="transparent"/>`);
  return {
    svg: html`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${f.t('diagramm_plan', { name: d.name })}">${t}</svg>`,
    geo: { L, pw, t0, t1, x, slots, yS: (s) => yS(s.soc), yP: yPreis },
  };
}

// Ein schmales Band je Fahrzeug fuer die Uebersicht, alle auf derselben Zeitachse.
export function streifenSvg(d, W, f) {
  const { fz, fenster, termine } = d;
  const slots = fenster.slots;
  const t0 = fenster.start;
  const t1 = fenster.ende;
  const H = 56;
  const pad = 4;
  const x = (t) => ((t - t0) / (t1 - t0)) * W;
  const y = (soc) => H - pad - (Math.max(0, Math.min(100, soc)) / 100) * (H - 2 * pad);
  const id = d.schluessel;
  const t = [];
  mitternaechte(t0, t1, f.tz).forEach((m) => t.push(html`<line class="gitter" x1="${r(x(m))}" x2="${r(x(m))}" y1="0" y2="${H}"/>`));
  t.push(html`<defs><pattern id="weg-${id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--mv-weg)" stroke-width="3"/></pattern></defs>`);
  for (const termin of termine) {
    if (termin.rueckkehr <= t0 || termin.abfahrt >= t1) continue;
    const a = x(Math.max(termin.abfahrt, t0));
    const b = x(Math.min(termin.rueckkehr, t1));
    t.push(html`<rect x="${r(a)}" y="0" width="${r(b - a)}" height="${H}" fill="url(#weg-${id})"/>`);
  }
  laeufe(slots, (s) => s.laden).forEach(([a, b]) => {
    const xa = x(slots[a].t);
    const w = Math.max(2, x(slots[b].ende) - xa);
    t.push(html`<rect x="${r(xa)}" y="0" width="${r(w)}" height="${H}" fill="var(--mv-laden-soft)"/><rect x="${r(xa)}" y="${H - 4}" width="${r(w)}" height="4" fill="var(--mv-laden)"/>`);
  });
  t.push(html`<line class="grenzlinie" x1="0" x2="${W}" y1="${r(y(fz.soc_min_pct))}" y2="${r(y(fz.soc_min_pct))}"/>`);
  let pfad = `M0,${r(y(fenster.socStart))}`;
  slots.forEach((s) => {
    pfad += `L${r(x(s.ende))},${r(y(s.soc))}`;
  });
  t.push(html`<path d="${pfad}" class="soc-linie"/>`);
  for (const termin of termine) {
    if (termin.abfahrt < t0 || termin.abfahrt >= t1 || !hatWarnung(termin)) continue;
    const xd = x(termin.abfahrt);
    t.push(html`<path d="M${r(xd - 5)},1L${r(xd + 5)},1L${r(xd)},8Z" fill="var(--mv-warn-icon)"/>`);
  }
  return html`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">${t}</svg>`;
}

// Der Preis ueber der Uebersicht: der Preis, mit dem geplant wurde.
export function preisStreifenSvg(fenster, W, f, gebuehr) {
  const slots = fenster.slots;
  const t0 = fenster.start;
  const t1 = fenster.ende;
  const H = 40;
  const pad = 4;
  const preis = (s) => s.preis + gebuehr;
  const pMax = Math.max(...slots.map(preis));
  const pMin = Math.min(0, ...slots.map(preis));
  const x = (t) => ((t - t0) / (t1 - t0)) * W;
  const y = (s) => H - pad - ((preis(s) - pMin) / (pMax - pMin || 1)) * (H - 2 * pad);
  const t = [];
  mitternaechte(t0, t1, f.tz).forEach((m) => t.push(html`<line class="gitter" x1="${r(x(m))}" x2="${r(x(m))}" y1="0" y2="${H}"/>`));
  const boerse = slots.filter((s) => s.boerse);
  const prognose = slots.filter((s) => !s.boerse);
  if (boerse.length) t.push(html`<path d="${treppe(boerse, x, y)}" class="preis-linie"/>`);
  if (prognose.length) t.push(html`<path d="${treppe(prognose, x, y)}" class="preis-linie prognose"/>`);
  return html`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">${t}</svg>`;
}

// Die Tage unter den Baendern der Uebersicht.
export function achseSvg(t0, t1, W, f) {
  const t = [];
  tageBeschriften(t, t0, t1, (tt) => ((tt - t0) / (t1 - t0)) * W, 13, W > 500, f);
  return html`<svg viewBox="0 0 ${W} 18" width="${W}" height="18" aria-hidden="true">${t}</svg>`;
}

// Die Prognose im Tab Preise. d: { slots aus preisSlots, bereich, tage aus tageswerte }.
export function preisChartSvg(d, W, schmal, f, gebuehr) {
  const grenze = d.bereich === '48h' ? d.slots[0].t + 48 * STUNDE : Infinity;
  const slots = d.slots.filter((s) => s.t < grenze);
  const t0 = slots[0].t;
  const t1 = slots[slots.length - 1].ende;
  const L = 44;
  const pw = W - L - 10;
  const h = schmal ? 190 : 250;
  const y0 = 14;
  const y1 = y0 + h;
  const H = y1 + 26;
  const x = (t) => L + ((t - t0) / (t1 - t0)) * pw;
  const lo = Math.floor(Math.min(0, ...slots.map((s) => s.q10 + gebuehr)) * 10) / 10;
  const hi = Math.max(lo + 0.1, Math.ceil(Math.max(...slots.map((s) => s.q90 + gebuehr)) * 10) / 10);
  const y = (p) => y1 - ((p - lo) / (hi - lo)) * h;
  const t = [];
  for (let p = lo; p <= hi + 1e-9; p += 0.1) {
    t.push(html`<line class="gitter" x1="${L}" x2="${r(L + pw)}" y1="${r(y(p))}" y2="${r(y(p))}"/><text class="achse" x="${L - 8}" y="${r(y(p) + 4)}" text-anchor="end">${Math.round(p * 100)} ct</text>`);
  }
  mitternaechte(t0, t1, f.tz).forEach((m) => t.push(html`<line class="gitter" x1="${r(x(m))}" x2="${r(x(m))}" y1="${y0}" y2="${y1}"/>`));
  tageBeschriften(t, t0, t1, x, H - 8, !schmal, f);
  const wert = (feld) => (s) => y(s[feld] + gebuehr);
  const prognose = slots.filter((s) => !s.boerse);
  const boerse = slots.filter((s) => s.boerse);
  if (prognose.length) {
    const oben = treppe(prognose, x, wert('q90'));
    const unten = [...prognose].reverse()
      .map((s) => `L${r(x(s.ende))},${r(y(s.q10 + gebuehr))}L${r(x(s.t))},${r(y(s.q10 + gebuehr))}`).join('');
    t.push(html`<path d="${oben}${unten}Z" fill="var(--mv-band)"/>`);
  }
  for (const tag of d.tage) {
    if (!tag.fenster || tag.fenster.von >= t1) continue;
    const xa = x(tag.fenster.von);
    const xb = Math.min(x(tag.fenster.bis), L + pw);
    t.push(html`<rect x="${r(xa)}" y="${y1 - 7}" width="${r(Math.max(3, xb - xa))}" height="7" rx="1.5" fill="var(--mv-laden)"/>`);
  }
  if (boerse.length) t.push(html`<path d="${treppe(boerse, x, wert('q50'))}" class="preis-linie stark"/>`);
  if (prognose.length) {
    const xp = x(prognose[0].t);
    t.push(html`<path d="${treppe(prognose, x, wert('q50'))}" class="preis-linie stark prognose"/>`);
    t.push(html`<line class="prognose-marke" x1="${r(xp)}" x2="${r(xp)}" y1="${y0 - 6}" y2="${y1}"/><text class="achse klein" x="${r(xp + 5)}" y="${y0 + 4}">${f.t('leg_prognose')}</text>`);
  }
  t.push(html`<g class="fadenkreuz" visibility="hidden"><line class="faden" y1="${y0}" y2="${y1}"/><circle class="faden-preis" r="4"/></g>`);
  t.push(html`<rect class="fang" x="${L}" y="0" width="${r(pw)}" height="${y1}" fill="transparent"/>`);
  return {
    svg: html`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${f.t('p_diagramm')}">${t}</svg>`,
    geo: { L, pw, t0, t1, x, slots, yP: wert('q50') },
  };
}

// Das Antippen: Fadenkreuz und Werte des Slots. zeilen(slot) liefert den Inhalt als Html.
export function bindeTooltip(box, geo, zeilen) {
  const svg = box.querySelector('svg');
  const kreuz = svg.querySelector('.fadenkreuz');
  const tip = box.querySelector('.tooltip');
  const faden = kreuz.querySelector('.faden');
  const punktSoc = kreuz.querySelector('.faden-soc');
  const punktPreis = kreuz.querySelector('.faden-preis');
  const zeige = (ev) => {
    const rahmen = svg.getBoundingClientRect();
    const zeitpunkt = geo.t0 + ((ev.clientX - rahmen.left - geo.L) / geo.pw) * (geo.t1 - geo.t0);
    const slot = geo.slots.find((s) => zeitpunkt < s.ende) || geo.slots[geo.slots.length - 1];
    const xm = geo.x((slot.t + slot.ende) / 2);
    kreuz.setAttribute('visibility', 'visible');
    faden.setAttribute('x1', xm);
    faden.setAttribute('x2', xm);
    if (punktSoc && geo.yS) {
      punktSoc.setAttribute('cx', xm);
      punktSoc.setAttribute('cy', geo.yS(slot));
    }
    punktPreis.setAttribute('cx', xm);
    punktPreis.setAttribute('cy', geo.yP(slot));
    tip.innerHTML = String(zeilen(slot));
    tip.hidden = false;
    const aussen = box.getBoundingClientRect();
    let links = ev.clientX - aussen.left + 14;
    if (links + tip.offsetWidth > aussen.width) links = ev.clientX - aussen.left - tip.offsetWidth - 14;
    tip.style.left = `${Math.max(0, links)}px`;
  };
  const fang = svg.querySelector('.fang');
  fang.addEventListener('pointermove', zeige);
  fang.addEventListener('pointerdown', zeige);
  fang.addEventListener('pointerleave', (ev) => {
    if (ev.pointerType !== 'mouse') return;
    kreuz.setAttribute('visibility', 'hidden');
    tip.hidden = true;
  });
}
