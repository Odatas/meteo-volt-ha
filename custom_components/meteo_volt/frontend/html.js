// HTML aus Vorlagen, die jeden eingesetzten Wert escapen. Spec C8 Abschnitt 4.
//
// Titel von Fahrzeugen und Namen von Personen kommen vom Nutzer. Unveraendert
// geht nur hinein, was selbst aus html`...` entstanden ist, und die Symbole,
// die das Panel mitbringt (vertraut).

const ZEICHEN = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export class Html {
  constructor(text) {
    this.text = text;
  }

  toString() {
    return this.text;
  }
}

export const esc = (wert) => String(wert).replace(/[&<>"']/g, (zeichen) => ZEICHEN[zeichen]);

function einsetzen(wert) {
  if (wert instanceof Html) return wert.text;
  if (Array.isArray(wert)) return wert.map(einsetzen).join('');
  if (wert === null || wert === undefined || wert === false) return '';
  return esc(wert);
}

export function html(teile, ...werte) {
  let text = teile[0];
  werte.forEach((wert, i) => {
    text += einsetzen(wert) + teile[i + 1];
  });
  return new Html(text);
}

// Nur fuer Text aus dem Panel selbst, nie fuer Daten.
export const vertraut = (text) => new Html(text);
