// Das Panel Meteo-Volt in der Seitenleiste von Home Assistant. Spec C8.
//
// Home Assistant setzt hass, narrow, route und panel (Frontend 20260325.6,
// ha-panel-custom). Ein neues hass kommt mit jeder Zustandsaenderung; das
// Panel zeichnet deshalb nur neu, wenn sich Sprache, Zeitzone oder Hell und
// Dunkel aendern, sonst nach seinen eigenen Daten (Spec Abschnitt 4).
//
// Gelesen wird ueber die Websocket-Befehle aus C3, geschrieben ueber
// call_service. Jede Meldung von meteo_volt/subscribe liest den betroffenen
// Teil neu, dazu alles zu Beginn jeder Viertelstunde (Spec Abschnitt 5).

import { fahrzeugHtml, uebersichtHtml } from './ansichten.js';
import {
  achseSvg, bindeTooltip, planChartSvg, preisChartSvg, preisStreifenSvg, streifenSvg, unterwegs,
} from './diagramme.js';
import { oeffneTermin, schliesseOberstes } from './dialoge.js';
import { formatierer } from './format.js';
import { html, vertraut } from './html.js';
import { planAbJetzt, planende, termineAus } from './plan.js';
import { preisSlots, tageswerte } from './preise.js';
import { preiseHtml } from './preisansicht.js';
import { STIL } from './stil.js';
import { symbol } from './symbole.js';
import { TEXTE, sprache, text } from './texte.js';
import { MINUTE, ausIso, datumVon, iso, plusTage, tagesbeginn } from './zeit.js';

const VIERTELSTUNDE = 15 * MINUTE;
const SCHMAL = 720;

class MeteoVoltPanel extends HTMLElement {
  constructor() {
    super();
    this._ui = {
      tab: 'uebersicht', filter: 'alle', tageUebersicht: 7, tageFahrzeug: 21, bereich: 'alles',
      preisart: 'kunde', fensterStunden: 2, alleBloecke: false, planLaeuft: false,
    };
    this._daten = { site: null, preise: null, plaene: new Map(), termine: [] };
    this._zustand = 'laedt';
    this._offen = new Set();
    this._sp = 'de';
    this._tz = 'UTC';
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = String(html`<style>${vertraut(STIL)}</style>
      <div class="wurzel">
        <header class="toolbar">
          <button class="iconbtn menue" type="button" data-aktion="menue">${symbol('menue')}</button>
          <div class="titel">Meteo-Volt</div>
          <span class="planstand num"></span>
          <button class="iconbtn neuplanen" type="button" data-aktion="neuplanen">${symbol('neuPlanen')}</button>
        </header>
        <nav class="tabs" role="tablist" hidden></nav>
        <main class="content"></main>
        <button class="fab" type="button" data-aktion="neu" hidden>${symbol('plus')}<span></span></button>
        <div class="toast" hidden></div>
        <div class="dialoge"></div>
      </div>`);
    this._wurzel = this.shadowRoot.querySelector('.wurzel');
    this._inhalt = this.shadowRoot.querySelector('.content');
    this.shadowRoot.addEventListener('click', (ev) => this._klick(ev));
    this.shadowRoot.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') schliesseOberstes(this);
    });
    this._groesse = new ResizeObserver(() => {
      const schmal = this.clientWidth < SCHMAL;
      if (schmal !== this._wurzel.classList.contains('schmal')) this._wurzel.classList.toggle('schmal', schmal);
      cancelAnimationFrame(this._rahmen);
      this._rahmen = requestAnimationFrame(() => this._diagramme());
    });
  }

  // --- Was Home Assistant setzt --------------------------------------------------

  set hass(hass) {
    const alt = this._hass;
    this._hass = hass;
    const sp = sprache(hass.locale && hass.locale.language);
    const tz = (hass.config && hass.config.time_zone) || 'UTC';
    this.toggleAttribute('dunkel', Boolean(hass.themes && hass.themes.darkMode));
    const anders = !alt || sp !== this._sp || tz !== this._tz || hass.dockedSidebar !== alt.dockedSidebar;
    this._sp = sp;
    this._tz = tz;
    if (!this._laeuft) this._starten();
    else if (anders) this._zeichnen();
  }

  get hass() {
    return this._hass;
  }

  set narrow(wert) {
    this._narrow = wert;
    if (this._hass) this._werkzeugleiste(this._kontext());
  }

  set route(route) {
    this._route = route;
    const teile = ((route && route.path) || '').split('/').filter(Boolean);
    const tab = teile[0] === 'prices' ? 'preise' : teile[0] === 'vehicle' && teile[1] ? teile[1] : 'uebersicht';
    if (tab !== this._ui.tab) this._tabSetzen(tab);
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    this._verbunden = true;
    this._groesse.observe(this);
    this._starten();
  }

  disconnectedCallback() {
    this._verbunden = false;
    this._groesse.disconnect();
    this._beenden();
  }

  // --- Lesen und Aktualisieren, Spec Abschnitt 5 ------------------------------------

  async _starten() {
    if (this._laeuft || !this._verbunden || !this._hass) return;
    this._laeuft = true;
    this._conn = this._hass.connection;
    this._bereit = () => this._allesLesen();
    this._conn.addEventListener('ready', this._bereit);
    this._zeitplan();
    this._zeichnen();
    await this._allesLesen();
  }

  _beenden() {
    this._laeuft = false;
    if (this._conn && this._bereit) this._conn.removeEventListener('ready', this._bereit);
    if (this._abo) this._abo();
    this._abo = null;
    clearTimeout(this._uhr);
    clearTimeout(this._buendel);
    clearTimeout(this._toastUhr);
  }

  async _abonnieren() {
    if (this._abo || this._abonniert) return;
    this._abonniert = true;
    try {
      const abo = await this._conn.subscribeMessage((meldung) => this._gemeldet(meldung), { type: 'meteo_volt/subscribe' });
      if (this._laeuft) this._abo = abo;
      else abo();
    } catch {
      // Ohne Standort gibt es nichts zu melden. Die naechste Viertelstunde versucht es wieder.
    } finally {
      this._abonniert = false;
    }
  }

  _zeitplan() {
    clearTimeout(this._uhr);
    const jetzt = Date.now();
    const naechste = Math.floor(jetzt / VIERTELSTUNDE) * VIERTELSTUNDE + VIERTELSTUNDE + 5000;
    this._uhr = setTimeout(async () => {
      if (!this._laeuft) return;
      await this._allesLesen();
      this._zeitplan();
    }, naechste - jetzt);
  }

  _gemeldet(was) {
    this._offen.add(was);
    clearTimeout(this._buendel);
    this._buendel = setTimeout(() => this._nachlesen(), 150);
  }

  async _nachlesen() {
    const offen = this._offen;
    this._offen = new Set();
    if (offen.has('site')) await this._siteLesen();
    const lesen = [];
    if (offen.has('prices')) lesen.push(this._preiseLesen());
    if (offen.has('plan') || offen.has('planning') || offen.has('site')) lesen.push(this._plaeneLesen());
    await Promise.all(lesen);
    if (offen.has('appointments') || offen.has('plan') || offen.has('site')) await this._termineLesen();
    this._zeichnen();
  }

  _ws(nachricht) {
    return this._hass.connection.sendMessagePromise(nachricht);
  }

  async _siteLesen() {
    try {
      this._daten.site = await this._ws({ type: 'meteo_volt/site' });
      this._zustand = 'bereit';
    } catch {
      this._daten.site = null;
      this._zustand = 'nichtGeladen';
    }
  }

  async _preiseLesen() {
    try {
      this._daten.preise = await this._ws({ type: 'meteo_volt/prices' });
    } catch {
      this._daten.preise = null;
    }
  }

  async _plaeneLesen() {
    const fahrzeuge = (this._daten.site && this._daten.site.vehicles) || [];
    const plaene = await Promise.all(fahrzeuge.map((v) => this._ws({ type: 'meteo_volt/plan', vehicle: v.vehicle }).catch(() => null)));
    this._daten.plaene = new Map(fahrzeuge.map((v, i) => [v.vehicle, plaene[i]]));
  }

  // Alle Fahrzeuge, ab jetzt bis zum spaeteren von Planende und Ende der gezeigten Liste.
  async _termineLesen() {
    if (!this._daten.site) return;
    const jetzt = Date.now();
    const tage = this._ui.tab === 'uebersicht' ? this._ui.tageUebersicht : this._ui.tab === 'preise' ? 1 : this._ui.tageFahrzeug;
    const liste = tagesbeginn(plusTage(datumVon(jetzt, this._tz), tage), this._tz);
    const ende = Math.max(planende([...this._daten.plaene.values()], jetzt) ?? 0, liste);
    try {
      this._daten.termine = termineAus(await this._ws({ type: 'meteo_volt/appointments', start: iso(jetzt), end: iso(ende) }));
    } catch {
      this._daten.termine = [];
    }
  }

  async _allesLesen() {
    await this._siteLesen();
    if (this._daten.site) {
      await Promise.all([this._preiseLesen(), this._plaeneLesen()]);
      await this._termineLesen();
      this._abonnieren();
    }
    this._zeichnen();
  }

  // --- Fuer die Dialoge -----------------------------------------------------------

  kontext() {
    return this._z || this._kontext();
  }

  lesen(nachricht) {
    return this._ws(nachricht);
  }

  async aufrufen(service, daten, mitAntwort) {
    const nachricht = { type: 'call_service', domain: 'meteo_volt', service, service_data: daten };
    if (mitAntwort) nachricht.return_response = true;
    const ergebnis = await this._ws(nachricht);
    return mitAntwort ? ergebnis.response : ergebnis;
  }

  fehlerText(fehler) {
    const schluessel = fehler && fehler.translation_key;
    if (schluessel && schluessel in TEXTE[this._sp]) return text(this._sp, schluessel, fehler.translation_placeholders || {});
    return (fehler && fehler.message) || String(fehler);
  }

  dialogWurzel() {
    return this.shadowRoot.querySelector('.dialoge');
  }

  tabFahrzeug() {
    const fahrzeuge = (this._daten.site && this._daten.site.vehicles) || [];
    return fahrzeuge.some((v) => v.vehicle === this._ui.tab) ? this._ui.tab : null;
  }

  melden(inhalt, schritt) {
    const toast = this.shadowRoot.querySelector('.toast');
    const f = formatierer(this._sp, this._tz);
    toast.innerHTML = String(html`<span>${inhalt}</span>${schritt ? html`<button type="button" data-aktion="rueckgaengig">${f.t('rueckgaengig')}</button>` : ''}`);
    this._schritt = schritt || null;
    toast.hidden = false;
    clearTimeout(this._toastUhr);
    this._toastUhr = setTimeout(() => {
      toast.hidden = true;
    }, 5000);
  }

  // --- Handlungen -----------------------------------------------------------------

  _klick(ev) {
    const ziel = ev.target.closest('[data-aktion]');
    if (!ziel || !this._wurzel.contains(ziel)) return;
    const { aktion, id, wert, was, entry, date } = ziel.dataset;
    if (aktion === 'tab') this._navigieren(id);
    else if (aktion === 'filter') this._setzen({ filter: id });
    else if (aktion === 'bereich') this._setzen({ bereich: wert });
    else if (aktion === 'preisart') this._setzen({ preisart: wert });
    else if (aktion === 'fenster') this._setzen({ fensterStunden: Number(wert) });
    else if (aktion === 'bloecke') this._setzen({ alleBloecke: !this._ui.alleBloecke });
    else if (aktion === 'risiko') this._schreiben('set_risk', { risk: Number(wert) });
    else if (aktion === 'mehr') this._mehr(was);
    else if (aktion === 'neuplanen') this._neuPlanen();
    else if (aktion === 'menue') this.dispatchEvent(new CustomEvent('hass-toggle-menu', { bubbles: true, composed: true }));
    else if (aktion === 'rueckgaengig') this._rueckgaengig();
    else if (aktion === 'neu') oeffneTermin(this, null);
    else if (aktion === 'termin') {
      const termin = this._daten.termine.find((t) => t.entry === entry && t.date === date);
      if (termin) oeffneTermin(this, termin);
    }
  }

  _setzen(werte) {
    Object.assign(this._ui, werte);
    this._zeichnen();
  }

  async _mehr(was) {
    if (was === 'uebersicht') this._ui.tageUebersicht += 7;
    else this._ui.tageFahrzeug += 21;
    await this._termineLesen();
    this._zeichnen();
  }

  _navigieren(tab) {
    const pfad = tab === 'uebersicht' ? 'overview' : tab === 'preise' ? 'prices' : `vehicle/${tab}`;
    window.history.pushState(null, '', `${(this._route && this._route.prefix) || '/meteo-volt'}/${pfad}`);
    window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } }));
    this._tabSetzen(tab);
  }

  async _tabSetzen(tab) {
    this._ui.tab = tab;
    this._ui.tageFahrzeug = 21;
    this._ui.alleBloecke = false;
    this._inhalt.scrollTop = 0;
    this._zeichnen();
    if (this._laeuft && this._daten.site) {
      await this._termineLesen();
      this._zeichnen();
    }
  }

  async _schreiben(service, daten) {
    try {
      await this.aufrufen(service, daten, false);
    } catch (fehler) {
      this.melden(this.fehlerText(fehler), null);
    }
  }

  async _neuPlanen() {
    if (this._ui.planLaeuft) return;
    this._ui.planLaeuft = true;
    this._werkzeugleiste(this._kontext());
    await this._schreiben('replan', {});
    this._ui.planLaeuft = false;
    this._zeichnen();
  }

  async _rueckgaengig() {
    const schritt = this._schritt;
    this._schritt = null;
    this.shadowRoot.querySelector('.toast').hidden = true;
    if (schritt) await this._schreiben('undo', { step: schritt });
  }

  // --- Zeichnen ---------------------------------------------------------------------

  _kontext() {
    const jetzt = Date.now();
    const site = this._daten.site;
    const fahrzeuge = (site && site.vehicles) || [];
    const netzentgelt = site && site.grid_fees > 0 ? site.grid_fees : null;
    const plaene = [...this._daten.plaene.values()].filter(Boolean);
    return {
      f: formatierer(this._sp, this._tz),
      jetzt,
      tz: this._tz,
      ui: this._ui,
      fahrzeuge,
      personen: (site && site.persons) || [],
      risiko: (site && site.risk) || 2,
      netzentgelt,
      gebuehr: netzentgelt !== null && this._ui.preisart === 'kunde' ? netzentgelt : 0,
      plaene: this._daten.plaene,
      fenster: new Map(fahrzeuge.map((v) => [v.vehicle, planAbJetzt(this._daten.plaene.get(v.vehicle), jetzt, v.soc_pct)])),
      termine: this._daten.termine,
      planende: planende(plaene, jetzt),
      preise: preisSlots(this._daten.preise, jetzt),
      preiseRoh: this._daten.preise || {},
      planFehler: (plaene.find((p) => p.error) || {}).error || null,
      planung: this._ui.planLaeuft || plaene.some((p) => p.planning),
      berechnet: ausIso((plaene.find((p) => p.computed_at) || {}).computed_at),
    };
  }

  _werkzeugleiste(z) {
    const { f } = z;
    const menue = this.shadowRoot.querySelector('.menue');
    menue.hidden = !(this._narrow || (this._hass && this._hass.dockedSidebar === 'always_hidden'));
    menue.setAttribute('aria-label', f.t('seitenleiste'));
    const mitPlan = this._zustand === 'bereit' && z.fahrzeuge.length > 0;
    const stand = this.shadowRoot.querySelector('.planstand');
    const knopf = this.shadowRoot.querySelector('.neuplanen');
    stand.hidden = !mitPlan;
    knopf.hidden = !mitPlan;
    stand.textContent = z.planung ? f.t('plan_laeuft')
      : z.berechnet !== null ? f.t('plan_von', { zeit: f.zeitMitTag(z.berechnet, z.jetzt) }) : f.t('kein_plan');
    stand.classList.toggle('laeuft', z.planung);
    knopf.classList.toggle('drehen', z.planung);
    knopf.disabled = z.planung;
    knopf.setAttribute('aria-label', f.t('neu_planen'));
    knopf.title = f.t('neu_planen');
  }

  _zeichnen() {
    if (!this._hass) return;
    const z = this._kontext();
    this._z = z;
    const { f } = z;
    this._werkzeugleiste(z);
    const tabs = this.shadowRoot.querySelector('.tabs');
    const fab = this.shadowRoot.querySelector('.fab');
    if (this._zustand !== 'bereit') {
      tabs.hidden = true;
      fab.hidden = true;
      this._inhalt.innerHTML = String(html`<div class="zustand">${f.t(this._zustand === 'laedt' ? 'laedt' : 'nicht_geladen')}</div>`);
      return;
    }
    if (!z.fahrzeuge.length) this._ui.tab = 'preise';
    else if (this._ui.tab !== 'uebersicht' && this._ui.tab !== 'preise' && !z.fahrzeuge.some((v) => v.vehicle === this._ui.tab)) {
      this._ui.tab = 'uebersicht';
    }
    const liste = [
      { id: 'uebersicht', name: f.t('tab_uebersicht'), sym: 'raster' },
      { id: 'preise', name: f.t('tab_preise'), sym: 'diagramm' },
      ...z.fahrzeuge.map((v) => ({ id: v.vehicle, name: v.title, sym: 'auto' })),
    ];
    tabs.hidden = !z.fahrzeuge.length;
    tabs.setAttribute('aria-label', f.t('tabs'));
    tabs.innerHTML = String(html`${liste.map((tab) => html`<button type="button" role="tab" aria-selected="${this._ui.tab === tab.id}" data-aktion="tab" data-id="${tab.id}">${symbol(tab.sym)}<span>${tab.name}</span></button>`)}`);
    fab.hidden = !z.fahrzeuge.length || this._ui.tab === 'preise';
    fab.querySelector('span').textContent = f.t('termin_knopf');
    const fz = z.fahrzeuge.find((v) => v.vehicle === this._ui.tab);
    this._inhalt.innerHTML = String(this._ui.tab === 'preise' ? preiseHtml(z) : fz ? fahrzeugHtml(z, fz) : uebersichtHtml(z));
    this._diagramme();
  }

  _diagramme() {
    const z = this._z;
    if (!z || this._zustand !== 'bereit') return;
    const { f } = z;
    const schmal = this._wurzel.classList.contains('schmal');
    this.shadowRoot.querySelectorAll('.planchart[data-fz]').forEach((box, i) => {
      const fz = z.fahrzeuge.find((v) => v.vehicle === box.dataset.fz);
      const fenster = z.fenster.get(box.dataset.fz);
      if (!fz || !fenster || !box.clientWidth) return;
      const termine = z.termine.filter((t) => t.vehicle === fz.vehicle);
      const d = { schluessel: `p${i}`, fz, name: fz.title, fenster, termine, bereich: z.ui.bereich };
      const { svg, geo } = planChartSvg(d, box.clientWidth, schmal, f, z.gebuehr);
      box.innerHTML = String(html`${svg}<div class="tooltip" hidden></div>`);
      bindeTooltip(box, geo, (s) => this._planTipp(z, s, termine));
    });
    const erster = z.fahrzeuge.map((v) => z.fenster.get(v.vehicle)).find(Boolean);
    this.shadowRoot.querySelectorAll('.h-strip').forEach((box, i) => {
      if (!box.clientWidth) return;
      if (box.dataset.art === 'preis') {
        if (erster) box.innerHTML = String(preisStreifenSvg(erster, box.clientWidth, f, z.gebuehr));
        return;
      }
      const fz = z.fahrzeuge.find((v) => v.vehicle === box.dataset.fz);
      const fenster = z.fenster.get(box.dataset.fz);
      if (!fz || !fenster) return;
      const d = { schluessel: `s${i}`, fz, fenster, termine: z.termine.filter((t) => t.vehicle === fz.vehicle) };
      box.innerHTML = String(streifenSvg(d, box.clientWidth, f));
    });
    this.shadowRoot.querySelectorAll('.h-achse').forEach((box) => {
      if (box.clientWidth && erster) box.innerHTML = String(achseSvg(erster.start, erster.ende, box.clientWidth, f));
    });
    const preisBox = this.shadowRoot.querySelector('.preischart');
    if (preisBox && preisBox.clientWidth && z.preise.length) {
      const d = { slots: z.preise, bereich: z.ui.bereich, tage: tageswerte(z.preise, z.ui.fensterStunden, z.tz, z.gebuehr) };
      const { svg, geo } = preisChartSvg(d, preisBox.clientWidth, schmal, f, z.gebuehr);
      preisBox.innerHTML = String(html`${svg}<div class="tooltip" hidden></div>`);
      bindeTooltip(preisBox, geo, (s) => this._preisTipp(z, s));
    }
  }

  _planTipp(z, s, termine) {
    const { f } = z;
    const zeilen = [
      html`<b>${f.tagZeit(s.t)}</b>`,
      f.t('tip_ladestand', { soc: f.prozent(s.soc) }),
      f.t(s.boerse ? 'tip_preis' : 'tip_preis_prognose', { preis: f.ct(s.preis + z.gebuehr) }),
    ];
    if (unterwegs(s, termine)) zeilen.push(f.t('tip_unterwegs'));
    else if (s.laden) zeilen.push(html`<span class="tip-laden">${f.t('tip_laedt', { kw: f.kw(s.kw ?? 0), eur: f.eur(s.kosten + z.gebuehr * s.kwh) })}</span>`);
    return html`${zeilen.map((zeile, i) => html`${i ? html`<br>` : ''}${zeile}`)}`;
  }

  _preisTipp(z, s) {
    const { f } = z;
    const g = z.gebuehr;
    const zeilen = [html`<b>${f.tagZeit(s.t)}</b>`];
    if (s.boerse) zeilen.push(f.t('p_tip_boerse', { preis: f.ct(s.q50 + g) }));
    else {
      zeilen.push(f.t('p_tip_prognose', { preis: f.ct(s.q50 + g) }));
      zeilen.push(f.t('p_tip_spanne', { von: f.ctKurz(s.q10 + g), bis: f.ctKurz(s.q90 + g) }));
    }
    return html`${zeilen.map((zeile, i) => html`${i ? html`<br>` : ''}${zeile}`)}`;
  }
}

if (!customElements.get('meteo-volt-panel')) customElements.define('meteo-volt-panel', MeteoVoltPanel);
