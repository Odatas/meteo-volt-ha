// Die Symbole des Panels, als SVG im Shadow DOM. Spec C8 Abschnitt 4.

import { vertraut } from './html.js';

const PFADE = {
  menue: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  neuPlanen: '<path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  schliessen: '<path d="M6 6l12 12M18 6L6 18"/>',
  wiederholung: '<path d="M17 2l3 3-3 3M4 11V9a4 4 0 0 1 4-4h12M7 22l-3-3 3-3M20 13v2a4 4 0 0 1-4 4H4"/>',
  warnung: '<path d="M12 3L2 20h20L12 3zM12 10v4M12 17h.01"/>',
  person: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  auto: '<path d="M3 16v-3l2.2-5A2 2 0 0 1 7 6.8h10a2 2 0 0 1 1.8 1.2L21 13v3h-2M5 16H3M9 16h6M3 13h18"/>'
    + '<circle cx="7" cy="16" r="2"/><circle cx="17" cy="16" r="2"/>',
  raster: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
    + '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  papierkorb: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  diagramm: '<path d="M5 20V11M12 20V5M19 20v-6"/>',
};

export const symbol = (name) => vertraut(`<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${PFADE[name]}</svg>`);
