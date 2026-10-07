// Der Tab Preise als HTML, ohne DOM. Spec C8 Abschnitte 6.6 und 6.7.
//
// Das Diagramm zeichnet das Panel danach in den Platzhalter .preischart.

import { bereichSchalterHtml, preisHinweis, preisSchalterHtml } from './ansichten.js';
import { html } from './html.js';
import { tageswerte } from './preise.js';
import { ausIso, datumVon, plusTage, tagesbeginn } from './zeit.js';

export function preiseHtml(z) {
  const { f } = z;
  if (!z.preise.length) return html`<div class="spalte"><div class="karte zustand">${f.t('p_keine')}</div></div>`;
  const h = z.ui.fensterStunden;
  const g = z.gebuehr;
  const ohne = f.t('ohne_wert');
  const tage = tageswerte(z.preise, h, z.tz, g);
  const heute = datumVon(z.jetzt, z.tz);
  const tagVon = (datum) => tage.find((t) => t.datum === datum);
  const zeitraum = (fenster) => (fenster ? f.t('von_bis', { von: f.zeit(fenster.von), bis: f.zeit(fenster.bis) }) : ohne);
  const mittel = (tag) => (tag && tag.fenster ? f.ctKurz(tag.fenster.mittel) : ohne);
  const kz = (wert, label) => html`<div class="kz"><b class="num">${wert}</b><span>${label}</span></div>`;
  const bekannt = ausIso(z.preiseRoh.prices_known_until);
  const berechnet = ausIso(z.preiseRoh.computed_at);
  const ende = z.preise[z.preise.length - 1].ende;
  const zeilen = tage.map((tag) => {
    const ab = tag.von > tagesbeginn(tag.datum, z.tz) ? html` <span class="hinweis">${f.t('p_ab', { zeit: f.zeit(tag.von) })}</span>` : '';
    const bis = tag.bis < tagesbeginn(plusTage(tag.datum, 1), z.tz) ? html` <span class="hinweis">${f.t('p_bis', { zeit: f.zeit(tag.bis) })}</span>` : '';
    const werte = f.t('p_werte', {
      tief: f.ctKurz(tag.tief.q50 + g), tiefzeit: f.zeit(tag.tief.t), hoch: f.ctKurz(tag.hoch.q50 + g),
      hochzeit: f.zeit(tag.hoch.t), mittel: f.ctKurz(tag.mittel),
    });
    const spanne = tag.spanne !== null ? `${f.t('trenner')}${f.t('p_spanne', { spanne: f.ctKurz(tag.spanne) })}` : '';
    return html`<div class="tagzeile">
      <span class="t-tag"><b>${f.tagKopf(tag.datum, z.jetzt)}</b>${ab}${bis}</span>
      <span class="t-quelle"><span class="quelle${tag.quelle === 'boerse' ? ' boerse' : ''}">${f.t(tag.quelle === 'boerse' ? 'p_quelle_boerse' : 'p_quelle_prognose')}</span></span>
      <span class="t-fenster num">${tag.fenster ? html`<b>${zeitraum(tag.fenster)}</b> <span class="hinweis">${f.t('durchschnitt', { preis: mittel(tag) })}</span>` : html`<span class="hinweis">${f.t('p_zu_kurz')}</span>`}</span>
      <span class="t-werte num">${werte}${spanne}</span></div>`;
  });
  const morgen = tagVon(plusTage(heute, 1));
  return html`<div class="spalte">
    <div class="karte plankarte">
      <div class="kennzahlen">
        ${kz(f.ctKurz(z.preise[0].q50 + g), f.t(g ? 'p_jetzt_mit' : 'p_jetzt'))}
        ${kz(zeitraum(tagVon(heute)?.fenster), f.t('p_heute', { h, preis: mittel(tagVon(heute)) }))}
        ${kz(zeitraum(morgen?.fenster), f.t('p_morgen', { h, preis: mittel(morgen) }))}
        ${kz(bekannt !== null ? f.tag(bekannt) : ohne, f.t('p_letzter_tag'))}
      </div>
      <div class="chartkopf"><div class="legende"><span><i class="sw sw-preis stark"></i>${f.t('p_leg_boerse')}</span><span><i class="sw sw-prognose stark"></i>${f.t('p_leg_prognose')}</span>
          <span><i class="sw sw-band"></i>${f.t('p_leg_spanne')}</span><span><i class="sw sw-laden"></i>${f.t('p_leg_guenstig', { h })}</span></div>
        <div class="steuerung">${preisSchalterHtml(z)}${bereichSchalterHtml(z, ende)}</div></div>
      <div class="planchart preischart"></div>
      <p class="hinweis">${berechnet !== null ? `${f.t('p_prognose_von', { zeit: f.zeitMitTag(berechnet, z.jetzt), modell: z.preiseRoh.model ?? ohne })} ` : ''}${preisHinweis(z)}</p>
    </div>
    <div class="karte tage">
      <div class="tage-kopf"><b>${f.t('p_je_tag')}</b>
        <div class="seg klein" role="group" aria-label="${f.t('p_laenge')}">
          ${[1, 2, 3, 4].map((n) => html`<button type="button" data-aktion="fenster" data-wert="${n}" aria-pressed="${h === n}">${n} h</button>`)}
        </div></div>
      <div class="tagzeile kopfzeile"><span>${f.t('p_kopf_tag')}</span><span></span><span>${f.t('p_kopf_guenstig', { h })}</span><span>${f.t('p_kopf_werte')}</span></div>
      ${zeilen}
    </div></div>`;
}
