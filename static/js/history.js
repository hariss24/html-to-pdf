// Injecté via meta tag par Flask
const IS_SERVERLESS = JSON.parse(
  document.querySelector('meta[name="is-serverless"]')?.content || 'false'
);
const HISTORY_KEY = 'cv-history';
let entries = [];

function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

function el(tag, attrs, children) {
  attrs    = attrs    || {};
  children = children || [];
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class')        node.className   = v;
    else if (k === 'onclick') node.onclick      = v;
    else if (k === 'text')    node.textContent  = v;
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    if (typeof c === 'string') node.appendChild(document.createTextNode(c));
    else node.appendChild(c);
  }
  return node;
}

function buildRow(e) {
  const id       = e.id;
  const pdfHref  = e.pdf_url || e.pdf_blob_url || ('/api/history/' + encodeURIComponent(id) + '/pdf');
  const reloadBase = '/?load=' + encodeURIComponent(id);
  const htmlSrc  = e.html_url || e.html_blob_url || '';
  const reloadHref = htmlSrc
    ? (reloadBase + '&htmlUrl=' + encodeURIComponent(htmlSrc))
    : reloadBase;

  const actions = [
    el('a',      { class: 'btn',          href: pdfHref,    target: '_blank', text: 'Voir PDF' }),
    el('a',      { class: 'btn',          href: reloadHref,                   text: 'Recharger' }),
    !IS_SERVERLESS
      ? el('button', { class: 'ghost', onclick: () => openLocal(id), text: 'Ouvrir local' })
      : null,
    el('button', { class: 'ghost danger', onclick: () => del(id), text: 'Supprimer' }),
  ].filter(Boolean);

  return el('tr', { 'data-id': id }, [
    el('td', { text: fmtDate(e.created_at) }),
    el('td', {}, [el('span', { class: 'badge', text: e.doc_type || '' })]),
    el('td', { text: e.company || '-' }),
    el('td', { title: e.job_desc || '', text: e.role || '-' }),
    el('td', { class: 'filename', title: e.filename, text: e.filename || '' }),
    el('td', { class: 'actions' }, actions),
  ]);
}

function render(filter) {
  filter = filter || '';
  const f        = filter.toLowerCase();
  const filtered = !f ? entries : entries.filter(e =>
    (e.company  || '').toLowerCase().includes(f) ||
    (e.role     || '').toLowerCase().includes(f) ||
    (e.doc_type || '').toLowerCase().includes(f) ||
    (e.notes    || '').toLowerCase().includes(f) ||
    (e.job_desc || '').toLowerCase().includes(f) ||
    (e.filename || '').toLowerCase().includes(f)
  );
  const root = document.getElementById('root');
  root.replaceChildren();
  if (!filtered.length) {
    root.appendChild(el('div', { class: 'empty', text: 'Aucun document.' }));
    return;
  }
  const head = el('thead', {}, [el('tr', {}, [
    el('th', { text: 'Date' }),
    el('th', { text: 'Type' }),
    el('th', { text: 'Entreprise' }),
    el('th', { text: 'Poste' }),
    el('th', { text: 'Fichier' }),
    el('th'),
  ])]);
  const body = el('tbody', {}, filtered.map(buildRow));
  root.appendChild(el('table', {}, [head, body]));
}

function showError(msg) {
  const root = document.getElementById('root');
  root.replaceChildren();
  root.appendChild(el('div', { class: 'error', text: msg }));
}

async function load() {
  try {
    const r = await fetch('/api/history');
    if (r.ok) {
      entries = await r.json();
      render(document.getElementById('search').value);
      return;
    }
  } catch (_) {}

  try {
    const raw    = localStorage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed !== null) {
      entries = parsed;
      render(document.getElementById('search').value);
      return;
    }
  } catch (_) {}

  showError('Historique vide ou impossible à charger.');
}

async function del(id) {
  if (!confirm('Supprimer cette entrée ?')) return;

  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (raw) {
      const hist = JSON.parse(raw).filter(e => e.id !== id);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(hist));
    }
  } catch (_) {}

  try {
    await fetch('/api/history/' + encodeURIComponent(id), { method: 'DELETE' });
  } catch (_) {}

  await load();
}

async function openLocal(id) {
  try {
    const r = await fetch('/api/history/' + encodeURIComponent(id) + '/open', { method: 'POST' });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      alert("Impossible d'ouvrir le fichier : " + (body.error || r.status));
    }
  } catch (err) {
    alert('Erreur réseau : ' + err.message);
  }
}

document.getElementById('search').addEventListener('input', e => render(e.target.value));
load();
