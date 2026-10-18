(() => {
  'use strict';
  const key = 'kk_cookie_notice_v1', lifetime = 180 * 24 * 60 * 60 * 1000;
  let previousFocus;
  const panel = document.createElement('section');
  panel.id = 'cookie-notice';
  panel.setAttribute('aria-label', 'Cookies und Browserspeicher');
  panel.hidden = true;
  panel.innerHTML = '<div><strong>Cookies &amp; Spielspeicher</strong><p>Wir verwenden nur notwendige Cookies und Browserspeicher für Anmeldung, Sicherheit und Spielteilnahme.</p><a href="/datenschutz#speicher">Datenschutz</a></div><button type="button">Verstanden</button>';
  document.body.append(panel);
  const button = panel.querySelector('button');
  function open(focus) {
    previousFocus = document.activeElement;
    panel.hidden = false;
    if (focus) button.focus();
  }
  button.addEventListener('click', () => {
    try { localStorage.setItem(key, String(Date.now())); } catch (_) {}
    panel.hidden = true;
    if (previousFocus && previousFocus.isConnected) previousFocus.focus();
  });
  document.querySelectorAll('[data-cookie-notice]').forEach(link => {
    link.addEventListener('click', event => { event.preventDefault(); open(true); });
  });
  let seen = 0;
  try { seen = Number(localStorage.getItem(key)); } catch (_) {}
  if (!Number.isFinite(seen) || seen <= 0 || seen > Date.now() || Date.now() - seen >= lifetime) open(false);
})();
