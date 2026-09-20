// Das Formular eines Termins, die Rueckfrage nach dem Umfang, das Angebot bei
// Ueberschneidung. Spec C8 Abschnitte 7.1 bis 7.6.
//
// Das Panel prueft beim Eingeben mit pruefung.js. C3 prueft beim Speichern
// dasselbe; ein Fehler von dort steht am selben Ort wie der eigene.

import { fahrzeugTitel, personName } from './ansichten.js';
import { html } from './html.js';
import { termineAus } from './plan.js';
import { FAHRER_VORAUS, FEHLERORTE, fahrerKonflikt, fehlerOrt, pruefen } from './pruefung.js';
import { symbol } from './symbole.js';
import { REGELN } from './wiederholung.js';
import { MINUTE, datumVon, iso, naechsteVolleStunde, naiv, zuMs } from './zeit.js';

function oeffneDialog(panel, inhalt, voll) {
  const scrim = document.createElement('div');
  scrim.className = `scrim${voll ? ' voll' : ''}`;
  scrim.innerHTML = String(inhalt);
  panel.dialogWurzel().appendChild(scrim);
  const erstes = scrim.querySelector('input:not([disabled]), select, button.btn.voll');
  if (erstes) erstes.focus();
  return scrim;
}

export const schliesseOberstes = (panel) => {
  const oberstes = panel.dialogWurzel().lastElementChild;
  if (oberstes) oberstes.remove();
};
const schliesseAlle = (panel) => panel.dialogWurzel().replaceChildren();

// Neu oder bearbeiten. termin: ein Termin aus termineAus, oder null fuer neu.
export function oeffneTermin(panel, termin) {
  const z = panel.kontext();
  const { f, tz } = z;
  const jetzt = Date.now();
  const abfahrt = termin ? naiv(termin.abfahrt, tz) : naechsteVolleStunde(jetzt, tz);
  const rueckkehr = termin ? naiv(termin.rueckkehr, tz) : naiv(zuMs(abfahrt, tz) + 60 * MINUTE, tz);
  const fahrzeug = termin ? termin.vehicle : (panel.tabFahrzeug() ?? z.fahrzeuge[0].vehicle);
  const fahrer = termin ? termin.driver : (z.personen.some((p) => p.entity_id === z.ui.filter) ? z.ui.filter : null);
  const regel = termin ? termin.repeat : 'once';
  const loeschen = termin
    ? html`<button type="button" class="btn rot links" data-d="loeschen">${symbol('papierkorb')}${f.t('loeschen')}</button>` : '';
  const scrim = oeffneDialog(panel, html`
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-titel">
      <header>
        <button type="button" class="iconbtn" data-d="schliessen" aria-label="${f.t('schliessen')}">${symbol('schliessen')}</button>
        <h2 id="dlg-titel">${f.t(termin ? 'termin_bearbeiten' : 'neuer_termin')}</h2>
        <button type="button" class="btn kopfspeichern" data-d="speichern">${f.t('speichern')}</button>
      </header>
      <div class="koerper">
        <div class="feld"><span class="label" id="l-ab">${f.t('f_abfahrt')}</span>
          <div class="paar"><input type="date" id="f-ab-datum" aria-labelledby="l-ab" value="${abfahrt.slice(0, 10)}"><input type="time" id="f-ab-zeit" aria-labelledby="l-ab" value="${abfahrt.slice(11, 16)}"></div></div>
        <div class="feld" id="feld-rueckkehr"><span class="label" id="l-zu">${f.t('f_rueckkehr')}</span>
          <div class="paar"><input type="date" id="f-zu-datum" aria-labelledby="l-zu" value="${rueckkehr.slice(0, 10)}"><input type="time" id="f-zu-zeit" aria-labelledby="l-zu" value="${rueckkehr.slice(11, 16)}"></div>
          <span class="fehler" data-ort="rueckkehr" hidden></span></div>
        <div class="feld"><label for="f-regel">${f.t('f_wiederholung')}</label><select id="f-regel"></select>
          <span class="fehler" data-ort="wiederholung" hidden></span></div>
        <div class="feld" id="feld-strecke"><label for="f-km">${f.t('f_strecke')}</label>
          <input type="number" id="f-km" inputmode="numeric" min="0" step="1" value="${termin ? termin.distance_km : ''}">
          <span class="fehler" data-ort="strecke" hidden></span></div>
        <div class="zwei">
          <div class="feld"><label for="f-fahrzeug">${f.t('f_fahrzeug')}</label><select id="f-fahrzeug">
            ${z.fahrzeuge.map((v) => html`<option value="${v.vehicle}"${v.vehicle === fahrzeug ? html` selected` : ''}>${v.title}</option>`)}</select></div>
          <div class="feld"><label for="f-fahrer">${f.t('f_fahrer')}</label><select id="f-fahrer"><option value="">${f.t('f_kein_fahrer')}</option>
            ${z.personen.map((p) => html`<option value="${p.entity_id}"${p.entity_id === fahrer ? html` selected` : ''}>${p.name}</option>`)}</select></div>
        </div>
        <div class="feld" id="zeile-fahrer" hidden><span class="warnhinweis" data-ort="fahrer"></span></div>
        <div class="feld" id="feld-ladestand"><label for="f-soc">${f.t('f_ladestand')}</label>
          <input type="number" id="f-soc" inputmode="numeric" min="0" max="100" step="1" placeholder="${f.t('f_optional')}" value="${termin && termin.soc !== null && termin.soc !== undefined ? termin.soc : ''}">
          <span class="warnhinweis" data-warnung="ladestand" hidden></span><span class="fehler" data-ort="ladestand" hidden></span></div>
        ${termin ? html`<div class="unten-loeschen">${loeschen}</div>` : ''}
      </div>
      <footer>${loeschen}<button type="button" class="btn" data-d="schliessen">${f.t('abbrechen')}</button><button type="button" class="btn voll" data-d="speichern">${f.t('speichern')}</button></footer>
    </div>`, true);

  const q = (s) => scrim.querySelector(s);
  let dauer = Math.round((zuMs(rueckkehr, tz) - zuMs(abfahrt, tz)) / MINUTE);
  let versucht = false;
  let dienstFehler = null;
  let andere = [];
  const lokal = (datum, zeit) => (q(datum).value && q(zeit).value ? `${q(datum).value}T${q(zeit).value.slice(0, 5)}:00` : null);
  const lese = () => ({
    abfahrt: lokal('#f-ab-datum', '#f-ab-zeit'),
    rueckkehr: lokal('#f-zu-datum', '#f-zu-zeit'),
    regel: q('#f-regel').value || regel,
    km: q('#f-km').value,
    soc: q('#f-soc').value,
    fahrzeug: q('#f-fahrzeug').value,
    fahrer: q('#f-fahrer').value || null,
  });
  const regelOptionen = () => {
    const bezug = (lese().abfahrt || abfahrt).slice(0, 10);
    const gewaehlt = q('#f-regel').value || regel;
    q('#f-regel').innerHTML = String(html`${REGELN.map((r) => html`<option value="${r}"${r === gewaehlt ? html` selected` : ''}>${f.regelLang(r, bezug)}</option>`)}`);
  };
  // Roher Text wird escaped: Ein Fehler des Dienstes traegt Platzhalter aus Home Assistant.
  const zeige = (knoten, inhalt) => {
    knoten.hidden = !inhalt;
    knoten.innerHTML = inhalt ? String(html`${inhalt}`) : '';
  };
  const pruefenZeigen = () => {
    const w = lese();
    const socMin = (z.fahrzeuge.find((v) => v.vehicle === w.fahrzeug) || {}).soc_min_pct ?? 0;
    const e = pruefen(w, { jetzt: Date.now(), tz, socMin, versucht });
    const orte = Object.fromEntries(FEHLERORTE.map((ort) => [ort, '']));
    let warnung = '';
    for (const m of e.meldungen) {
      if (m.art === 'warnung') warnung = f.t(m.key, { min: f.zahlKurz(m.platzhalter.min) });
      else if (!orte[m.ort]) orte[m.ort] = f.t(m.key);
    }
    if (dienstFehler && !orte[dienstFehler.ort]) orte[dienstFehler.ort] = dienstFehler.text;
    for (const [ort, text] of Object.entries(orte)) zeige(q(`.fehler[data-ort="${ort}"]`), text);
    q('#feld-rueckkehr').classList.toggle('falsch', Boolean(orte.rueckkehr));
    q('#feld-strecke').classList.toggle('falsch', Boolean(orte.strecke));
    zeige(q('[data-warnung="ladestand"]'), !orte.ladestand && warnung ? html`${symbol('warnung')}<span>${warnung}</span>` : '');
    const konflikt = fahrerKonflikt(e.werte, w.fahrer, w.fahrzeug, andere, termin ? termin.entry : null, Date.now(), tz);
    const fahrerText = konflikt ? f.t('fahrer_doppelt', {
      fahrer: personName(z, w.fahrer) ?? '', datum: f.tag(konflikt.eigen.abfahrt),
      fahrzeug: fahrzeugTitel(z, konflikt.anderer.vehicle) ?? f.t('anderes_fahrzeug'),
    }) : '';
    q('#zeile-fahrer').hidden = !fahrerText;
    zeige(q('[data-ort="fahrer"]'), fahrerText ? html`${symbol('warnung')}<span>${fahrerText}</span>` : '');
    return { w, e };
  };

  // Die Termine der naechsten acht Wochen, fuer die Warnung zum Fahrer (Spec 7.2).
  panel.lesen({ type: 'meteo_volt/appointments', start: iso(jetzt), end: iso(jetzt + FAHRER_VORAUS) })
    .then((liste) => {
      andere = liste;
      if (scrim.isConnected) pruefenZeigen();
    })
    .catch(() => {});

  const fehlerZeigen = (fehler) => {
    const ort = fehler && fehlerOrt(fehler.translation_key);
    if (ort) {
      dienstFehler = { ort, text: panel.fehlerText(fehler) };
      pruefenZeigen();
      return;
    }
    schliesseAlle(panel);
    panel.melden(panel.fehlerText(fehler), null);
  };

  const senden = async (daten, umfang) => {
    let antwort;
    try {
      antwort = termin
        ? await panel.aufrufen('update_appointment', { entry: termin.entry, date: termin.date, ...(umfang ? { scope: umfang } : {}), ...daten }, true)
        : await panel.aufrufen('create_appointment', daten, true);
    } catch (fehler) {
      fehlerZeigen(fehler);
      return;
    }
    schliesseAlle(panel);
    const gespeichert = termin ? antwort.entries[0] : antwort.entry;
    if (daten.repeat === 'once') await ueberschneidungPruefen(panel, daten, gespeichert, antwort.step);
    else panel.melden(f.t('m_gespeichert'), antwort.step);
  };

  const speichern = () => {
    versucht = true;
    dienstFehler = null;
    const { w, e } = pruefenZeigen();
    if (!e.ok) return;
    const daten = {
      vehicle: w.fahrzeug, departure: w.abfahrt, return: w.rueckkehr, repeat: w.regel, distance_km: Number(w.km),
      driver: w.fahrer, soc: w.soc === '' ? null : Number(w.soc),
    };
    if (termin && termin.repeat !== 'once') oeffneUmfang(panel, 'speichern', termin, w, (umfang) => senden(daten, umfang));
    else senden(daten, null);
  };

  const loeschenSenden = async (umfang) => {
    try {
      const antwort = await panel.aufrufen('delete_appointment', { entry: termin.entry, date: termin.date, ...(umfang ? { scope: umfang } : {}) }, true);
      schliesseAlle(panel);
      panel.melden(f.t(!umfang ? 'm_geloescht' : umfang === 'this' ? 'm_abgesagt' : 'm_geloescht_n'), antwort.step);
    } catch (fehler) {
      schliesseAlle(panel);
      panel.melden(panel.fehlerText(fehler), null);
    }
  };

  regelOptionen();
  pruefenZeigen();
  scrim.addEventListener('input', (ev) => {
    const id = ev.target.id;
    dienstFehler = null;
    if (id === 'f-ab-datum' || id === 'f-ab-zeit') {
      const ab = zuMs(lokal('#f-ab-datum', '#f-ab-zeit'), tz);
      if (ab !== null) {
        const zu = naiv(ab + dauer * MINUTE, tz);
        q('#f-zu-datum').value = zu.slice(0, 10);
        q('#f-zu-zeit').value = zu.slice(11, 16);
      }
      if (id === 'f-ab-datum') regelOptionen();
    }
    if (id === 'f-zu-datum' || id === 'f-zu-zeit') {
      const ab = zuMs(lokal('#f-ab-datum', '#f-ab-zeit'), tz);
      const zu = zuMs(lokal('#f-zu-datum', '#f-zu-zeit'), tz);
      if (ab !== null && zu !== null) dauer = Math.round((zu - ab) / MINUTE);
    }
    pruefenZeigen();
  });
  scrim.addEventListener('click', (ev) => {
    const knopf = ev.target.closest('[data-d]');
    if (!knopf) return;
    if (knopf.dataset.d === 'schliessen') schliesseOberstes(panel);
    else if (knopf.dataset.d === 'speichern') speichern();
    else if (knopf.dataset.d === 'loeschen') {
      if (termin.repeat !== 'once') oeffneUmfang(panel, 'loeschen', termin, null, loeschenSenden);
      else loeschenSenden(null);
    }
  });
}

// Die Rueckfrage nach dem Umfang (Spec 7.4). werte: aus dem Formular, beim Loeschen null.
function oeffneUmfang(panel, art, termin, werte, weiter) {
  const { f, tz } = panel.kontext();
  const regelNeu = art === 'speichern' && werte.regel !== termin.repeat;
  const tagNeu = art === 'speichern' && werte.abfahrt.slice(0, 10) !== datumVon(termin.abfahrt, tz);
  const option = (wert, text, gewaehlt, gesperrt, klein) => html`<label class="${gesperrt ? 'aus' : ''}"><input type="radio" name="umfang" value="${wert}"${gewaehlt ? html` checked` : ''}${gesperrt ? html` disabled` : ''}><span>${text}${klein ? html`<small>${klein}</small>` : ''}</span></label>`;
  const scrim = oeffneDialog(panel, html`
    <div class="dialog schmal-dialog" role="dialog" aria-modal="true" aria-labelledby="umf-titel">
      <header><h2 id="umf-titel">${f.t(art === 'speichern' ? 'umfang_aendern' : 'umfang_loeschen')}</h2></header>
      <div class="koerper">
        <div class="optionen" role="radiogroup">
          ${option('this', f.t('umfang_this'), !regelNeu, regelNeu, regelNeu ? f.t('umfang_gesperrt') : '')}
          ${option('following', f.t('umfang_following'), regelNeu, false, '')}
          ${option('all', f.t('umfang_all'), false, false, '')}
        </div>
        <p class="hinweis" id="umf-hinweis" hidden>${f.t('umfang_zuruecksetzen')}</p>
      </div>
      <footer><button type="button" class="btn links" data-u="abbrechen">${f.t('abbrechen')}</button><button type="button" class="btn voll" data-u="ok">${f.t('ok')}</button></footer>
    </div>`, false);
  const wert = () => scrim.querySelector('input[name="umfang"]:checked').value;
  const hinweis = () => {
    scrim.querySelector('#umf-hinweis').hidden = !((regelNeu || tagNeu) && wert() !== 'this');
  };
  hinweis();
  scrim.addEventListener('change', hinweis);
  scrim.addEventListener('click', (ev) => {
    const knopf = ev.target.closest('[data-u]');
    if (!knopf) return;
    const umfang = wert();
    schliesseOberstes(panel);
    if (knopf.dataset.u === 'ok') weiter(umfang);
  });
}

// Nach dem Speichern eines einmaligen Termins (Spec 7.5).
async function ueberschneidungPruefen(panel, daten, eintrag, schritt) {
  const { f, tz } = panel.kontext();
  let andere = [];
  try {
    andere = termineAus(await panel.lesen({
      type: 'meteo_volt/appointments', start: iso(zuMs(daten.departure, tz)), end: iso(zuMs(daten.return, tz)), vehicle: daten.vehicle,
    })).filter((t) => t.entry !== eintrag);
  } catch {
    andere = [];
  }
  if (!andere.length) {
    panel.melden(f.t('m_gespeichert'), schritt);
    return;
  }
  const z = panel.kontext();
  const zeile = (t) => {
    const unten = [t.repeat === 'once' ? f.t('ue_einmalig') : f.regelKurz(t.repeat, t.date), personName(z, t.driver)].filter(Boolean);
    return html`<label><input type="checkbox" checked data-entry="${t.entry}" data-date="${t.date}"><span class="num"><b>${f.tag(t.abfahrt)}</b> ${f.t('von_bis', { von: f.zeit(t.abfahrt), bis: f.zeit(t.rueckkehr) })}${f.t('trenner')}${f.t('km', { km: t.distance_km })}
      <small>${unten.join(f.t('trenner'))}</small></span></label>`;
  };
  const scrim = oeffneDialog(panel, html`
    <div class="dialog schmal-dialog" role="dialog" aria-modal="true" aria-labelledby="ue-titel">
      <header><h2 id="ue-titel">${andere.length === 1 ? f.t('ue_titel_1') : f.t('ue_titel_n', { n: andere.length })}</h2></header>
      <div class="koerper">
        <p class="hinweis">${f.t('ue_frage', { fahrzeug: fahrzeugTitel(z, daten.vehicle) ?? '' })}</p>
        <div class="optionen">${andere.map(zeile)}</div>
      </div>
      <footer><button type="button" class="btn links" data-ue="behalten">${f.t('ue_behalten')}</button><button type="button" class="btn voll" data-ue="absagen"></button></footer>
    </div>`, false);
  const knopf = scrim.querySelector('[data-ue="absagen"]');
  const gewaehlt = () => [...scrim.querySelectorAll('input:checked')];
  const zaehlen = () => {
    const n = gewaehlt().length;
    knopf.textContent = n === 1 ? f.t('ue_absagen_1') : f.t('ue_absagen_n', { n });
    knopf.disabled = n === 0;
  };
  zaehlen();
  scrim.addEventListener('change', zaehlen);
  scrim.addEventListener('click', async (ev) => {
    const ziel = ev.target.closest('[data-ue]');
    if (!ziel) return;
    const termine = gewaehlt().map((e) => ({ entry: e.dataset.entry, date: e.dataset.date }));
    schliesseOberstes(panel);
    if (ziel.dataset.ue === 'behalten') {
      panel.melden(f.t('m_gespeichert'), schritt);
      return;
    }
    try {
      const antwort = await panel.aufrufen('cancel_appointments', { appointments: termine, step: schritt }, true);
      panel.melden(termine.length === 1 ? f.t('m_gespeichert_abgesagt_1') : f.t('m_gespeichert_abgesagt_n', { n: termine.length }), antwort.step);
    } catch (fehler) {
      panel.melden(panel.fehlerText(fehler), null);
    }
  });
}
