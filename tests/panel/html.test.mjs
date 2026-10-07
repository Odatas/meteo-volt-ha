// Prueft html.js: jeder eingesetzte Wert wird escaped. Spec C8 Abschnitt 4.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { Html, html, vertraut } from '../../custom_components/meteo_volt/frontend/html.js';

test('ein Wert wird escaped', () => {
  const name = '<img src=x onerror="alert(1)">';
  assert.equal(String(html`<b>${name}</b>`), '<b>&lt;img src=x onerror=&quot;alert(1)&quot;&gt;</b>');
  assert.equal(String(html`<i title="${"a'b"}">`), '<i title="a&#39;b">');
});

test('eine Vorlage in einer Vorlage bleibt, wie sie ist', () => {
  const innen = html`<i>${'&'}</i>`;
  assert.ok(innen instanceof Html);
  assert.equal(String(html`<b>${innen}</b>`), '<b><i>&amp;</i></b>');
});

test('Listen, Zahlen und leere Werte', () => {
  assert.equal(String(html`${[html`<i>1</i>`, '<2>', 3]}`), '<i>1</i>&lt;2&gt;3');
  assert.equal(String(html`${null}${undefined}${false}${0}`), '0');
});

test('vertraut nur fuer Text aus dem Panel', () => {
  assert.equal(String(html`${vertraut('<svg/>')}`), '<svg/>');
});
