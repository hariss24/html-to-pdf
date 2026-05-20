// ============================================================
// Utilitaires de base
// ============================================================
const $ = (id) => document.getElementById(id);

function showToast(msg, cls, persist) {
  const c = $('toast-container');
  const t = document.createElement('div');
  t.className = 'toast' + (cls ? ' ' + cls : '');
  t.textContent = msg;
  c.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  if (!persist) {
    setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 250); }, 3500);
  }
  return t;
}

let _activeToast = null;
function setStatus(msg, cls) {
  if (_activeToast) {
    _activeToast.classList.remove('show');
    setTimeout(() => { if (_activeToast) { _activeToast.remove(); _activeToast = null; } }, 250);
  }
  if (!msg) return;
  _activeToast = showToast(msg, cls, cls === 'err');
}

let _autosaveTimer = null;
function flashAutosave() {
  const el = $('autosave');
  if (!el) return;
  el.style.opacity = '1';
  clearTimeout(_autosaveTimer);
  _autosaveTimer = setTimeout(() => { el.style.opacity = '0'; }, 2000);
}

// ============================================================
// Constantes de stockage
// ============================================================
const STORAGE_KEY_HTML = 'html-to-pdf:draft:html';
const STORAGE_KEY_CSS  = 'html-to-pdf:draft:css';
const STORAGE_KEY_TAB  = 'html-to-pdf:draft:tab';
const HISTORY_KEY      = 'cv-history';

// Jeton CSRF (pour les requêtes multipart/form-data)
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';

// ============================================================
// Templates HTML/CSS intégrés
// ============================================================
const TEMPLATES = {
  sobre: {
    html: `<div class="resume-template-1 resume-template-renderer">

  <section class="resume-template-renderer-section personal-data">
    <h2 class="resume-template-renderer-section__title">Informations personnelles</h2>
    <div class="personal-data__photo" style="background:#eee;">
      <!-- URL_DE_VOTRE_PHOTO_ICI -->
    </div>
    <div class="personal-data__title-row">
      <span class="personal-data__name">Prenom Nom</span><span class="personal-data__desired-job-title">Titre du poste</span>
    </div>
    <div class="personal-data__contact-row">
      Ville, Pays &middot; email@example.com &middot; +33 6 00 00 00 00 &middot; linkedin.com/in/profil
    </div></section>

  <section class="resume-template-renderer-section summary-objective">
    <h2 class="resume-template-renderer-section__title summary-objective__title">A propos</h2>
    <div class="summary-objective__content">
      Bref resume professionnel : 2 a 3 phrases qui presentent votre profil, votre experience et ce que vous recherchez.
    </div>
  </section>

  <section class="resume-template-renderer-section entry-list">
    <h2 class="resume-template-renderer-section__title">Experience</h2>
    <div class="entry-list__item">
      <span class="entry-list__title">Poste occupe</span>
      <span class="entry-list__date">Jan 2024 - Present</span>
      <div class="entry-list__company-row">
        <span class="entry-list__subtitle">Entreprise</span><span class="entry-list__location">Ville</span>
      </div>
      <div class="entry-list__description">
        <ul>
          <li>Realisation marquante avec metrique chiffree.</li>
          <li>Autre realisation pertinente pour le poste vise.</li>
        </ul>
      </div>
    </div>
    <div class="entry-list__item">
      <span class="entry-list__title">Poste precedent</span>
      <span class="entry-list__date">2022 - 2023</span>
      <div class="entry-list__company-row">
        <span class="entry-list__subtitle">Autre entreprise</span><span class="entry-list__location">Ville</span>
      </div>
      <div class="entry-list__description">
        <ul>
          <li>Description courte de la mission.</li>
        </ul>
      </div>
    </div>
  </section>

  <section class="resume-template-renderer-section entry-list">
    <h2 class="resume-template-renderer-section__title">Formation</h2>
    <div class="entry-list__item">
      <span class="entry-list__title">Diplome</span>
      <span class="entry-list__date">2020 - 2022</span>
      <div class="entry-list__company-row">
        <span class="entry-list__subtitle">Etablissement</span><span class="entry-list__location">Ville</span>
      </div>
    </div>
  </section>

  <section class="resume-template-renderer-section plain-list">
    <h2 class="resume-template-renderer-section__title">Competences</h2>
    <div class="plain-list__items">
      <span class="plain-list__item">Competence 1</span>
      <span class="plain-list__item">Competence 2</span>
      <span class="plain-list__item">Competence 3</span>
      <span class="plain-list__item">Competence 4</span>
      <span class="plain-list__item">Competence 5</span>
      <span class="plain-list__item">Competence 6</span>
    </div>
  </section>

  <section class="resume-template-renderer-section languages">
    <h2 class="resume-template-renderer-section__title">Langues</h2>
    <div class="languages__items">
      <div class="languages__item">
        <span class="languages__name">Francais</span>
        <span class="languages__description">Natif</span>
      </div>
      <div class="languages__item">
        <span class="languages__name">Anglais</span>
        <span class="languages__description">Courant</span>
      </div>
    </div>
  </section>

</div>`,
    css: `@page { size: A4; margin: 0; }

:root { --resume-template-customization-color: #c9c6c1; }

* { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  font-family: "Helvetica", "Arial", sans-serif;
  color: #555;
  font-size: 9pt;
  line-height: 1.35;
}

ul { list-style: none; }
a { color: inherit; text-decoration: underline; }

.resume-template-1.resume-template-renderer { padding: 24px 50px 20px; }
.resume-template-1.resume-template-renderer .resume-template-renderer-section { border-top: 2px solid var(--resume-template-customization-color); padding-top: 7px; }
.resume-template-1.resume-template-renderer .resume-template-renderer-section .resume-template-renderer-section__title { margin-bottom: 8px; text-transform: uppercase; font-size: 8.5pt; letter-spacing: 0.5px; color: #555; font-weight: 500; }
.resume-template-1.resume-template-renderer .resume-template-renderer-section.personal-data { border-top: none; padding-top: 0; }
.resume-template-1.resume-template-renderer .resume-template-renderer-section.personal-data .resume-template-renderer-section__title { display: none; }
.resume-template-1.resume-template-renderer .personal-data { display: block; margin-bottom: 10px; min-height: 80px; padding-left: calc(25% + 0px); position: relative; }
.resume-template-1.resume-template-renderer .personal-data .personal-data__photo { aspect-ratio: 1; left: 0; position: absolute; width: 80px; top: 0; }
.resume-template-1.resume-template-renderer .personal-data .personal-data__photo img { width: 100%; height: 100%; border-radius: 6px; object-fit: cover; display: block; }
.resume-template-1.resume-template-renderer .personal-data .personal-data__title-row { margin-bottom: 4px; }
.resume-template-1.resume-template-renderer .personal-data .personal-data__name,
.resume-template-1.resume-template-renderer .personal-data .personal-data__desired-job-title { color: #000; font-size: 14pt; font-weight: 500; }
.resume-template-1.resume-template-renderer .personal-data .personal-data__desired-job-title::before { content: ", "; }
.resume-template-1.resume-template-renderer .personal-data .personal-data__contact-row { font-size: 9.5pt; color: #555; }
.resume-template-1.resume-template-renderer .summary-objective { display: flex; margin-bottom: 6px; }
.resume-template-1.resume-template-renderer .summary-objective .summary-objective__title { flex-shrink: 0; width: 25%; margin-bottom: 0; }
.resume-template-1.resume-template-renderer .summary-objective .summary-objective__content { flex: 1; }
.resume-template-1.resume-template-renderer .entry-list .entry-list__item { display: block; padding-bottom: 7px; }
.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__title { color: #000; font-weight: 500; display: inline; }
.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__date { float: right; color: #555; font-weight: 400; }
.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__subtitle { color: #000; font-weight: 600; display: inline; }
.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__location { color: #787673; font-weight: 400; display: inline; margin-left: 4px; }
.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__company-row { display: block; margin-top: 1px; clear: both; }
.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__description { margin-top: 3px; clear: both; }
.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__description ul { list-style-type: disc; padding-left: 14px; }
.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__description li { margin-bottom: 1px; }
.resume-template-1.resume-template-renderer .plain-list { display: flex; margin-bottom: 6px; }
.resume-template-1.resume-template-renderer .plain-list .resume-template-renderer-section__title { flex-shrink: 0; width: 25%; margin-bottom: 0; }
.resume-template-1.resume-template-renderer .plain-list .plain-list__items { display: flex; flex-wrap: wrap; gap: 3px 0; flex: 1; }
.resume-template-1.resume-template-renderer .plain-list .plain-list__items .plain-list__item { color: #000; font-weight: 500; padding-right: 12px; width: 33.33%; }
.resume-template-1.resume-template-renderer .languages { display: flex; margin-bottom: 6px; }
.resume-template-1.resume-template-renderer .languages .resume-template-renderer-section__title { flex-shrink: 0; width: 25%; margin-bottom: 0; }
.resume-template-1.resume-template-renderer .languages .languages__items { display: flex; flex-grow: 1; flex-wrap: wrap; gap: 6px 0; }
.resume-template-1.resume-template-renderer .languages .languages__items .languages__item { display: flex; flex-wrap: wrap; padding-right: 12px; width: 33.33%; }
.resume-template-1.resume-template-renderer .languages .languages__items .languages__item .languages__name { color: #000; font-weight: 500; margin-right: 4px; }
.resume-template-1.resume-template-renderer .languages .languages__items .languages__item .languages__description { color: #787673; }
.resume-template-1.resume-template-renderer .languages .languages__items .languages__item .languages__description::before { content: "("; }
.resume-template-1.resume-template-renderer .languages .languages__items .languages__item .languages__description::after { content: ")"; }`,
  },
  moderne: {
    html: `<header class="cv-head">
  <!-- URL_DE_VOTRE_PHOTO_ICI -->
  <h1>Prenom Nom</h1>
  <p class="role">Titre du poste recherche</p>
  <p class="contact">email@example.com &middot; +33 6 00 00 00 00 &middot; linkedin.com/in/profil &middot; Ville</p>
</header>

<section class="cv-section">
  <h2>A propos</h2>
  <p>Bref resume professionnel : 2 a 3 phrases qui presentent votre profil et ce que vous recherchez.</p>
</section>

<section class="cv-section">
  <h2>Experience</h2>
  <div class="job">
    <div class="job-head">
      <span><strong>Poste occupe</strong> &middot; Entreprise</span>
      <span class="date">Jan 2024 - Present</span>
    </div>
    <ul>
      <li>Realisation marquante avec metrique chiffree.</li>
      <li>Autre realisation pertinente pour le poste vise.</li>
    </ul>
  </div>
  <div class="job">
    <div class="job-head">
      <span><strong>Poste precedent</strong> &middot; Autre entreprise</span>
      <span class="date">2022 - 2023</span>
    </div>
    <ul>
      <li>Description courte de la mission.</li>
    </ul>
  </div>
</section>

<section class="cv-section">
  <h2>Formation</h2>
  <div class="job">
    <div class="job-head">
      <span><strong>Diplome</strong> &middot; Etablissement</span>
      <span class="date">2020 - 2022</span>
    </div>
  </div>
</section>

<section class="cv-section">
  <h2>Competences</h2>
  <ul class="skills">
    <li>JavaScript</li><li>TypeScript</li><li>Python</li><li>React</li><li>Node.js</li><li>SQL</li>
  </ul>
</section>`,
    css: `@page { size: A4; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color: #1e293b; line-height: 1.55; font-size: 10.5pt; padding: 18mm 16mm; }
h1 { color: #2563eb; font-size: 22pt; font-weight: 700; margin-bottom: 4px; }
.role { color: #475569; font-size: 11.5pt; margin-bottom: 6px; }
.contact { color: #64748b; font-size: 9.5pt; }
.cv-head { padding-bottom: 12px; border-bottom: 2px solid #2563eb; margin-bottom: 14px; }
.cv-section { margin-bottom: 14px; }
.cv-section h2 { color: #2563eb; font-size: 12pt; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.6px; }
.cv-section p { margin-bottom: 6px; }
.job { margin-bottom: 10px; }
.job-head { display: flex; justify-content: space-between; margin-bottom: 4px; }
.date { color: #94a3b8; font-weight: 400; font-size: 9.5pt; }
.job ul { list-style: disc; padding-left: 18px; }
.job ul li { margin-bottom: 2px; }
ul.skills { list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
ul.skills li { background: #eff6ff; color: #2563eb; padding: 2px 10px; border-radius: 12px; font-size: 9.5pt; font-weight: 500; }`,
  },
  minimal: {
    html: `<!-- URL_DE_VOTRE_PHOTO_ICI -->
<h1>Prenom Nom</h1>
<p class="meta">Titre du poste &middot; email@example.com &middot; +33 6 00 00 00 00</p>

<h2>Experience</h2>
<p><strong>Poste occupe</strong>, Entreprise &mdash; Jan 2024 - Present</p>
<p>Description courte de ce que vous avez accompli.</p>

<p><strong>Poste precedent</strong>, Autre entreprise &mdash; 2022 - 2023</p>
<p>Autre description courte.</p>

<h2>Formation</h2>
<p><strong>Diplome</strong>, Etablissement &mdash; 2020 - 2022</p>

<h2>Competences</h2>
<p>Competence 1, Competence 2, Competence 3, Competence 4, Competence 5.</p>`,
    css: `@page { size: A4; margin: 0; }
body { font: 11pt/1.6 Georgia, "Times New Roman", serif; color: #222; padding: 22mm; }
h1 { font-size: 22pt; font-weight: normal; margin: 0 0 4px; }
h2 { font-size: 13pt; font-weight: normal; margin: 18px 0 6px; border-bottom: 1px solid #ccc; padding-bottom: 2px; }
p { margin: 0 0 6px; }
.meta { color: #666; margin-bottom: 18px; }
strong { font-weight: 600; }`,
  },
};

// ============================================================
// Variables globales Monaco
// ============================================================
let editor;
let htmlModel;
let cssModel;
let activeTab = 'html';

// ============================================================
// Fusion HTML + CSS avec échappement anti-injection de balise
// ============================================================
function mergedHtml() {
  const html = htmlModel ? htmlModel.getValue() : '';
  const css  = cssModel  ? cssModel.getValue()  : '';
  if (!css.trim()) return html;
  // Empêcher la fermeture prématurée du bloc <style> par du CSS malformé.
  const safeCss = css.replace(/<\/style\s*>/gi, '<\\/style>');
  if (/<\/head>/i.test(html)) {
    return html.replace(/<\/head>/i, `<style>\n${safeCss}\n</style>\n</head>`);
  }
  if (/<html[\s>]/i.test(html)) {
    return html.replace(/<html([^>]*)>/i, `<html$1>\n<head><meta charset="utf-8"><style>\n${safeCss}\n</style></head>`);
  }
  return `<!DOCTYPE html>\n<html lang="fr">\n<head>\n<meta charset="utf-8">\n<style>\n${safeCss}\n</style>\n</head>\n<body>\n${html}\n</body>\n</html>`;
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  const importPane = $('import-pane');
  const editorDiv  = $('editor');
  if (tab === 'import') {
    if (editorDiv)   editorDiv.style.display   = 'none';
    if (importPane)  importPane.classList.add('active');
  } else {
    if (editorDiv)  editorDiv.style.display   = '';
    if (importPane) importPane.classList.remove('active');
    if (editor) editor.setModel(tab === 'css' ? cssModel : htmlModel);
  }
  try { localStorage.setItem(STORAGE_KEY_TAB, tab); } catch (_) {}
}

// ============================================================
// Utilitaires nommage (aligné Python)
// ============================================================
function slug(s) {
  if (!s) return '';
  return s.normalize('NFKD')
          .replace(/[̀-ͯ]/g, '')
          .replace(/[^\w\s-]/gu, '')
          .trim()
          .replace(/[\s_-]+/g, '');
}

function autoFilename() {
  const today   = new Date().toISOString().slice(0, 10);
  const docType = $('doc_type').value || 'Document';
  const company = slug($('company').value);
  const role    = slug($('role').value);
  const tail    = company || role || '';
  return tail ? `${docType}_${tail}_${today}.pdf` : `${docType}_${today}.pdf`;
}

function refreshFilenamePreview() {
  const custom = $('filename').value.trim();
  const auto   = autoFilename();
  $('filename_preview').textContent = custom ? `Nom : ${custom}` : `Nom auto : ${auto}`;
}

['doc_type', 'company', 'role', 'filename'].forEach(id =>
  $(id).addEventListener('input', refreshFilenamePreview)
);
refreshFilenamePreview();

// ============================================================
// Indicateur de pages A4
// ============================================================
function updatePageCount() {
  const iframe = $('preview');
  const badge  = $('page-count-badge');
  if (!badge || !iframe) return;
  try {
    const doc = iframe.contentDocument;
    if (!doc || !doc.body) return;
    // A4 à 96 dpi ≈ 1122px (297mm × 96 / 25.4)
    const A4_H = 1122;
    const h    = doc.body.scrollHeight;
    const pages = Math.max(1, Math.ceil(h / A4_H));
    if (pages === 1) {
      badge.textContent = '1 page ✓';
      badge.className   = 'page-badge ok';
    } else {
      badge.textContent = `${pages} pages ⚠`;
      badge.className   = pages === 2 ? 'page-badge warn' : 'page-badge over';
    }
  } catch (_) {}
}

// ============================================================
// Prévisualisation avec debounce
// ============================================================
let previewTimer;
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    $('preview').srcdoc = mergedHtml();
    // Mettre à jour le compteur après un délai pour laisser l'iframe charger
    setTimeout(updatePageCount, 600);
  }, 400);
}

$('preview').addEventListener('load', updatePageCount);

// ============================================================
// Snapshots IndexedDB
// ============================================================
const IDB_DB    = 'html-to-pdf-snapshots';
const IDB_STORE = 'snapshots';
const MAX_SNAPS = 20;

const IDB_HTML_STORE = 'cv-html-store';

function _openIDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_DB, 2);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(IDB_STORE)) {
        db.createObjectStore(IDB_STORE, { keyPath: 'ts' });
      }
      if (!db.objectStoreNames.contains(IDB_HTML_STORE)) {
        db.createObjectStore(IDB_HTML_STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}

async function saveHtmlToIDB(id, html, css) {
  try {
    const db = await _openIDB();
    await new Promise((res, rej) => {
      const tx = db.transaction(IDB_HTML_STORE, 'readwrite');
      tx.objectStore(IDB_HTML_STORE).put({ id, html, css });
      tx.oncomplete = res;
      tx.onerror    = e => rej(e.target.error);
    });
  } catch (_) {}
}

async function loadHtmlFromIDB(id) {
  try {
    const db = await _openIDB();
    return await new Promise((res, rej) => {
      const tx  = db.transaction(IDB_HTML_STORE, 'readonly');
      const req = tx.objectStore(IDB_HTML_STORE).get(id);
      req.onsuccess = () => res(req.result || null);
      req.onerror   = e => rej(e.target.error);
    });
  } catch (_) { return null; }
}

async function deleteHtmlFromIDB(id) {
  try {
    const db = await _openIDB();
    await new Promise((res, rej) => {
      const tx = db.transaction(IDB_HTML_STORE, 'readwrite');
      tx.objectStore(IDB_HTML_STORE).delete(id);
      tx.oncomplete = res;
      tx.onerror    = e => rej(e.target.error);
    });
  } catch (_) {}
}

async function saveSnapshot(label) {
  if (!htmlModel) return;
  try {
    const db = await _openIDB();
    const snap = {
      ts:       Date.now(),
      label:    label || new Date().toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }),
      html:     htmlModel.getValue(),
      css:      cssModel ? cssModel.getValue() : '',
      doc_type: $('doc_type')?.value || 'CV',
      company:  $('company')?.value  || '',
      role:     $('role')?.value     || '',
    };
    await new Promise((res, rej) => {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      const st = tx.objectStore(IDB_STORE);
      st.put(snap);
      tx.oncomplete = res;
      tx.onerror    = e => rej(e.target.error);
    });
    // Garder seulement les MAX_SNAPS derniers
    await _pruneSnapshots(db);
  } catch (e) {
    console.warn('Snapshot:', e);
  }
}

async function _pruneSnapshots(db) {
  return new Promise((res) => {
    const tx = db.transaction(IDB_STORE, 'readwrite');
    const st = tx.objectStore(IDB_STORE);
    const req = st.getAll();
    req.onsuccess = () => {
      const all = req.result.sort((a, b) => b.ts - a.ts);
      all.slice(MAX_SNAPS).forEach(s => st.delete(s.ts));
    };
    tx.oncomplete = res;
  });
}

async function listSnapshots() {
  const db  = await _openIDB();
  return new Promise((res, rej) => {
    const tx  = db.transaction(IDB_STORE, 'readonly');
    const req = tx.objectStore(IDB_STORE).getAll();
    req.onsuccess = () => res(req.result.sort((a, b) => b.ts - a.ts));
    req.onerror   = e => rej(e.target.error);
  });
}

async function deleteSnapshot(ts) {
  const db = await _openIDB();
  return new Promise((res, rej) => {
    const tx = db.transaction(IDB_STORE, 'readwrite');
    tx.objectStore(IDB_STORE).delete(ts);
    tx.oncomplete = res;
    tx.onerror    = e => rej(e.target.error);
  });
}

function restoreSnapshot(snap) {
  if (!htmlModel) return;
  if (!confirm(`Restaurer le snapshot "${snap.label}" ? Le contenu actuel sera remplacé.`)) return;
  htmlModel.setValue(snap.html || '');
  if (cssModel) cssModel.setValue(snap.css || '');
  if (snap.doc_type && $('doc_type')) $('doc_type').value = snap.doc_type;
  if (snap.company  && $('company'))  $('company').value  = snap.company;
  if (snap.role     && $('role'))     $('role').value     = snap.role;
  refreshFilenamePreview();
  closeSnapshotsModal();
  showToast('Snapshot restauré.', 'ok');
}

// Auto-snapshot toutes les 5 minutes
setInterval(() => saveSnapshot(), 5 * 60 * 1000);

// Modal Snapshots
function openSnapshotsModal() {
  const modal = $('modal-snapshots');
  modal.classList.add('open');
  renderSnapshotsList();
}
function closeSnapshotsModal() {
  $('modal-snapshots').classList.remove('open');
}

async function renderSnapshotsList() {
  const list = $('snapshots-list');
  list.innerHTML = '';
  let snaps;
  try {
    snaps = await listSnapshots();
  } catch (_) {
    list.innerHTML = '<div class="snapshots-empty">Impossible de charger les snapshots.</div>';
    return;
  }
  if (!snaps.length) {
    list.innerHTML = '<div class="snapshots-empty">Aucun snapshot. Les snapshots sont créés automatiquement toutes les 5 minutes.</div>';
    return;
  }
  snaps.forEach(s => {
    const date   = new Date(s.ts).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
    const chars  = (s.html || '').length + (s.css || '').length;
    const item   = document.createElement('div');
    item.className = 'snapshot-item';
    item.innerHTML = `
      <div>
        <div>${s.label}</div>
        <div class="snap-meta">${date} · ${chars.toLocaleString()} car. · ${s.doc_type || 'CV'}${s.company ? ' · ' + s.company : ''}${s.role ? ' · ' + s.role : ''}</div>
      </div>
      <div class="snap-actions">
        <button class="snap-restore">Restaurer</button>
        <button class="snap-delete">Suppr.</button>
      </div>`;
    item.querySelector('.snap-restore').onclick = () => restoreSnapshot(s);
    item.querySelector('.snap-delete').onclick  = async () => {
      await deleteSnapshot(s.ts);
      renderSnapshotsList();
    };
    list.appendChild(item);
  });
}

$('btn-snapshots').onclick = openSnapshotsModal;
$('close-snapshots').onclick = closeSnapshotsModal;
$('modal-snapshots').addEventListener('click', e => {
  if (e.target === $('modal-snapshots')) closeSnapshotsModal();
});
$('btn-save-snapshot-now').onclick = async () => {
  await saveSnapshot('Manuel · ' + new Date().toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }));
  renderSnapshotsList();
  showToast('Snapshot créé.', 'ok');
};

// ============================================================
// Initialisation Monaco
// ============================================================
require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' } });
require(['vs/editor/editor.main'], function () {
  const storedHtml = localStorage.getItem(STORAGE_KEY_HTML);
  const storedCss  = localStorage.getItem(STORAGE_KEY_CSS);
  const wantTab    = localStorage.getItem(STORAGE_KEY_TAB) || 'html';
  const fallback   = TEMPLATES.sobre;

  htmlModel = monaco.editor.createModel(
    storedHtml !== null ? storedHtml : fallback.html, 'html');
  cssModel  = monaco.editor.createModel(
    storedCss  !== null ? storedCss  : fallback.css,  'css');

  editor = monaco.editor.create($('editor'), {
    model: htmlModel,
    theme: 'vs-dark',
    automaticLayout: true,
    minimap: { enabled: false },
    wordWrap: 'on',
    fontSize: 13,
    tabSize: 2,
    scrollBeyondLastLine: false,
  });

  htmlModel.onDidChangeContent(() => {
    try { localStorage.setItem(STORAGE_KEY_HTML, htmlModel.getValue()); flashAutosave(); } catch (_) {}
    schedulePreview();
  });
  cssModel.onDidChangeContent(() => {
    try { localStorage.setItem(STORAGE_KEY_CSS, cssModel.getValue()); flashAutosave(); } catch (_) {}
    schedulePreview();
  });

  document.querySelectorAll('.tab').forEach(btn => {
    btn.onclick = () => switchTab(btn.dataset.tab);
  });
  switchTab(wantTab);

  $('preview').srcdoc = mergedHtml();

  $('format-btn').onclick = () => {
    const action = editor.getAction('editor.action.formatDocument');
    if (action) action.run();
  };
  $('snippet-page').onclick = () => {
    switchTab('css'); insertSnippet('@page { size: A4; margin: 15mm; }\n');
  };
  $('snippet-pagebreak').onclick = () => {
    switchTab('html'); insertSnippet('<div style="page-break-after: always;"></div>\n');
  };
  $('refresh-preview').onclick = () => { $('preview').srcdoc = mergedHtml(); };

  $('template-select').onchange = (e) => {
    const key = e.target.value;
    e.target.value = '';
    if (!key) return;
    const tpl = TEMPLATES[key];
    if (!tpl) return;
    const dirty = htmlModel.getValue().trim() || cssModel.getValue().trim();
    if (dirty && !confirm(`Charger le template "${key}" et ecraser le contenu actuel ?`)) return;
    htmlModel.setValue(tpl.html);
    cssModel.setValue(tpl.css);
  };

  // ---- Sélecteur de type de document (CV / Lettre) -------------------------
  const _TYPE_STORE_PREFIX = 'html-to-pdf:type:';

  const _LETTRE_SKELETON = `<div style="font-family: Georgia, 'Times New Roman', serif; max-width: 680px; margin: 40px auto; color: #222; line-height: 1.7; font-size: 14px;">

  <div style="text-align: right; margin-bottom: 48px;">
    <p style="margin: 0;">Prénom Nom<br>
    Adresse, Ville<br>
    email@example.com &middot; +33 6 00 00 00 00</p>
    <p style="margin: 16px 0 0;">Ville, le JJ/MM/AAAA</p>
  </div>

  <div style="margin-bottom: 32px;">
    <p style="margin: 0;"><strong>Nom de l'entreprise</strong><br>
    Service Recrutement<br>
    Adresse de l'entreprise</p>
  </div>

  <p><strong>Objet : Candidature au poste de [Intitulé du poste]</strong></p>

  <p>Madame, Monsieur,</p>

  <p>[Accroche : présentez-vous brièvement et expliquez pourquoi ce poste et cette entreprise vous intéressent particulièrement.]</p>

  <p>[Argumentaire : décrivez vos compétences et expériences les plus pertinentes, avec des exemples concrets.]</p>

  <p>[Conclusion : réaffirmez votre motivation, mentionnez votre disponibilité pour un entretien et remerciez pour l'attention portée à votre candidature.]</p>

  <p>Dans l'attente de votre réponse, je reste à votre disposition pour tout échange.</p>

  <p>Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.</p>

  <br><br>
  <p>Prénom Nom</p>

</div>`;

  function _docTypeKey(type) { return _TYPE_STORE_PREFIX + type.toLowerCase(); }

  function _saveContentForType(type) {
    if (!htmlModel) return;
    try {
      localStorage.setItem(_docTypeKey(type), JSON.stringify({
        html: htmlModel.getValue(),
        css: cssModel ? cssModel.getValue() : '',
      }));
    } catch (_) {}
  }

  function _loadContentForType(type) {
    if (!htmlModel) return;
    const raw = localStorage.getItem(_docTypeKey(type));
    if (raw) {
      try {
        const saved = JSON.parse(raw);
        htmlModel.setValue(saved.html || '');
        if (cssModel) cssModel.setValue(saved.css || '');
        return;
      } catch (_) {}
    }
    if (type === 'Lettre') {
      htmlModel.setValue(_LETTRE_SKELETON);
      if (cssModel) cssModel.setValue('');
    }
  }

  let _activeDocType = $('doc_type').value || 'CV';
  _saveContentForType(_activeDocType);

  $('doc_type').addEventListener('change', function () {
    const newType = this.value;
    if (newType === _activeDocType) return;
    _saveContentForType(_activeDocType);
    _activeDocType = newType;
    _loadContentForType(newType);
    refreshFilenamePreview();
  });

  // ---- Chargement depuis l'historique (?load=) -------------------------
  const params = new URLSearchParams(location.search);
  const loadId = params.get('load');

  if (loadId) {
    let localEntry = null;
    try {
      const hist = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
      localEntry = hist.find(e => e.id === loadId) || null;
    } catch (_) {}

    if (localEntry) {
      $('doc_type').value    = localEntry.doc_type || 'CV';
      $('company').value     = localEntry.company  || '';
      $('role').value        = localEntry.role     || '';
      $('notes').value       = localEntry.notes    || '';
      $('ia-job-desc').value = localEntry.job_desc || '';
      if (typeof updatePrompt === 'function') updatePrompt();
      refreshFilenamePreview();
    }

    loadHtmlFromIDB(loadId).then(stored => {
      if (stored) {
        htmlModel.setValue(stored.html || '');
        if (cssModel) cssModel.setValue(stored.css || '');
        switchTab('html');
      } else if (!localEntry) {
        setStatus('Document introuvable dans ce navigateur.', 'err');
      }
    });
  }
});

function insertSnippet(text) {
  if (!editor) return;
  const sel = editor.getSelection();
  editor.executeEdits('snippet', [{ range: sel, text, forceMoveMarkers: true }]);
  editor.focus();
}

// ============================================================
// Nouveau CV
// ============================================================
const modalNewCv = $('modal-new-cv');

$('btn-new-cv').onclick = () => { modalNewCv.style.display = 'flex'; };
$('close-new-cv').onclick = () => { modalNewCv.style.display = 'none'; };
window.addEventListener('click', e => { if (e.target === modalNewCv) modalNewCv.style.display = 'none'; });

document.querySelectorAll('.template-card').forEach(card => {
  card.addEventListener('click', () => {
    const key = card.dataset.tpl;
    const tpl = TEMPLATES[key];
    if (!tpl) return;

    saveSnapshot('Avant nouveau CV');

    if (htmlModel) htmlModel.setValue(tpl.html);
    if (cssModel)  cssModel.setValue(tpl.css);

    ['company', 'role', 'filename', 'notes'].forEach(id => { const el = $(id); if (el) el.value = ''; });
    refreshFilenamePreview();

    modalNewCv.style.display = 'none';
    switchTab('html');
    showToast(`Template "${key}" chargé.`, 'ok');
  });
});

// ============================================================
// Effacer
// ============================================================
$('clear').onclick = () => {
  const hasContent = (htmlModel && htmlModel.getValue().trim()) || (cssModel && cssModel.getValue().trim());
  if (hasContent && !confirm('Effacer tout le contenu ? Un snapshot automatique sera créé avant.')) return;
  saveSnapshot('Avant effacement');
  if (htmlModel) htmlModel.setValue('');
  if (cssModel)  cssModel.setValue('');
  ['company', 'role', 'filename', 'notes'].forEach(id => $(id).value = '');
  refreshFilenamePreview();
  try {
    localStorage.removeItem(STORAGE_KEY_HTML);
    localStorage.removeItem(STORAGE_KEY_CSS);
  } catch (_) {}
};

// ============================================================
// Raccourcis clavier
// ============================================================
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); $('go').click(); }
  if (e.ctrlKey && e.shiftKey && e.key === 'H') { e.preventDefault(); window.location.href = '/history'; }
  if (e.ctrlKey && e.shiftKey && e.key === 'I') { e.preventDefault(); $('btn-ia').click(); }
  if (e.ctrlKey && e.shiftKey && e.key === 'S') { e.preventDefault(); openSnapshotsModal(); }
});

// ============================================================
// Convertir en PDF
// ============================================================
$('go').onclick = async () => {
  const html = mergedHtml();
  if (!html.trim()) { setStatus("Editez du HTML d'abord.", 'err'); return; }
  const btn = $('go');
  btn.disabled = true;
  btn.textContent = 'Conversion...';
  setStatus('Generation du PDF...', '');
  try {
    const res = await fetch('/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        html,
        doc_type:   $('doc_type').value,
        company:    $('company').value.trim(),
        role:       $('role').value.trim(),
        notes:      $('notes').value.trim(),
        job_desc:   $('ia-job-desc').value.trim(),
        format:     $('format').value,
        margin:     $('margin').value,
        background: $('bg').checked,
        filename:   $('filename').value.trim(),
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'Erreur inconnue' }));
      setStatus('Erreur : ' + (err.error || res.statusText), 'err');
      return;
    }
    const meta = JSON.parse(res.headers.get('X-Archive-Entry') || '{}');
    const entryId = meta.id || crypto.randomUUID();

    const blob   = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a      = document.createElement('a');
    a.href       = objUrl;
    a.download   = meta.filename || 'document.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(objUrl), 10_000);

    setStatus(`PDF téléchargé : ${meta.filename}`, 'ok');

    // Persistance navigateur : métadonnées dans localStorage, HTML+CSS dans IndexedDB
    try {
      const hist = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
      hist.unshift({
        id:         entryId,
        filename:   meta.filename,
        created_at: meta.created_at,
        doc_type:   $('doc_type').value,
        company:    $('company').value.trim(),
        role:       $('role').value.trim(),
        notes:      $('notes').value.trim(),
        job_desc:   $('ia-job-desc').value.trim(),
      });
      localStorage.setItem(HISTORY_KEY, JSON.stringify(hist.slice(0, 100)));
    } catch (_) {}
    await saveHtmlToIDB(entryId, htmlModel.getValue(), cssModel ? cssModel.getValue() : '');
  } catch (e) {
    setStatus('Erreur réseau : ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Convertir en PDF';
  }
};

// ============================================================
// Splitter redimensionnable
// ============================================================
(function initSplitter() {
  const split      = $('split');
  const splitter   = $('splitter');
  const editorPane = $('editor-pane');
  let dragging     = false;

  const onStart = (e) => {
    dragging = true;
    if (e.cancelable) e.preventDefault();
    const isMobile = window.innerWidth <= 768;
    document.body.style.cursor = isMobile ? 'row-resize' : 'col-resize';
  };

  const onMove = (e) => {
    if (!dragging) return;
    const rect    = split.getBoundingClientRect();
    const isMobile = window.innerWidth <= 768;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    if (isMobile) {
      const pct = Math.max(15, Math.min(85, ((clientY - rect.top) / rect.height) * 100));
      editorPane.style.flexBasis = `${pct}%`;
    } else {
      const pct = Math.max(15, Math.min(85, ((clientX - rect.left) / rect.width) * 100));
      editorPane.style.flexBasis = `${pct}%`;
    }
  };

  const onEnd = () => { dragging = false; document.body.style.cursor = ''; };

  splitter.addEventListener('mousedown', onStart);
  splitter.addEventListener('touchstart', onStart, { passive: false });
  window.addEventListener('mousemove', onMove);
  window.addEventListener('touchmove', onMove, { passive: false });
  window.addEventListener('mouseup', onEnd);
  window.addEventListener('touchend', onEnd);
})();

// ============================================================
// Assistant IA
// ============================================================
const modalIa = $('modal-ia');
$('btn-ia').onclick = () => { modalIa.style.display = 'flex'; updatePrompt(); };
$('close-modal').onclick = () => { modalIa.style.display = 'none'; };
window.addEventListener('click', e => { if (e.target === modalIa) modalIa.style.display = 'none'; });

// ---- Sélecteurs de niveau ----------------------------------------
let _tailorLevel = 'adapte';
let _iaLevel = 'adapte';

function _initLevelSelector(selectorId, onChange) {
  const el = $(selectorId);
  if (!el) return;
  el.querySelectorAll('.level-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      el.querySelectorAll('.level-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      onChange(btn.dataset.level);
    });
  });
}

_initLevelSelector('tailor-level-selector', (lvl) => { _tailorLevel = lvl; });
_initLevelSelector('ia-level-selector', (lvl) => { _iaLevel = lvl; updatePrompt(); });

// ---- Prompts par niveau pour l'assistant IA ----------------------
const LEVEL_PROMPT_RULES = {
  peu: `Règles d'adaptation (niveau SUBTIL) :
- Ajuste le titre/tagline sous le nom pour refléter le type de poste visé, de façon générique.
- Réoriente le résumé/accroche avec 2-3 mots-clés du poste, de façon naturelle et non évidente.
- NE modifie PAS les compétences, les expériences, les langues, les centres d'intérêt, la formation.
- Le CV doit rester fidèle à l'original à 95%.
- ANTI-DÉTECTION : n'écris jamais le nom de l'entreprise ciblée dans le résumé ou le titre. Le CV doit sembler naturel, pas taillé pour une seule offre.`,
  adapte: `Règles d'adaptation (niveau MODÉRÉ) :
- Ajuste le titre/tagline et réécris le résumé/accroche pour le type de poste visé.
- Réordonne les compétences existantes (sans en ajouter ni supprimer).
- Enrichis et reformule les puces d'expériences existantes (4 puces max par expérience, sans inventer de contenu absent du CV).
- NE touche PAS aux langues (garde-les toutes), aux centres d'intérêt, aux dates, aux entreprises du parcours.
- ANTI-DÉTECTION : n'écris jamais le nom de l'entreprise ciblée dans le résumé ou le titre.`,
  hyper: `Règles d'adaptation (niveau MAXIMUM) :
- Ajuste le titre/tagline et réécris complètement le résumé/accroche.
- Réorganise et reformule les compétences existantes (sans en inventer de nouvelles).
- Réécris entièrement les puces d'expériences (4 puces max par expérience, sans inventer de contenu absent du CV).
- ANTI-DÉTECTION : n'écris jamais le nom de l'entreprise ciblée dans le résumé ou le titre.
- ABSOLUMENT INTERDIT : supprimer des langues, supprimer les centres d'intérêt, inventer des compétences, modifier les dates/entreprises du parcours/diplômes.`,
};

function updatePrompt() {
  const jobDesc    = $('ia-job-desc').value.trim();
  const tplName    = $('ia-template').value;
  const wantLetter = $('ia-cover-letter').checked;
  const tpl        = TEMPLATES[tplName] || TEMPLATES['sobre'];
  const levelRules = LEVEL_PROMPT_RULES[_iaLevel] || LEVEL_PROMPT_RULES['adapte'];

  let prompt = `Agis en tant qu'expert en recrutement. Je te fournis en pièce jointe mon CV actuel en .pdf ou html.

Voici l'offre d'emploi à laquelle je postule :
---
${jobDesc || "[Collez votre offre d'emploi ici ou décrivez le poste visé]"}
---

Ton objectif est de rédiger mon nouveau CV${wantLetter ? ' ET MA LETTRE DE MOTIVATION' : ''} optimisé(s) pour ce poste, en utilisant STRICTEMENT la structure HTML fournie ci-dessous.

${levelRules}

Règles générales (non négociables) :
1. Fais d'abord une brève analyse des mots-clés de l'offre et de mon profil.
2. Remplis les balises HTML avec mes informations. Le CV doit tenir sur 1 page A4.
3. Ne modifie AUCUNE classe CSS, ne touche pas à la structure HTML.
4. Pour la photo de profil, laisse exactement le tag suivant sans le modifier : src="URL_DE_VOTRE_PHOTO_ICI".
5. Rends UNIQUEMENT le(s) bloc(s) de code HTML final, prêt(s) à être copié(s).
6. QUANTITÉS — RÈGLE CRITIQUE : le squelette est un modèle de structure, pas un modèle de quantité. Le nombre d'éléments dans chaque section (compétences, langues, expériences, formations) est indicatif. Tu dois reproduire le pattern HTML autant de fois que nécessaire pour inclure TOUS les éléments du CV fourni. Exemples : si le CV a 10 compétences, crée 10 balises. Si le CV a 4 langues, crée 4 entrées. Si le CV a 5 expériences, crée 5 blocs. Ne jamais limiter à ce que le squelette montre.
7. Pour chaque expérience professionnelle, liste 3 à 4 tâches maximum.
8. Pour les dates d'expériences, utilise le format : MM/AAAA - MM/AAAA ou MM/AAAA - Présent.

Voici le squelette du CV à remplir :
\`\`\`html
${tpl.html}
\`\`\`
`;

  if (wantLetter) {
    prompt += `
Voici le squelette de la lettre de motivation à remplir :
\`\`\`html
<div style="padding: 40px; font-family: sans-serif; font-size: 11pt; line-height: 1.5; color: #333;">
  <p><strong>Prénom Nom</strong><br>
  email@example.com &middot; +33 6 00 00 00 00<br>
  Ville</p>
  <br><br>
  <p><strong>À l'attention du responsable du recrutement</strong><br>
  [Nom de l'entreprise]</p>
  <br><br>
  <p><strong>Objet : Candidature au poste de [Titre du poste]</strong></p>
  <br>
  <p>Madame, Monsieur,</p>
  <p>[Paragraphe 1 : Accroche contextuelle (Vous)]</p>
  <p>[Paragraphe 2 : Compétences et valeur ajoutée (Moi)]</p>
  <p>[Paragraphe 3 : Projection future (Nous)]</p>
  <p>[Appel à l'action pour un entretien]</p>
  <br>
  <p>Cordialement,</p>
  <p>Prénom Nom</p>
</div>
\`\`\`
`;
  }

  $('ia-prompt').value = prompt;
}

$('ia-job-desc').addEventListener('input', updatePrompt);
$('ia-template').addEventListener('change', updatePrompt);
$('ia-cover-letter').addEventListener('change', updatePrompt);

$('ia-copy-btn').onclick = () => {
  navigator.clipboard.writeText($('ia-prompt').value).then(() => {
    const btn = $('ia-copy-btn');
    const oldText = btn.innerHTML;
    btn.textContent = 'Copié ! Collez-le dans ChatGPT ou Claude';
    btn.style.background = '#5dd39e';
    setTimeout(() => { btn.innerHTML = oldText; btn.style.background = ''; }, 3000);
  });
};

// ============================================================
// Insertion Photo Base64
// ============================================================
$('btn-photo').onclick = () => {
  if (htmlModel && !htmlModel.getValue().includes('URL_DE_VOTRE_PHOTO_ICI')) {
    alert("Aucun emplacement automatique de photo détecté.\n\nVotre photo sera insérée exactement là où se trouve actuellement votre curseur clignotant dans le code HTML.\n\nAssurez-vous d'avoir cliqué au bon endroit dans l'éditeur avant de choisir votre image !");
  }
  $('photo-upload').click();
};

$('photo-upload').onchange = e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = rev => {
    const base64 = rev.target.result;
    if (!htmlModel) return;
    const currentHtml = htmlModel.getValue();
    const photoCode   = `\n<!-- #region Photo_Base64 -->\n<img src="${base64}" alt="Photo de profil" style="width:80px; border-radius:4px;"/>\n<!-- #endregion -->\n`;

    if (currentHtml.includes('URL_DE_VOTRE_PHOTO_ICI')) {
      let newHtml = currentHtml;
      if (currentHtml.includes('src="URL_DE_VOTRE_PHOTO_ICI"')) {
        newHtml = currentHtml.replace('URL_DE_VOTRE_PHOTO_ICI', base64);
      } else {
        newHtml = currentHtml
          .replace('<!-- URL_DE_VOTRE_PHOTO_ICI -->', photoCode.trim())
          .replace('URL_DE_VOTRE_PHOTO_ICI', photoCode.trim());
      }
      htmlModel.setValue(newHtml);
      setStatus('Photo insérée avec succès dans le CV !', 'ok');
    } else {
      insertSnippet(photoCode);
      setStatus('Photo insérée là où se trouvait votre curseur.', 'ok');
    }
    setTimeout(() => {
      if (editor) editor.trigger('fold', 'editor.foldAllMarkerRegions');
    }, 100);
  };
  reader.readAsDataURL(file);
  e.target.value = '';
};

// ============================================================
// Clé API utilisateur (localStorage)
// ============================================================
const STORAGE_KEY_APIKEY = 'userApiKey';

function getUserApiKey() { return localStorage.getItem(STORAGE_KEY_APIKEY) || ''; }
function getApiHeaders() {
  const key = getUserApiKey();
  return key ? { 'X-Api-Key': key } : {};
}

$('btn-settings').addEventListener('click', () => {
  const key = getUserApiKey();
  $('settings-api-key').value = '';
  $('key-active-indicator').style.display = key ? '' : 'none';
  $('modal-settings').classList.add('open');
});
$('close-settings').addEventListener('click', () => { $('modal-settings').classList.remove('open'); });
$('modal-settings').addEventListener('click', (e) => {
  if (e.target === $('modal-settings')) $('modal-settings').classList.remove('open');
});
$('btn-settings-save').addEventListener('click', () => {
  const val = $('settings-api-key').value.trim();
  if (val) {
    localStorage.setItem(STORAGE_KEY_APIKEY, val);
    $('key-active-indicator').style.display = '';
    showToast('Clé enregistrée dans votre navigateur.', 'ok');
  }
  $('modal-settings').classList.remove('open');
});
$('btn-settings-clear').addEventListener('click', () => {
  localStorage.removeItem(STORAGE_KEY_APIKEY);
  $('settings-api-key').value = '';
  $('key-active-indicator').style.display = 'none';
  showToast('Clé effacée.', 'ok');
  $('modal-settings').classList.remove('open');
});

// ============================================================
// Streaming SSE → Monaco
// ============================================================
async function _readSseStream(resp, onChunk) {
  const reader  = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let accumulated = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6);
      if (data === '[DONE]') return accumulated;
      if (data.startsWith('[ERROR]')) throw new Error(data.slice(8).trim() || 'Erreur serveur');
      try {
        const chunk = JSON.parse(data);
        accumulated += chunk;
        if (onChunk) onChunk(accumulated);
      } catch (_) {}
    }
  }
  return accumulated;
}

async function streamToMonaco(url, body, extraHeaders, onChunk) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...extraHeaders },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let msg = 'Erreur serveur';
    try { msg = (await resp.json()).error || msg; } catch (_) {}
    throw new Error(msg);
  }
  return _readSseStream(resp, onChunk);
}

async function streamFormToMonaco(url, formData, extraHeaders, onChunk) {
  const resp = await fetch(url, {
    method: 'POST',
    // Passe le token CSRF pour les requêtes multipart
    headers: { 'X-CSRF-Token': CSRF_TOKEN, ...extraHeaders },
    body: formData,
  });
  if (!resp.ok) {
    let msg = 'Erreur serveur';
    try { msg = (await resp.json()).error || msg; } catch (_) {}
    throw new Error(msg);
  }
  return _readSseStream(resp, onChunk);
}

// ============================================================
// Panneau Import — onglets
// ============================================================
document.querySelectorAll('.import-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.import-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.import-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('import-tab-' + tab.dataset.tab).classList.add('active');
  });
});

function markCvLoaded() { switchTab('html'); }

// ============================================================
// Import helpers
// ============================================================
function _applyImportCss(docType) {
  if (!cssModel) return;
  if (docType === 'Lettre') {
    cssModel.setValue('');
  } else {
    cssModel.setValue(TEMPLATES.sobre.css);
  }
}

// ============================================================
// Import texte → HTML
// ============================================================
$('btn-text-to-html').addEventListener('click', async () => {
  const text = $('cv-text-input').value.trim();
  if (!text) { showToast("Colle d'abord le contenu de ton CV.", 'err'); return; }

  const btn    = $('btn-text-to-html');
  const status = $('import-text-status');
  btn.disabled = true;
  status.textContent = 'Conversion en cours';
  status.className   = 'import-status status-busy';

  const docType = ($('doc_type') && $('doc_type').value) || 'CV';
  try {
    const html = await streamToMonaco(
      '/api/text-to-html',
      { text, doc_type: docType },
      getApiHeaders(),
      (partial) => { if (htmlModel) htmlModel.setValue(partial); }
    );
    if (htmlModel) htmlModel.setValue(html);
    _applyImportCss(docType);
    markCvLoaded();
    showToast('CV converti en HTML avec succès.', 'ok');
    status.textContent = '';
    status.className   = 'import-status';
  } catch (err) {
    showToast(err.message, 'err');
    status.textContent = err.message;
    status.className   = 'import-status status-err';
  } finally {
    btn.disabled = false;
  }
});

// ============================================================
// Import PDF → HTML
// ============================================================
let _selectedPdfFile = null;

$('btn-pdf-pick').addEventListener('click', () => { $('pdf-upload-input').click(); });

$('pdf-upload-input').addEventListener('change', (e) => {
  _selectedPdfFile = e.target.files[0] || null;
  $('pdf-filename').textContent = _selectedPdfFile ? _selectedPdfFile.name : '';
  $('btn-pdf-to-html').disabled = !_selectedPdfFile;
  e.target.value = '';
});

$('btn-pdf-to-html').addEventListener('click', async () => {
  if (!_selectedPdfFile) return;

  const btn    = $('btn-pdf-to-html');
  const status = $('import-pdf-status');
  btn.disabled = true;
  status.textContent = 'Lecture du PDF';
  status.className   = 'import-status status-busy';

  const docType = ($('doc_type') && $('doc_type').value) || 'CV';
  const formData = new FormData();
  formData.append('file', _selectedPdfFile);
  formData.append('doc_type', docType);

  try {
    const html = await streamFormToMonaco(
      '/api/pdf-to-html',
      formData,
      getApiHeaders(),
      (partial) => {
        if (htmlModel) htmlModel.setValue(partial);
        status.textContent = `${partial.length} car. générés`;
        status.className   = 'import-status status-busy';
      }
    );
    if (htmlModel) htmlModel.setValue(html);
    _applyImportCss(docType);
    markCvLoaded();
    showToast('PDF converti en HTML avec succès.', 'ok');
    status.textContent = '';
    status.className   = 'import-status';
  } catch (err) {
    showToast(err.message, 'err');
    status.textContent = err.message;
    status.className   = 'import-status status-err';
  } finally {
    btn.disabled = false;
  }
});

// ============================================================
// Offres d'emploi sauvegardées
// ============================================================
const STORAGE_KEY_JOB_DRAFT  = 'html-to-pdf:draft:job-desc';
const STORAGE_KEY_SAVED_OFFERS = 'html-to-pdf:saved-offers';

function _getSavedOffers() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY_SAVED_OFFERS) || '[]'); } catch (_) { return []; }
}

function _setSavedOffers(list) {
  try { localStorage.setItem(STORAGE_KEY_SAVED_OFFERS, JSON.stringify(list)); } catch (_) {}
}

function _refreshOffersSelect() {
  const sel = $('saved-offers-select');
  const del = $('btn-delete-offer');
  if (!sel) return;
  const offers = _getSavedOffers();
  sel.innerHTML = `<option value="">Offres sauvegardées (${offers.length})...</option>` +
    offers.map(o => `<option value="${o.id}">${o.label}</option>`).join('');
  if (del) del.style.display = 'none';
}

function _saveCurrentOffer() {
  const content = ($('job-desc-input').value || '').trim();
  if (!content) { showToast("Aucune offre à sauvegarder.", 'err'); return; }
  const company = ($('company').value || '').trim();
  const role    = ($('role').value || '').trim();
  const date    = new Date().toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
  const label   = [company, role].filter(Boolean).join(' · ') || `Offre du ${date}`;
  const offers  = _getSavedOffers();
  const id      = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  offers.unshift({ id, label, content, date: new Date().toISOString() });
  if (offers.length > 30) offers.pop();
  _setSavedOffers(offers);
  _refreshOffersSelect();
  showToast(`Offre "${label}" sauvegardée.`, 'ok');
}

function _syncJobDesc(value) {
  const tailor = $('job-desc-input');
  const modal  = $('ia-job-desc');
  if (tailor && tailor.value !== value) tailor.value = value;
  if (modal  && modal.value  !== value) modal.value  = value;
  try { localStorage.setItem(STORAGE_KEY_JOB_DRAFT, value); } catch (_) {}
  if (typeof updatePrompt === 'function') updatePrompt();
}

// Restore draft job desc on load
(function() {
  const draft = localStorage.getItem(STORAGE_KEY_JOB_DRAFT) || '';
  if (draft) { const t = $('job-desc-input'); const m = $('ia-job-desc'); if (t) t.value = draft; if (m) m.value = draft; }
  _refreshOffersSelect();
})();

// Auto-save draft + sync on input
$('job-desc-input').addEventListener('input', (e) => { _syncJobDesc(e.target.value); });
$('ia-job-desc').addEventListener('input', (e) => { _syncJobDesc(e.target.value); });

// Save button
$('btn-save-offer').addEventListener('click', _saveCurrentOffer);

// Load saved offer on select change
$('saved-offers-select').addEventListener('change', (e) => {
  const id  = e.target.value;
  const del = $('btn-delete-offer');
  if (!id) { if (del) del.style.display = 'none'; return; }
  const offer = _getSavedOffers().find(o => o.id === id);
  if (!offer) return;
  _syncJobDesc(offer.content);
  if (del) del.style.display = '';
});

// Delete selected offer
$('btn-delete-offer').addEventListener('click', () => {
  const id = $('saved-offers-select').value;
  if (!id) return;
  const offers = _getSavedOffers().filter(o => o.id !== id);
  _setSavedOffers(offers);
  _syncJobDesc('');
  _refreshOffersSelect();
  showToast('Offre supprimée.', 'ok');
});

// ============================================================
// Tailoring — adapter à une offre
// ============================================================
$('tailor-toggle').addEventListener('click', () => {
  const body    = $('tailor-body');
  const chevron = $('tailor-chevron');
  const isOpen  = body.classList.contains('open');
  body.classList.toggle('open', !isOpen);
  chevron.classList.toggle('open', !isOpen);
});

$('btn-tailor').addEventListener('click', async () => {
  const jobDesc = $('job-desc-input').value.trim();
  if (!jobDesc) { showToast("Colle d'abord une offre d'emploi.", 'err'); return; }
  if (!htmlModel || !htmlModel.getValue().trim()) {
    showToast("Charge d'abord un CV dans l'éditeur.", 'err'); return;
  }

  saveSnapshot('Avant tailoring');

  const btn    = $('btn-tailor');
  const status = $('tailor-status');
  const atsPanel = $('ats-panel');
  btn.disabled = true;
  atsPanel.style.display = 'none';
  status.textContent = 'Adaptation en cours';
  status.className   = 'tailor-status status-busy';

  try {
    const adapted = await streamToMonaco(
      '/api/tailor',
      { html: htmlModel.getValue(), job_desc: jobDesc, level: _tailorLevel },
      getApiHeaders(),
      (partial) => {
        if (htmlModel) htmlModel.setValue(partial);
        status.textContent = `${partial.length} car. générés`;
        status.className   = 'tailor-status status-busy';
      }
    );
    if (htmlModel) htmlModel.setValue(adapted);
    showToast('CV adapté avec succès.', 'ok');
    status.textContent = '';
    status.className   = 'tailor-status';
    _renderAts(adapted, jobDesc);
  } catch (err) {
    showToast(err.message, 'err');
    status.textContent = err.message;
    status.className   = 'tailor-status status-err';
  } finally {
    btn.disabled = false;
  }
});

// ============================================================
// Score ATS
// ============================================================

const _ATS_STOP_WORDS = new Set([
  'le','la','les','de','du','des','un','une','et','ou','à','au','aux',
  'en','dans','sur','pour','par','avec','sans','que','qui','quoi','dont',
  'il','elle','ils','elles','je','tu','nous','vous','on','ce','se','sa',
  'son','ses','mon','ton','notre','votre','leur','leurs','est','sont',
  'être','avoir','faire','plus','très','bien','tout','tous','aussi',
  'the','of','and','or','to','a','an','in','on','for','with','be','is',
  'are','was','were','will','have','has','do','does','that','this','it',
]);

function _extractKeywords(text) {
  return [...new Set(
    text.toLowerCase()
        .replace(/<[^>]+>/g, ' ')
        .replace(/[^a-zàâäéèêëïîôùûüœç\s-]/gi, ' ')
        .split(/\s+/)
        .map(w => w.replace(/^-+|-+$/g, ''))
        .filter(w => w.length >= 4 && !_ATS_STOP_WORDS.has(w))
  )];
}

function _detectSections(html) {
  const lower = html.toLowerCase();
  return {
    'Résumé / Accroche': /(résumé|accroche|profil|summary|about|à propos)/i.test(html),
    'Expériences':       /(expérience|experience|emploi|poste|travail)/i.test(html),
    'Compétences':       /(compétence|competence|skill|technologie|technique)/i.test(html),
    'Langues':           /(langue|langu|language|anglais|français|allemand|espagnol|english|french)/i.test(html),
    'Formation':         /(formation|diplôme|diplome|école|ecole|université|universite|education|degree)/i.test(html),
    "Centres d'intérêt": /(intérêt|interêt|loisir|hobby|centre d|passion)/i.test(html),
  };
}

function _renderAts(cvHtml, jobDesc) {
  const panel = $('ats-panel');
  if (!panel) return;

  const jobKw  = _extractKeywords(jobDesc);
  const cvText = cvHtml.toLowerCase().replace(/<[^>]+>/g, ' ');
  const matched = jobKw.filter(kw => cvText.includes(kw));
  const missing = jobKw.filter(kw => !cvText.includes(kw)).slice(0, 20);
  const score   = jobKw.length ? Math.round((matched.length / jobKw.length) * 100) : 0;
  const cls     = score >= 70 ? 'ats-ok' : score >= 45 ? 'ats-mid' : 'ats-low';
  const barColor= score >= 70 ? '#5dd39e' : score >= 45 ? '#f5a623' : '#ff6b6b';
  const sections = _detectSections(cvHtml);

  const matchedTop = matched.slice(0, 20);
  const pillsMatched = matchedTop.map(k => `<span class="ats-pill match">${k}</span>`).join('');
  const pillsMissing = missing.map(k  => `<span class="ats-pill missing">${k}</span>`).join('');
  const sectBadges = Object.entries(sections).map(([name, ok]) =>
    `<span class="ats-section-badge ${ok ? 'found' : 'missing'}">${ok ? '✓' : '✗'} ${name}</span>`
  ).join('');

  panel.innerHTML = `
    <div class="ats-score-row">
      <div class="ats-score-circle ${cls}">${score}</div>
      <div class="ats-score-label">
        Score ATS estimé
        <span>${matched.length} / ${jobKw.length} mots-clés détectés</span>
      </div>
    </div>
    <div class="ats-bar"><div class="ats-bar-fill" style="width:0%;background:${barColor}" data-target="${score}"></div></div>
    ${matchedTop.length ? `<div class="ats-keywords-title">Mots-clés présents</div><div class="ats-pills">${pillsMatched}</div>` : ''}
    ${missing.length    ? `<div class="ats-keywords-title">Mots-clés absents</div><div class="ats-pills">${pillsMissing}</div>` : ''}
    <div class="ats-keywords-title">Sections détectées</div>
    <div class="ats-sections">${sectBadges}</div>
  `;
  panel.style.display = 'block';

  // Animate bar
  requestAnimationFrame(() => {
    const fill = panel.querySelector('.ats-bar-fill');
    if (fill) fill.style.width = fill.dataset.target + '%';
  });
}
