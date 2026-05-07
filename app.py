"""
Convertisseur HTML/CSS -> PDF (interface web locale).

Utilisation :
    Double-cliquez sur ce fichier. Le navigateur s'ouvre sur http://127.0.0.1:5050
    Collez votre HTML (CSS inclus dans <style>), remplissez eventuellement
    les champs Type/Entreprise/Poste, cliquez "Convertir en PDF".

    Chaque conversion est archivee dans Documents/CV-Archive/ avec ses
    metadonnees. Page /history pour parcourir l'archive.

Pour quitter :
    Cliquez sur le bouton "Quitter" dans la petite fenetre de controle.
"""

import io
import json as _json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

import tkinter as tk
from flask import Flask, abort, jsonify, render_template_string, request, send_file

import archive
from pdf_engine import html_to_pdf_bytes

PORT = 5050
URL = f"http://127.0.0.1:{PORT}"

PAGE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>HTML -> PDF</title>
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; height: 100%; font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #0f1115; color: #e6e6e6; overflow: hidden; }
  .wrap { display: flex; flex-direction: column; height: 100vh; padding: 16px 20px; gap: 10px; }
  .topbar { display: flex; justify-content: space-between; align-items: baseline; }
  h1 { font-size: 20px; margin: 0; }
  a { color: #4f8cff; text-decoration: none; }
  a:hover { text-decoration: underline; }

  .meta { display: grid; grid-template-columns: 110px 1fr 1fr; gap: 8px; }
  .field { display: flex; flex-direction: column; gap: 3px; }
  .field label { font-size: 11px; color: #9aa0a6; text-transform: uppercase; letter-spacing: 0.5px; }
  select, input[type=text], textarea {
    background: #1b1f27; color: #e6e6e6; border: 1px solid #2a2f3a;
    border-radius: 6px; padding: 7px 9px; font-size: 13px;
  }

  .split { display: flex; flex: 1 1 auto; min-height: 0; gap: 6px; }
  .pane { display: flex; flex-direction: column; min-height: 0; min-width: 0; border: 1px solid #2a2f3a; border-radius: 8px; overflow: hidden; }
  .pane-title { background: #14181f; color: #9aa0a6; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; padding: 6px 12px; border-bottom: 1px solid #2a2f3a; display: flex; justify-content: space-between; align-items: center; }
  .pane-title .actions-mini button, .pane-title .actions-mini select { background: #2a2f3a; color: #e6e6e6; border: 0; border-radius: 4px; padding: 3px 8px; font-size: 11px; cursor: pointer; margin-left: 4px; }
  .pane-title .actions-mini button:hover, .pane-title .actions-mini select:hover { background: #353b48; }
  .tabs { display: flex; gap: 2px; }
  .tab { background: transparent; color: #9aa0a6; border: 0; padding: 4px 12px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; cursor: pointer; border-radius: 4px; font-weight: 600; }
  .tab:hover { color: #e6e6e6; }
  .tab.active { color: #4f8cff; background: #2a2f3a; }
  #editor { flex: 1; min-height: 0; }
  #preview { flex: 1; border: 0; background: white; }
  .splitter { width: 6px; cursor: col-resize; background: transparent; }
  .splitter:hover { background: #2a2f3a; }

  .editor-pane { flex: 0 0 50%; }
  .preview-pane { flex: 1 1 50%; }

  details { color: #9aa0a6; font-size: 13px; }
  summary { cursor: pointer; padding: 4px 0; }
  .opts { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; align-items: center; }
  .opt { display: flex; gap: 6px; align-items: center; }
  .opt label { font-size: 13px; color: #c8c8c8; }
  .filename-preview { color: #9aa0a6; font-size: 12px; font-family: ui-monospace, Consolas, monospace; margin-top: 4px; }
  #notes { width: 100%; min-height: 38px; resize: vertical; margin-top: 8px; font-family: ui-monospace, Consolas, monospace; }

  .actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  button.go {
    background: #4f8cff; color: white; border: 0; border-radius: 8px;
    padding: 10px 20px; font-size: 14px; font-weight: 600; cursor: pointer;
  }
  button.go:hover { background: #3d7af0; }
  button.go:disabled { background: #444; cursor: wait; }
  button.ghost { background: #2a2f3a; color: #e6e6e6; border: 0; border-radius: 8px; padding: 10px 16px; font-size: 13px; cursor: pointer; }
  button.ghost:hover { background: #353b48; }
  #status { font-size: 13px; color: #9aa0a6; }
  #status.ok { color: #5dd39e; }
  #status.err { color: #ff6b6b; }
</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/editor/editor.main.css" />
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <h1>HTML/CSS -> PDF</h1>
    <div><a href="/history">Historique &rsaquo;</a></div>
  </div>

  <div class="meta">
    <div class="field">
      <label for="doc_type">Type</label>
      <select id="doc_type">
        <option value="CV" selected>CV</option>
        <option value="Lettre">Lettre</option>
        <option value="Autre">Autre</option>
      </select>
    </div>
    <div class="field">
      <label for="company">Entreprise</label>
      <input type="text" id="company" placeholder="Acme Corp" />
    </div>
    <div class="field">
      <label for="role">Poste</label>
      <input type="text" id="role" placeholder="Software Engineer" />
    </div>
  </div>

  <div class="split" id="split">
    <div class="pane editor-pane" id="editor-pane">
      <div class="pane-title">
        <div class="tabs">
          <button class="tab active" type="button" data-tab="html">HTML</button>
          <button class="tab" type="button" data-tab="css">CSS</button>
        </div>
        <div class="actions-mini">
          <select id="template-select" title="Charger un template">
            <option value="">Templates...</option>
            <option value="sobre">Sobre</option>
            <option value="moderne">Moderne</option>
            <option value="minimal">Minimal</option>
          </select>
          <button type="button" id="snippet-page">@page A4</button>
          <button type="button" id="snippet-pagebreak">page-break</button>
          <button type="button" id="format-btn" title="Formater (Alt+Shift+F)">Format</button>
        </div>
      </div>
      <div id="editor"></div>
    </div>
    <div class="splitter" id="splitter"></div>
    <div class="pane preview-pane">
      <div class="pane-title">
        <span>Prévisualisation</span>
        <div class="actions-mini">
          <button type="button" id="refresh-preview">Rafraichir</button>
        </div>
      </div>
      <iframe id="preview" sandbox="allow-same-origin"></iframe>
    </div>
  </div>

  <details>
    <summary>Options PDF (avancees)</summary>
    <div class="opts">
      <div class="opt">
        <label for="format">Format</label>
        <select id="format">
          <option value="A4" selected>A4</option>
          <option value="Letter">Letter</option>
          <option value="Legal">Legal</option>
        </select>
      </div>
      <div class="opt">
        <label for="margin">Marges</label>
        <select id="margin">
          <option value="0" selected>Aucune (CSS gere tout)</option>
          <option value="10mm">10 mm</option>
          <option value="15mm">15 mm</option>
          <option value="20mm">20 mm</option>
        </select>
      </div>
      <div class="opt">
        <label for="filename">Nom du fichier</label>
        <input type="text" id="filename" placeholder="auto" />
      </div>
      <div class="opt">
        <label><input type="checkbox" id="bg" checked /> Inclure les arrieres-plans</label>
      </div>
    </div>
    <div class="filename-preview" id="filename_preview"></div>
    <textarea id="notes" placeholder="Notes pour vous-meme, conservees dans l'archive..."></textarea>
  </details>

  <div class="actions">
    <button id="go" class="go">Convertir en PDF</button>
    <button id="clear" class="ghost" type="button">Effacer</button>
    <span id="status"></span>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/loader.js"></script>
<script>
const $ = (id) => document.getElementById(id);
const setStatus = (msg, cls) => { const s = $('status'); s.textContent = msg; s.className = cls || ''; };

const STORAGE_KEY_HTML = 'html-to-pdf:draft:html';
const STORAGE_KEY_CSS = 'html-to-pdf:draft:css';
const STORAGE_KEY_TAB = 'html-to-pdf:draft:tab';

const TEMPLATES = {
  sobre: {
    html: `<div class="resume-template-1 resume-template-renderer">

  <section class="resume-template-renderer-section personal-data">
    <h2 class="resume-template-renderer-section__title">Informations personnelles</h2>
    <div class="personal-data__photo" style="background:#eee;"></div>
    <div class="personal-data__title-row">
      <span class="personal-data__name">Prenom Nom</span><span class="personal-data__desired-job-title">Titre du poste</span>
    </div>
    <div class="personal-data__contact-row">
      Ville, Pays &middot; email@example.com &middot; +33 6 00 00 00 00 &middot; linkedin.com/in/profil
    </div>
  </section>

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

.resume-template-1.resume-template-renderer {
  padding: 24px 50px 20px;
}

.resume-template-1.resume-template-renderer .resume-template-renderer-section {
  border-top: 2px solid var(--resume-template-customization-color);
  padding-top: 7px;
}

.resume-template-1.resume-template-renderer .resume-template-renderer-section .resume-template-renderer-section__title {
  margin-bottom: 8px;
  text-transform: uppercase;
  font-size: 8.5pt;
  letter-spacing: 0.5px;
  color: #555;
  font-weight: 500;
}

.resume-template-1.resume-template-renderer .resume-template-renderer-section.personal-data {
  border-top: none;
  padding-top: 0;
}

.resume-template-1.resume-template-renderer .resume-template-renderer-section.personal-data .resume-template-renderer-section__title {
  display: none;
}

.resume-template-1.resume-template-renderer .personal-data {
  display: block;
  margin-bottom: 10px;
  min-height: 80px;
  padding-left: calc(25% + 0px);
  position: relative;
}

.resume-template-1.resume-template-renderer .personal-data .personal-data__photo {
  aspect-ratio: 1;
  left: 0;
  position: absolute;
  width: 80px;
  top: 0;
}

.resume-template-1.resume-template-renderer .personal-data .personal-data__photo img {
  width: 100%;
  height: 100%;
  border-radius: 6px;
  object-fit: cover;
  display: block;
}

.resume-template-1.resume-template-renderer .personal-data .personal-data__title-row {
  margin-bottom: 4px;
}

.resume-template-1.resume-template-renderer .personal-data .personal-data__name,
.resume-template-1.resume-template-renderer .personal-data .personal-data__desired-job-title {
  color: #000;
  font-size: 14pt;
  font-weight: 500;
}

.resume-template-1.resume-template-renderer .personal-data .personal-data__desired-job-title::before {
  content: ", ";
}

.resume-template-1.resume-template-renderer .personal-data .personal-data__contact-row {
  font-size: 9.5pt;
  color: #555;
}

.resume-template-1.resume-template-renderer .summary-objective {
  display: flex;
  margin-bottom: 6px;
}

.resume-template-1.resume-template-renderer .summary-objective .summary-objective__title {
  flex-shrink: 0;
  width: 25%;
  margin-bottom: 0;
}

.resume-template-1.resume-template-renderer .summary-objective .summary-objective__content {
  flex: 1;
}

.resume-template-1.resume-template-renderer .entry-list .entry-list__item {
  display: block;
  padding-bottom: 7px;
}

.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__title {
  color: #000;
  font-weight: 500;
  display: inline;
}

.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__date {
  float: right;
  color: #555;
  font-weight: 400;
}

.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__subtitle {
  color: #000;
  font-weight: 600;
  display: inline;
}

.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__location {
  color: #787673;
  font-weight: 400;
  display: inline;
  margin-left: 4px;
}

.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__company-row {
  display: block;
  margin-top: 1px;
  clear: both;
}

.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__description {
  margin-top: 3px;
  clear: both;
}

.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__description ul {
  list-style-type: disc;
  padding-left: 14px;
}

.resume-template-1.resume-template-renderer .entry-list .entry-list__item .entry-list__description li {
  margin-bottom: 1px;
}

.resume-template-1.resume-template-renderer .entry-list .avoid-page-break .entry-list__item {
  padding-bottom: 0;
}

.resume-template-1.resume-template-renderer .plain-list {
  display: flex;
  margin-bottom: 6px;
}

.resume-template-1.resume-template-renderer .plain-list .resume-template-renderer-section__title {
  flex-shrink: 0;
  width: 25%;
  margin-bottom: 0;
}

.resume-template-1.resume-template-renderer .plain-list .plain-list__items {
  display: flex;
  flex-wrap: wrap;
  gap: 3px 0;
  flex: 1;
}

.resume-template-1.resume-template-renderer .plain-list .plain-list__items .plain-list__item {
  color: #000;
  font-weight: 500;
  padding-right: 12px;
  width: 33.33%;
}

.resume-template-1.resume-template-renderer .languages {
  display: flex;
  margin-bottom: 6px;
}

.resume-template-1.resume-template-renderer .languages .resume-template-renderer-section__title {
  flex-shrink: 0;
  width: 25%;
  margin-bottom: 0;
}

.resume-template-1.resume-template-renderer .languages .languages__items {
  display: flex;
  flex-grow: 1;
  flex-wrap: wrap;
  gap: 6px 0;
}

.resume-template-1.resume-template-renderer .languages .languages__items .languages__item {
  display: flex;
  flex-wrap: wrap;
  padding-right: 12px;
  width: 33.33%;
}

.resume-template-1.resume-template-renderer .languages .languages__items .languages__item .languages__name {
  color: #000;
  font-weight: 500;
  margin-right: 4px;
}

.resume-template-1.resume-template-renderer .languages .languages__items .languages__item .languages__description {
  color: #787673;
}

.resume-template-1.resume-template-renderer .languages .languages__items .languages__item .languages__description::before {
  content: "(";
}

.resume-template-1.resume-template-renderer .languages .languages__items .languages__item .languages__description::after {
  content: ")";
}`,
  },
  moderne: {
    html: `<header class="cv-head">
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
    css: `@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color: #1e293b; line-height: 1.55; font-size: 10.5pt; }
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
    html: `<h1>Prenom Nom</h1>
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
    css: `@page { size: A4; margin: 22mm; }
body { font: 11pt/1.6 Georgia, "Times New Roman", serif; color: #222; }
h1 { font-size: 22pt; font-weight: normal; margin: 0 0 4px; }
h2 { font-size: 13pt; font-weight: normal; margin: 18px 0 6px; border-bottom: 1px solid #ccc; padding-bottom: 2px; }
p { margin: 0 0 6px; }
.meta { color: #666; margin-bottom: 18px; }
strong { font-weight: 600; }`,
  },
};

let editor;
let htmlModel;
let cssModel;
let activeTab = 'html';

function mergedHtml() {
  const html = htmlModel ? htmlModel.getValue() : '';
  const css = cssModel ? cssModel.getValue() : '';
  if (!css.trim()) return html;
  if (/<\/head>/i.test(html)) {
    return html.replace(/<\/head>/i, `<style>\n${css}\n</style>\n</head>`);
  }
  if (/<html[\s>]/i.test(html)) {
    return html.replace(/<html([^>]*)>/i, `<html$1>\n<head><meta charset="utf-8"><style>\n${css}\n</style></head>`);
  }
  return `<!DOCTYPE html>\n<html lang="fr">\n<head>\n<meta charset="utf-8">\n<style>\n${css}\n</style>\n</head>\n<body>\n${html}\n</body>\n</html>`;
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  if (editor) editor.setModel(tab === 'css' ? cssModel : htmlModel);
  try { localStorage.setItem(STORAGE_KEY_TAB, tab); } catch (_) {}
}

function slug(s) {
  if (!s) return '';
  return s.normalize('NFKD').replace(/[̀-ͯ]/g, '')
          .replace(/[^\w\s-]/g, '').trim().replace(/[\s_-]+/g, '');
}

function autoFilename() {
  const today = new Date().toISOString().slice(0, 10);
  const docType = $('doc_type').value || 'Document';
  const company = slug($('company').value);
  const role = slug($('role').value);
  const tail = company || role || '';
  return tail ? `${docType}_Hariss_${tail}_${today}.pdf` : `${docType}_Hariss_${today}.pdf`;
}

function refreshFilenamePreview() {
  const custom = $('filename').value.trim();
  const auto = autoFilename();
  $('filename_preview').textContent = custom ? `Nom : ${custom}` : `Nom auto : ${auto}`;
}

['doc_type', 'company', 'role', 'filename'].forEach(id => $(id).addEventListener('input', refreshFilenamePreview));
refreshFilenamePreview();

let previewTimer;
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    $('preview').srcdoc = mergedHtml();
  }, 400);
}

require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' } });
require(['vs/editor/editor.main'], function () {
  const storedHtml = localStorage.getItem(STORAGE_KEY_HTML);
  const storedCss = localStorage.getItem(STORAGE_KEY_CSS);
  const wantTab = localStorage.getItem(STORAGE_KEY_TAB) || 'html';
  const fallback = TEMPLATES.sobre;

  htmlModel = monaco.editor.createModel(storedHtml !== null ? storedHtml : fallback.html, 'html');
  cssModel  = monaco.editor.createModel(storedCss  !== null ? storedCss  : fallback.css,  'css');

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
    try { localStorage.setItem(STORAGE_KEY_HTML, htmlModel.getValue()); } catch (_) {}
    schedulePreview();
  });
  cssModel.onDidChangeContent(() => {
    try { localStorage.setItem(STORAGE_KEY_CSS, cssModel.getValue()); } catch (_) {}
    schedulePreview();
  });

  document.querySelectorAll('.tab').forEach(btn => {
    btn.onclick = () => switchTab(btn.dataset.tab);
  });
  switchTab(wantTab);

  $('preview').srcdoc = mergedHtml();

  $('format-btn').onclick = () => editor.getAction('editor.action.formatDocument').run();
  $('snippet-page').onclick = () => { switchTab('css'); insertSnippet('@page { size: A4; margin: 15mm; }\n'); };
  $('snippet-pagebreak').onclick = () => { switchTab('html'); insertSnippet('<div style="page-break-after: always;"></div>\n'); };
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

  const params = new URLSearchParams(location.search);
  const loadId = params.get('load');
  if (loadId) {
    fetch(`/api/history/${encodeURIComponent(loadId)}`).then(r => r.json()).then(entry => {
      if (!entry || !entry.id) return;
      $('doc_type').value = entry.doc_type || 'CV';
      $('company').value = entry.company || '';
      $('role').value = entry.role || '';
      $('notes').value = entry.notes || '';
      return fetch(`/api/history/${encodeURIComponent(loadId)}/html`).then(r => r.text()).then(html => {
        htmlModel.setValue(html);
        cssModel.setValue('');
        switchTab('html');
      });
    }).then(refreshFilenamePreview);
  }
});

function insertSnippet(text) {
  if (!editor) return;
  const sel = editor.getSelection();
  editor.executeEdits('snippet', [{ range: sel, text, forceMoveMarkers: true }]);
  editor.focus();
}

$('clear').onclick = () => {
  if (htmlModel) htmlModel.setValue('');
  if (cssModel) cssModel.setValue('');
  ['company', 'role', 'filename', 'notes'].forEach(id => $(id).value = '');
  setStatus(''); refreshFilenamePreview();
  try { localStorage.removeItem(STORAGE_KEY_HTML); localStorage.removeItem(STORAGE_KEY_CSS); } catch (_) {}
};

$('go').onclick = async () => {
  const html = mergedHtml();
  if (!html.trim()) { setStatus("Editez du HTML d'abord.", 'err'); return; }
  const btn = $('go'); btn.disabled = true; btn.textContent = 'Conversion...';
  setStatus('Generation du PDF...', '');
  try {
    const res = await fetch('/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        html,
        doc_type: $('doc_type').value,
        company: $('company').value.trim(),
        role: $('role').value.trim(),
        notes: $('notes').value.trim(),
        format: $('format').value,
        margin: $('margin').value,
        background: $('bg').checked,
        filename: $('filename').value.trim(),
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'Erreur inconnue' }));
      setStatus('Erreur : ' + (err.error || res.statusText), 'err');
      return;
    }
    const meta = JSON.parse(res.headers.get('X-Archive-Entry') || '{}');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = meta.filename || 'document.pdf';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    setStatus(`PDF telecharge et archive sous ${meta.filename}`, 'ok');
  } catch (e) {
    setStatus('Erreur : ' + e.message, 'err');
  } finally {
    btn.disabled = false; btn.textContent = 'Convertir en PDF';
  }
};

(function initSplitter() {
  const split = $('split');
  const splitter = $('splitter');
  const editorPane = $('editor-pane');
  let dragging = false;
  splitter.addEventListener('mousedown', e => { dragging = true; e.preventDefault(); document.body.style.cursor = 'col-resize'; });
  window.addEventListener('mousemove', e => {
    if (!dragging) return;
    const rect = split.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = Math.max(15, Math.min(85, (x / rect.width) * 100));
    editorPane.style.flexBasis = `${pct}%`;
  });
  window.addEventListener('mouseup', () => { dragging = false; document.body.style.cursor = ''; });
})();
</script>
</body>
</html>
"""

HISTORY_PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Historique</title>
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #0f1115; color: #e6e6e6; }
  .wrap { max-width: 1200px; margin: 0 auto; padding: 24px; }
  .topbar { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; }
  h1 { font-size: 22px; margin: 0; }
  a { color: #4f8cff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  input#search { background: #1b1f27; color: #e6e6e6; border: 1px solid #2a2f3a; border-radius: 6px; padding: 8px 12px; font-size: 13px; width: 100%; margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #2a2f3a; font-size: 13px; vertical-align: top; }
  th { color: #9aa0a6; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }
  td.actions { text-align: right; white-space: nowrap; }
  td.actions button, td.actions a.btn { margin-left: 6px; display: inline-block; }
  button.ghost, a.btn {
    background: #2a2f3a; color: #e6e6e6; border: 0; border-radius: 5px;
    padding: 5px 10px; font-size: 12px; cursor: pointer; text-decoration: none;
  }
  button.ghost:hover, a.btn:hover { background: #353b48; text-decoration: none; }
  button.danger { background: #5a1e1e; }
  button.danger:hover { background: #7a2828; }
  .empty { color: #9aa0a6; padding: 24px; text-align: center; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; background: #2a2f3a; color: #c8c8c8; }
  tr:hover { background: #14181f; }
  .filename { font-family: ui-monospace, Consolas, monospace; font-size: 12px; color: #c8c8c8; }
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <h1>Historique</h1>
    <a href="/">&lsaquo; Retour</a>
  </div>
  <input type="text" id="search" placeholder="Rechercher entreprise, poste, notes..." />
  <div id="root"></div>
</div>
<script>
const $ = (id) => document.getElementById(id);
let entries = [];

function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'onclick') node.onclick = v;
    else if (k === 'text') node.textContent = v;
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
  const id = e.id;
  return el('tr', { 'data-id': id }, [
    el('td', { text: fmtDate(e.created_at) }),
    el('td', {}, [el('span', { class: 'badge', text: e.doc_type || '' })]),
    el('td', { text: e.company || '-' }),
    el('td', { text: e.role || '-' }),
    el('td', { class: 'filename', title: e.filename, text: e.filename || '' }),
    el('td', { class: 'actions' }, [
      el('a', { class: 'btn', href: `/api/history/${encodeURIComponent(id)}/pdf`, target: '_blank', text: 'Voir PDF' }),
      el('a', { class: 'btn', href: `/?load=${encodeURIComponent(id)}`, text: 'Recharger' }),
      el('button', { class: 'ghost', onclick: () => openLocal(id), text: 'Ouvrir local' }),
      el('button', { class: 'ghost danger', onclick: () => del(id), text: 'Supprimer' }),
    ]),
  ]);
}

function render(filter='') {
  const f = filter.toLowerCase();
  const filtered = !f ? entries : entries.filter(e =>
    (e.company || '').toLowerCase().includes(f) ||
    (e.role || '').toLowerCase().includes(f) ||
    (e.doc_type || '').toLowerCase().includes(f) ||
    (e.notes || '').toLowerCase().includes(f) ||
    (e.filename || '').toLowerCase().includes(f)
  );
  const root = $('root');
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

async function load() {
  const r = await fetch('/api/history');
  entries = await r.json();
  render($('search').value);
}

async function del(id) {
  if (!confirm('Supprimer cette entree (PDF et HTML) ?')) return;
  const r = await fetch(`/api/history/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (r.ok) load();
}

async function openLocal(id) {
  await fetch(`/api/history/${encodeURIComponent(id)}/open`, { method: 'POST' });
}

$('search').addEventListener('input', e => render(e.target.value));
load();
</script>
</body>
</html>
"""

app = Flask(__name__)


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/history")
def history_page():
    return render_template_string(HISTORY_PAGE)


@app.route("/convert", methods=["POST"])
def convert():
    data = request.get_json(silent=True) or {}
    html = data.get("html", "")
    if not html.strip():
        return jsonify({"error": "HTML vide."}), 400

    fmt = data.get("format", "A4")
    margin = data.get("margin", "0")
    background = bool(data.get("background", True))
    doc_type = data.get("doc_type", "CV")
    company = (data.get("company") or "").strip()
    role = (data.get("role") or "").strip()
    notes = (data.get("notes") or "").strip()
    custom_filename = (data.get("filename") or "").strip()

    try:
        pdf_bytes = html_to_pdf_bytes(html, page_format=fmt, margin=margin, background=background)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    entry = archive.save_document(
        html=html,
        pdf_bytes=pdf_bytes,
        doc_type=doc_type,
        company=company,
        role=role,
        notes=notes,
        custom_filename=custom_filename,
    )

    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=entry["filename"],
    )
    response.headers["X-Archive-Entry"] = _json.dumps({
        "id": entry["id"], "filename": entry["filename"], "created_at": entry["created_at"],
    })
    response.headers["Access-Control-Expose-Headers"] = "X-Archive-Entry"
    return response


@app.route("/api/history")
def api_history():
    return jsonify(archive.list_documents())


@app.route("/api/history/<doc_id>")
def api_history_get(doc_id):
    entry = archive.get_document(doc_id)
    if not entry:
        abort(404)
    return jsonify(entry)


@app.route("/api/history/<doc_id>/html")
def api_history_html(doc_id):
    entry = archive.get_document(doc_id)
    if not entry:
        abort(404)
    html_path = Path(entry["html_path"])
    if not html_path.exists():
        abort(404)
    return html_path.read_text(encoding="utf-8"), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/api/history/<doc_id>/pdf")
def api_history_pdf(doc_id):
    entry = archive.get_document(doc_id)
    if not entry:
        abort(404)
    pdf_path = Path(entry["pdf_path"])
    if not pdf_path.exists():
        abort(404)
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=False, download_name=entry["filename"])


@app.route("/api/history/<doc_id>/open", methods=["POST"])
def api_history_open(doc_id):
    entry = archive.get_document(doc_id)
    if not entry:
        abort(404)
    pdf_path = Path(entry["pdf_path"])
    if not pdf_path.exists():
        abort(404)
    try:
        os.startfile(str(pdf_path))
        return jsonify({"ok": True})
    except (AttributeError, OSError) as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<doc_id>", methods=["DELETE"])
def api_history_delete(doc_id):
    if archive.delete_document(doc_id):
        return jsonify({"ok": True})
    abort(404)


def lancer_serveur():
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


def lancer_navigateur():
    time.sleep(1.0)
    webbrowser.open(URL)


def fenetre_controle():
    root = tk.Tk()
    root.title("Convertisseur HTML -> PDF")
    root.resizable(False, False)
    largeur, hauteur = 360, 160
    x = (root.winfo_screenwidth() - largeur) // 2
    y = (root.winfo_screenheight() - hauteur) // 2
    root.geometry(f"{largeur}x{hauteur}+{x}+{y}")

    tk.Label(root, text="Le serveur tourne sur :", pady=8).pack()
    lien = tk.Label(root, text=URL, fg="#1a73e8", cursor="hand2", font=("Segoe UI", 10, "underline"))
    lien.pack()
    lien.bind("<Button-1>", lambda _e: webbrowser.open(URL))

    tk.Label(root, text="Fermez cette fenetre pour arreter.", fg="#666", pady=8).pack()

    def quitter():
        root.destroy()
        sys.exit(0)

    tk.Button(root, text="Quitter", width=14, command=quitter).pack(pady=6)
    root.protocol("WM_DELETE_WINDOW", quitter)
    root.mainloop()


def main():
    archive.ensure_archive_dir()
    threading.Thread(target=lancer_serveur, daemon=True).start()
    threading.Thread(target=lancer_navigateur, daemon=True).start()
    fenetre_controle()


if __name__ == "__main__":
    main()
