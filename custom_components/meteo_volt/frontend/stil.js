// Der Stil des Panels, aus dem Entwurf. Spec C8 Abschnitt 4.
//
// Flaechen, Text und Linien kommen aus den Theme-Variablen von Home Assistant,
// die Farben der Diagramme aus dem Entwurf. Das Attribut dunkel setzt das
// Panel nach hass.themes.darkMode. Unter 720 px Breite traegt die Wurzel die
// Klasse schmal: Tabs unten, der Termin als Vollbild.

export const STIL = `
:host {
  display: block; height: 100%;
  --mv-bg: var(--primary-background-color, #f5f6f7);
  --mv-card: var(--card-background-color, var(--ha-card-background, #ffffff));
  --mv-text: var(--primary-text-color, #212121);
  --mv-text2: var(--secondary-text-color, #6b7075);
  --mv-divider: var(--divider-color, #e3e5e8);
  --mv-primary: var(--primary-color, #03a9f4);
  --mv-primary-soft: color-mix(in srgb, var(--mv-primary) 14%, transparent);
  --mv-error: var(--error-color, #c62828);
  --mv-soc: #039be5; --mv-laden: #2e9d4f; --mv-laden-soft: rgba(46, 157, 79, .13);
  --mv-preis: #6b7075; --mv-weg: #d9dde1; --mv-grid: #eef0f2; --mv-band: rgba(3, 169, 244, .16);
  --mv-warn: #b26a00; --mv-warn-icon: #f59300;
  --mv-scrim: rgba(20, 24, 28, .45); --mv-shadow: 0 8px 28px rgba(0, 0, 0, .18);
}
:host([dunkel]) {
  --mv-soc: #29b6f6; --mv-laden: #4caf50; --mv-laden-soft: rgba(76, 175, 80, .17);
  --mv-preis: #aab0b6; --mv-weg: #383c41; --mv-grid: #25282c; --mv-band: rgba(41, 182, 246, .2);
  --mv-warn: #ffb74d; --mv-warn-icon: #ffa726;
  --mv-scrim: rgba(0, 0, 0, .6); --mv-shadow: 0 8px 28px rgba(0, 0, 0, .6);
}
* { box-sizing: border-box; }
.wurzel { position: relative; height: 100%; display: flex; flex-direction: column; overflow: hidden;
  background: var(--mv-bg); color: var(--mv-text); font-size: 14px; line-height: 1.4; }
button, input, select { font: inherit; color: inherit; }
button { cursor: pointer; }
:focus-visible { outline: 2px solid var(--mv-primary); outline-offset: 2px; }
svg.i { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round;
  stroke-linejoin: round; flex: none; }
.num { font-variant-numeric: tabular-nums; }
[hidden] { display: none !important; }

.toolbar { height: var(--header-height, 56px); flex: none; display: flex; align-items: center; gap: 8px;
  padding: 0 8px 0 16px; background: var(--app-header-background-color, var(--mv-bg));
  color: var(--app-header-text-color, var(--mv-text));
  border-bottom: var(--app-header-border-bottom, 1px solid var(--mv-divider)); }
.schmal .toolbar { padding-left: 4px; }
.toolbar .titel { font-size: 20px; font-weight: 400; flex: 1; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.iconbtn { width: 40px; height: 40px; border-radius: 50%; border: 0; background: none; display: grid;
  place-items: center; color: inherit; }
.iconbtn:hover { background: var(--mv-primary-soft); }
.iconbtn[disabled] { cursor: default; opacity: .6; }
.planstand { color: var(--mv-text2); font-size: 13px; white-space: nowrap; }
.planstand.laeuft { color: var(--mv-primary); }
.drehen svg { animation: dreh 1s linear infinite; }
@keyframes dreh { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .drehen svg { animation: none; } }

.tabs { flex: none; display: flex; gap: 4px; padding: 0 12px; border-bottom: 1px solid var(--mv-divider);
  background: var(--mv-bg); overflow-x: auto; }
.tabs button { border: 0; background: none; padding: 12px 14px 10px; color: var(--mv-text2);
  border-bottom: 2px solid transparent; display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.tabs button[aria-selected="true"] { color: var(--mv-primary); border-bottom-color: var(--mv-primary); font-weight: 500; }
.wurzel:not(.schmal) .tabs svg { display: none; }
.schmal .tabs { order: 3; border-bottom: 0; border-top: 1px solid var(--mv-divider); padding: 0 4px;
  justify-content: space-around; background: var(--mv-card); }
.schmal .tabs button { flex: 1; flex-direction: column; gap: 2px; padding: 8px 4px 10px; font-size: 12px;
  border-bottom: 0; border-top: 2px solid transparent; min-width: 72px; }
.schmal .tabs button[aria-selected="true"] { border-top-color: var(--mv-primary); }

.content { flex: 1; overflow-y: auto; padding: 16px 16px 96px; }
.spalte { max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
.zustand { padding: 48px 16px; text-align: center; color: var(--mv-text2); }
.warnzeile { display: flex; gap: 8px; align-items: flex-start; padding: 10px 14px; border-radius: 12px;
  background: color-mix(in srgb, var(--mv-warn-icon) 14%, transparent); color: var(--mv-warn); }
.warnzeile svg.i { width: 18px; height: 18px; color: var(--mv-warn-icon); margin-top: 1px; }

.karte { background: var(--mv-card); border: 1px solid var(--mv-divider); border-radius: 12px; }
.abschnitt { font-size: 13px; font-weight: 500; color: var(--mv-text2); letter-spacing: .02em; margin: 4px 4px -8px; }
.risiko { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.risiko .zeile { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }
.risiko .zeile strong { font-weight: 500; }
.hinweis { color: var(--mv-text2); font-size: 13px; margin: 0; }
.seg { display: inline-flex; border: 1px solid var(--mv-divider); border-radius: 999px; overflow: hidden;
  background: var(--mv-card); }
.seg button { border: 0; background: none; padding: 7px 14px; color: var(--mv-text2); }
.seg button[aria-pressed="true"] { background: var(--mv-primary-soft); color: var(--mv-primary); font-weight: 500; }
.seg.klein button { padding: 5px 11px; font-size: 13px; }
.status { color: var(--mv-text2); display: flex; flex-wrap: wrap; gap: 4px 12px; }
.status .warnung { color: var(--mv-warn); }

.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { border: 1px solid var(--mv-divider); background: var(--mv-card); border-radius: 999px; padding: 6px 12px;
  display: inline-flex; align-items: center; gap: 6px; }
.chip[aria-pressed="true"] { background: var(--mv-primary-soft); border-color: var(--mv-primary);
  color: var(--mv-primary); font-weight: 500; }
.chip svg.i { width: 16px; height: 16px; }

.agenda { overflow: clip; }
.tag { position: sticky; top: -16px; z-index: 1; background: var(--mv-card); padding: 10px 16px 6px;
  font-size: 13px; font-weight: 500; color: var(--mv-text2); border-top: 1px solid var(--mv-divider); }
.agenda .tag:first-child { border-top: 0; }
.tag.heute { color: var(--mv-primary); }
.termin { width: 100%; border: 0; background: none; text-align: left; display: grid;
  grid-template-columns: 64px 1fr auto; gap: 2px 12px; padding: 10px 16px; border-top: 1px solid var(--mv-divider); }
.tag + .termin { border-top: 0; }
.termin:hover { background: var(--mv-primary-soft); }
.termin .zeit { display: flex; flex-direction: column; }
.termin .zeit b { font-weight: 500; }
.termin .zeit span { color: var(--mv-text2); font-size: 13px; }
.termin .mitte { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.termin .z1 { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 10px; }
.termin .fzname { font-weight: 500; }
.meta { color: var(--mv-text2); display: inline-flex; align-items: center; gap: 4px; }
.meta svg.i { width: 15px; height: 15px; }
.plan { color: var(--mv-text2); }
.warn { color: var(--mv-warn); display: flex; align-items: flex-start; gap: 6px; }
.warn svg.i { width: 16px; height: 16px; margin-top: 1px; color: var(--mv-warn-icon); }
.termin .km { font-weight: 500; white-space: nowrap; }
.grenze { padding: 10px 16px; background: var(--mv-bg); color: var(--mv-text2); font-size: 13px;
  border-top: 1px solid var(--mv-divider); display: flex; align-items: center; gap: 8px; }
.grenze::before, .grenze::after { content: ""; flex: 1; height: 1px; background: var(--mv-divider); }
.mehr { border: 0; background: none; color: var(--mv-primary); font-weight: 500; padding: 12px 16px; width: 100%;
  border-top: 1px solid var(--mv-divider); }
.leer { padding: 28px 16px; text-align: center; color: var(--mv-text2); }

.fab { position: absolute; right: 20px; bottom: 20px; z-index: 3; border: 0; border-radius: 16px;
  background: var(--mv-primary); color: var(--text-primary-color, #fff); height: 52px; padding: 0 20px 0 16px;
  display: flex; align-items: center; gap: 8px; font-weight: 500; box-shadow: 0 4px 12px rgba(0, 0, 0, .25); }
.schmal .fab { bottom: 76px; right: 16px; }
.toast { position: absolute; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 6; background: #323232;
  color: #fff; border-radius: 8px; padding: 10px 16px; display: flex; align-items: center; gap: 16px;
  max-width: calc(100% - 32px); box-shadow: var(--mv-shadow); }
.schmal .toast { bottom: 84px; }
.toast button { border: 0; background: none; color: #80d8ff; font-weight: 500; padding: 4px; }

.scrim { position: absolute; inset: 0; z-index: 5; background: var(--mv-scrim); display: grid; place-items: center;
  padding: 16px; }
.dialog { background: var(--mv-card); border-radius: 16px; width: 100%; max-width: 520px; max-height: 100%;
  display: flex; flex-direction: column; box-shadow: var(--mv-shadow); }
.dialog.schmal-dialog { max-width: 440px; }
.dialog header { display: flex; align-items: center; gap: 8px; padding: 18px 20px 8px; }
.dialog h2 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; }
.dialog .koerper { container-type: inline-size; padding: 8px 20px 12px; overflow-y: auto; display: flex;
  flex-direction: column; gap: 14px; }
.dialog footer { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 12px 20px 18px; }
.dialog footer .links { margin-right: auto; }
.schmal .scrim.voll { padding: 0; place-items: stretch; }
.schmal .scrim.voll .dialog { max-width: none; border-radius: 0; height: 100%; }
.schmal .scrim.voll header { padding: 8px 8px 8px 4px; border-bottom: 1px solid var(--mv-divider); }
.schmal .scrim.voll footer { display: none; }
.dialog .kopfspeichern { display: none; }
.schmal .scrim.voll .kopfspeichern { display: inline-flex; }
.dialog .unten-loeschen { display: none; }
.schmal .scrim.voll .unten-loeschen { display: flex; }

.btn { border: 0; border-radius: 20px; padding: 9px 18px; font-weight: 500; background: none; color: var(--mv-primary);
  display: inline-flex; align-items: center; gap: 6px; }
.btn:hover { background: var(--mv-primary-soft); }
.btn.voll { background: var(--mv-primary); color: var(--text-primary-color, #fff); }
.btn.voll:hover { filter: brightness(1.1); }
.btn.rot { color: var(--mv-error); }
.btn[disabled] { opacity: .45; cursor: default; }

.feld { display: flex; flex-direction: column; gap: 4px; }
.feld label, .feld .label { font-size: 12px; color: var(--mv-text2); }
.feld input, .feld select { width: 100%; min-width: 0; height: 48px; border: 1px solid var(--mv-divider);
  border-radius: 8px; background: var(--mv-bg); padding: 0 12px; }
.feld input:focus, .feld select:focus { outline: 2px solid var(--mv-primary); outline-offset: -1px; }
.paar { display: grid; grid-template-columns: 1.25fr 1fr; gap: 8px; }
.zwei { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@container (max-width: 340px) { .zwei { grid-template-columns: 1fr; } }
.feld .fehler { color: var(--mv-error); font-size: 13px; }
.feld .warnhinweis { color: var(--mv-warn); font-size: 13px; display: flex; gap: 6px; }
.feld .warnhinweis svg.i { width: 16px; height: 16px; color: var(--mv-warn-icon); margin-top: 1px; }
.feld.falsch input { border-color: var(--mv-error); }
.feld.warnt input { border-color: var(--mv-warn-icon); }

.optionen { display: flex; flex-direction: column; gap: 2px; }
.optionen label { display: flex; align-items: center; gap: 12px; padding: 10px 4px; border-radius: 8px; }
.optionen label:hover { background: var(--mv-primary-soft); }
.optionen input { width: 20px; height: 20px; accent-color: var(--mv-primary); }
.optionen label.aus { color: var(--mv-text2); opacity: .6; }
.optionen small { display: block; color: var(--mv-text2); }

.plankarte { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.kennzahlen { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.schmal .kennzahlen { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.kz { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.kz b { font-size: 22px; font-weight: 500; white-space: nowrap; }
.kz span { font-size: 12px; color: var(--mv-text2); }
.chartkopf { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; }
.steuerung { display: flex; flex-wrap: wrap; gap: 8px; }
.legende { display: flex; flex-wrap: wrap; gap: 4px 12px; color: var(--mv-text2); font-size: 12px; }
.legende span { display: inline-flex; align-items: center; gap: 6px; }
.sw { display: inline-block; width: 16px; height: 10px; border-radius: 2px; }
.sw-soc { height: 3px; background: var(--mv-soc); }
.sw-laden { background: var(--mv-laden); }
.sw-weg { background: repeating-linear-gradient(45deg, var(--mv-weg) 0 3px, transparent 3px 6px);
  outline: 1px solid var(--mv-divider); }
.sw-preis { height: 2px; border-radius: 0; background: var(--mv-preis); }
.sw-prognose { height: 0; border-radius: 0; border-top: 2px dashed var(--mv-preis); }
.sw-preis.stark { background: var(--mv-primary); }
.sw-prognose.stark { border-top-color: var(--mv-primary); }
.sw-band { background: var(--mv-band); outline: 1px solid var(--mv-divider); }
.planchart { position: relative; width: 100%; min-height: 200px; touch-action: pan-y; user-select: none; }
.planchart svg, .h-strip svg, .h-achse svg { display: block; }
.tooltip { position: absolute; top: 18px; z-index: 2; pointer-events: none; background: var(--mv-card);
  border: 1px solid var(--mv-divider); border-radius: 8px; padding: 8px 10px; font-size: 12px; line-height: 1.5;
  box-shadow: var(--mv-shadow); white-space: nowrap; }
.tip-laden { color: var(--mv-laden); font-weight: 500; }
svg .gitter { stroke: var(--mv-grid); stroke-width: 1; }
svg .rahmen { stroke: var(--mv-divider); stroke-width: 1; }
svg .achse { fill: var(--mv-text2); font-size: 11px; font-family: inherit; }
svg .achse.klein { font-size: 10px; }
svg .achse.ziel { fill: var(--mv-text); font-weight: 500; }
svg .grenzlinie { stroke: var(--mv-text2); stroke-width: 1; stroke-dasharray: 3 3; opacity: .6; }
svg .soc-linie { fill: none; stroke: var(--mv-soc); stroke-width: 2; stroke-linejoin: round; }
svg .soc-linie.warnlinie { stroke: var(--mv-warn-icon); stroke-width: 2.5; }
svg .preis-linie { fill: none; stroke: var(--mv-preis); stroke-width: 1.4; }
svg .preis-linie.prognose { stroke-dasharray: 4 3; }
svg .preis-linie.stark { stroke: var(--mv-primary); stroke-width: 2; }
svg .prognose-marke { stroke: var(--mv-text2); stroke-width: 1; stroke-dasharray: 2 3; }
svg .zielpunkt { fill: var(--mv-card); stroke: var(--mv-soc); stroke-width: 2.5; }
svg .zielpunkt.verfehlt { stroke: var(--mv-warn-icon); }
svg .faden { stroke: var(--mv-text); stroke-width: 1; opacity: .45; }
svg .faden-soc { fill: var(--mv-soc); stroke: var(--mv-card); stroke-width: 2; }
svg .faden-preis { fill: var(--mv-preis); stroke: var(--mv-card); stroke-width: 2; }
.bloecke { display: flex; flex-direction: column; border-top: 1px solid var(--mv-divider); padding-top: 8px; }
.bloecke-kopf { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
  gap: 4px 12px; font-weight: 500; padding-bottom: 4px; }
.block { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 12px; padding: 8px 0;
  border-top: 1px solid var(--mv-divider); }
.block b { font-weight: 500; }
.b-soc { color: var(--mv-text2); white-space: nowrap; }
.b-info { grid-column: 1 / -1; color: var(--mv-text2); font-size: 13px; }
.bloecke .mehr { padding: 10px 0 2px; text-align: left; }

.horizont { display: flex; flex-direction: column; padding-top: 4px; overflow: clip; }
.h-zeile { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 6px 16px; align-items: center;
  padding: 10px 16px; border: 0; background: none; text-align: left; width: 100%; }
button.h-zeile { border-top: 1px solid var(--mv-divider); }
button.h-zeile:hover { background: var(--mv-primary-soft); }
.h-label { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.h-label .status { font-size: 13px; }
.h-label .seg { align-self: flex-start; margin-top: 6px; }
.h-soc { font-weight: 400; color: var(--mv-text2); }
.h-strip, .h-achse { min-width: 0; width: 100%; }
.h-achsenzeile { padding-top: 0; padding-bottom: 6px; }
.h-fuss { padding: 10px 16px 12px; border-top: 1px solid var(--mv-divider); }
.schmal .h-zeile { grid-template-columns: minmax(0, 1fr); }
.schmal .h-achsenzeile .h-label { display: none; }

.tage { padding: 4px 0; }
.tage-kopf { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px;
  padding: 10px 16px; }
.tage-kopf b { font-weight: 500; }
.tagzeile { display: grid; grid-template-columns: 170px 84px 180px minmax(0, 1fr); gap: 4px 12px;
  align-items: baseline; padding: 10px 16px; border-top: 1px solid var(--mv-divider); }
.tagzeile b { font-weight: 500; }
.tagzeile.kopfzeile { font-size: 12px; color: var(--mv-text2); padding-block: 6px; }
.t-werte { color: var(--mv-text2); font-size: 13px; }
.quelle { display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 999px;
  border: 1px solid var(--mv-divider); color: var(--mv-text2); }
.quelle.boerse { border-color: var(--mv-primary); color: var(--mv-primary); }
.schmal .tagzeile { grid-template-columns: minmax(0, 1fr) auto; }
.schmal .tagzeile.kopfzeile { display: none; }
.schmal .t-fenster, .schmal .t-werte { grid-column: 1 / -1; }
`;
