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
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    _HAS_TKINTER = True
except ImportError:
    _HAS_TKINTER = False

from flask import Flask, Response, abort, jsonify, render_template_string, request, send_file

import archive
from pdf_engine import html_to_pdf_bytes, VALID_FORMATS, VALID_MARGINS

PORT = 5050
URL = f"http://127.0.0.1:{PORT}"

# Limite de taille du corps de requête pour /convert (8 Mo)
MAX_HTML_BYTES = 8 * 1024 * 1024

# ---------------------------------------------------------------------------
# PAGE PRINCIPALE (éditeur Monaco + prévisualisation)
# Raw string : évite les warnings de syntaxe Python sur les regex JS.
# N'utilise PAS Jinja2 — retourné comme Response directe.
# ---------------------------------------------------------------------------
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
  
  /* Modal IA */
  .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.7); align-items: center; justify-content: center; backdrop-filter: blur(4px); }
  .modal-content { background-color: #181b21; padding: 32px; border: 1px solid #333842; border-radius: 12px; width: 680px; max-width: 95%; color: #e6e6e6; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
  .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
  .modal-header h2 { margin: 0; font-size: 22px; color: #fff; display: flex; align-items: center; gap: 8px; }
  .close-modal { color: #9aa0a6; font-size: 28px; font-weight: bold; cursor: pointer; transition: color 0.2s; }
  .close-modal:hover { color: #fff; }
  .ia-step-title { font-size: 14px; font-weight: 600; color: #e6e6e6; margin-bottom: 8px; margin-top: 20px; display: block; }
  .modal-content textarea { width: 100%; background: #111418; color: #fff; border: 1px solid #333842; border-radius: 8px; padding: 12px; font-size: 13px; line-height: 1.5; resize: vertical; transition: border-color 0.2s; }
  .modal-content textarea:focus { outline: none; border-color: #4f8cff; }
  .ia-options { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; background: #111418; padding: 16px; border-radius: 8px; border: 1px solid #333842; }
  .ia-options select { background: #1b1f27; color: #e6e6e6; border: 1px solid #333842; padding: 6px 12px; border-radius: 6px; font-size: 13px; outline: none; }
  .ia-options select:focus { border-color: #4f8cff; }
  .btn-copier { display: block; width: 100%; padding: 14px; font-size: 15px; font-weight: 600; text-align: center; background: linear-gradient(135deg, #4f8cff, #2563eb); color: white; border: none; border-radius: 8px; margin-top: 24px; cursor: pointer; transition: transform 0.1s, box-shadow 0.2s; }
  .btn-copier:hover { box-shadow: 0 4px 12px rgba(79, 140, 255, 0.4); transform: translateY(-1px); }
  .btn-copier:active { transform: translateY(1px); }

  /* Responsive Mobile */
  @media (max-width: 768px) {
    html, body { height: auto; overflow: visible; }
    .wrap { height: auto; min-height: 100vh; padding: 12px; }
    .topbar { flex-direction: column; gap: 12px; align-items: flex-start; }
    .meta { grid-template-columns: 1fr; gap: 12px; }
    .split { flex-direction: column; flex: none; height: 800px; } /* Hauteur fixe pour split sur mobile */
    .editor-pane, .preview-pane { flex: 1 1 50% !important; min-height: 300px; width: 100% !important; }
    .splitter { width: 100%; height: 12px; cursor: row-resize; background: #1b1f27; }
    
    .modal-content { padding: 20px; width: 100%; border-radius: 8px; }
    .modal-header { flex-direction: column; align-items: flex-start; gap: 12px; }
    .close-modal { position: absolute; top: 16px; right: 16px; }
    .ia-options { flex-direction: column; align-items: flex-start; gap: 12px; }
    .ia-options select { width: 100%; }
  }
</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/editor/editor.main.css" />
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <h1>HTML/CSS -> PDF</h1>
    <div style="display: flex; align-items: center; gap: 12px;">
      <button id="btn-ia" class="ghost" style="color: #f5a623; border: 1px solid #f5a623; padding: 6px 12px;">✨ Assistant IA</button>
      <a href="/history">Historique &rsaquo;</a>
    </div>
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
          <input type="file" id="photo-upload" accept="image/*" style="display: none;">
          <button type="button" id="btn-photo" title="Insérer une image dans le HTML">📸 Insérer ma photo</button>
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

<!-- Modal IA -->
<div id="modal-ia" class="modal">
  <div class="modal-content">
    <div class="modal-header">
      <h2><span style="font-size: 24px;">✨</span> Assistant IA</h2>
      <span class="close-modal" id="close-modal">&times;</span>
    </div>
    <div class="modal-body">
      <p style="margin-top:0; font-size: 14px; line-height: 1.5; color: #a1a7b0; margin-bottom: 24px;">
        Générez le prompt parfait pour ChatGPT ou Claude. L'IA rédigera votre CV en gardant le bon formatage HTML, prêt à être converti en PDF.
      </p>
      
      <span class="ia-step-title">1. Offre d'emploi ciblé :</span>
      <textarea id="ia-job-desc" placeholder="Collez la description du poste ici. Plus il y a de détails, mieux l'IA pourra adapter votre CV..." style="height: 100px;"></textarea>
      
      <div class="ia-options">
        <div style="display: flex; align-items: center; gap: 12px;">
          <span class="ia-step-title" style="margin: 0;">2. Paramètres :</span>
          <select id="ia-template">
            <option value="sobre">Design : Sobre</option>
            <option value="moderne">Design : Moderne</option>
            <option value="minimal">Design : Minimal</option>
          </select>
        </div>
        <label style="font-size:14px; cursor: pointer; display: flex; align-items: center; gap: 8px; color: #e6e6e6;">
          <input type="checkbox" id="ia-cover-letter" style="width: 16px; height: 16px;"> 
          Inclure une lettre de motivation
        </label>
      </div>

      <span class="ia-step-title">3. Prompt généré (à copier) :</span>
      <p style="font-size: 12px; color: #9aa0a6; margin-bottom: 8px;">Donnez ce texte à l'IA, en lui fournissant votre ancien CV en pièce jointe.</p>
      <textarea id="ia-prompt" readonly style="height: 180px; font-family: 'Consolas', monospace; font-size: 12px;"></textarea>
      
      <button id="ia-copy-btn" class="btn-copier">📋 Copier le prompt magique</button>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/loader.js"></script>
<script>
const $ = (id) => document.getElementById(id);
const setStatus = (msg, cls) => { const s = $('status'); s.textContent = msg; s.className = cls || ''; };

const STORAGE_KEY_HTML = 'html-to-pdf:draft:html';
const STORAGE_KEY_CSS  = 'html-to-pdf:draft:css';
const STORAGE_KEY_TAB  = 'html-to-pdf:draft:tab';
const HISTORY_KEY      = 'cv-history';

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

// ---- mergedHtml : fusion HTML + CSS avec échappement anti-injection --------
function mergedHtml() {
  const html = htmlModel ? htmlModel.getValue() : '';
  const css  = cssModel  ? cssModel.getValue()  : '';
  if (!css.trim()) return html;
  // Empêcher la fermeture prématurée du bloc <style> par du CSS malformé.
  // <\/style> est reconnu par les parseurs CSS comme du contenu valide
  // tout en bloquant la correspondance du tokeniseur HTML.
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
  if (editor) editor.setModel(tab === 'css' ? cssModel : htmlModel);
  try { localStorage.setItem(STORAGE_KEY_TAB, tab); } catch (_) {}
}

// ---- slug JS : aligné avec la version Python (NFKD + ASCII) ---------------
function slug(s) {
  if (!s) return '';
  // Supprimer les diacritiques (U+0300-U+036F : bloc "Combining Diacritical Marks")
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
  return tail ? `${docType}_Hariss_${tail}_${today}.pdf` : `${docType}_Hariss_${today}.pdf`;
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

// ---- Prévisualisation avec debounce ----------------------------------------
let previewTimer;
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => { $('preview').srcdoc = mergedHtml(); }, 400);
}

// ---- Initialisation Monaco -------------------------------------------------
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

  // Bouton Format — guard contre un model sans formateur disponible
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

  // ---- Chargement depuis l'historique (?load= ou ?htmlUrl=) ----------------
  const params   = new URLSearchParams(location.search);
  const loadId   = params.get('load');
  const htmlUrl  = params.get('htmlUrl');  // URL Blob directe (optionnel)

  if (loadId) {
    // 1. Chercher d'abord dans le localStorage (plus rapide, marche offline)
    let localEntry = null;
    try {
      const hist = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
      localEntry = hist.find(e => e.id === loadId) || null;
    } catch (_) {}

    if (localEntry) {
      // Restaurer les métadonnées immédiatement
      $('doc_type').value = localEntry.doc_type || 'CV';
      $('company').value  = localEntry.company  || '';
      $('role').value     = localEntry.role     || '';
      $('notes').value    = localEntry.notes    || '';
      $('ia-job-desc').value = localEntry.job_desc || '';
      if(typeof updatePrompt === 'function') updatePrompt();
      refreshFilenamePreview();

      // Charger le HTML depuis le Blob ou l'URL passée en param
      const src = htmlUrl || localEntry.html_url || '';
      if (src) {
        fetch(src)
          .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.text();
          })
          .then(h => {
            htmlModel.setValue(h);
            cssModel.setValue('');
            switchTab('html');
          })
          .catch(err => setStatus('Chargement HTML echoue : ' + err.message, 'err'));
      }
    } else {
      // 2. Fallback : API serveur (local dev ou entrée sans localStorage)
      fetch(`/api/history/${encodeURIComponent(loadId)}`)
        .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then(entry => {
          if (!entry || !entry.id) return;
          $('doc_type').value = entry.doc_type || 'CV';
          $('company').value  = entry.company  || '';
          $('role').value     = entry.role     || '';
          $('notes').value    = entry.notes    || '';
          $('ia-job-desc').value = entry.job_desc || '';
          if(typeof updatePrompt === 'function') updatePrompt();
          refreshFilenamePreview();

          const src = htmlUrl || entry.html_blob_url || '';
          return (src
            ? fetch(src)
            : fetch(`/api/history/${encodeURIComponent(loadId)}/html`)
          )
            .then(r => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
            .then(h => {
              htmlModel.setValue(h);
              cssModel.setValue('');
              switchTab('html');
            });
        })
        .catch(err => setStatus('Chargement echoue : ' + err.message, 'err'));
    }
  }
});

function insertSnippet(text) {
  if (!editor) return;
  const sel = editor.getSelection();
  editor.executeEdits('snippet', [{ range: sel, text, forceMoveMarkers: true }]);
  editor.focus();
}

// ---- Effacer ---------------------------------------------------------------
$('clear').onclick = () => {
  if (htmlModel) htmlModel.setValue('');
  if (cssModel)  cssModel.setValue('');
  ['company', 'role', 'filename', 'notes'].forEach(id => $(id).value = '');
  setStatus('');
  refreshFilenamePreview();
  try {
    localStorage.removeItem(STORAGE_KEY_HTML);
    localStorage.removeItem(STORAGE_KEY_CSS);
  } catch (_) {}
};

// ---- Convertir en PDF ------------------------------------------------------
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
    const meta        = JSON.parse(res.headers.get('X-Archive-Entry') || '{}');
    const pdfBlobUrl  = res.headers.get('X-Blob-PDF-URL')  || '';
    const htmlBlobUrl = res.headers.get('X-Blob-HTML-URL') || '';

    const blob    = await res.blob();
    const objUrl  = URL.createObjectURL(blob);
    const a       = document.createElement('a');
    a.href        = objUrl;
    a.download    = meta.filename || 'document.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Révoquer après un délai pour laisser le téléchargement commencer
    setTimeout(() => URL.revokeObjectURL(objUrl), 10_000);

    setStatus(`PDF telecharge : ${meta.filename}`, 'ok');

    // Persistance dans localStorage si Vercel Blob est actif
    if (pdfBlobUrl) {
      try {
        const hist = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
        hist.unshift({
          id:         meta.id || crypto.randomUUID(),
          filename:   meta.filename,
          created_at: meta.created_at,
          doc_type:   $('doc_type').value,
          company:    $('company').value.trim(),
          role:       $('role').value.trim(),
          notes:      $('notes').value.trim(),
          job_desc:   $('ia-job-desc').value.trim(),
          pdf_url:    pdfBlobUrl,
          html_url:   htmlBlobUrl,
        });
        localStorage.setItem(HISTORY_KEY, JSON.stringify(hist.slice(0, 100)));
      } catch (_) {}
    }
  } catch (e) {
    setStatus('Erreur : ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Convertir en PDF';
  }
};

// ---- Splitter redimensionnable ---------------------------------------------
(function initSplitter() {
  const split      = $('split');
  const splitter   = $('splitter');
  const editorPane = $('editor-pane');
  let dragging     = false;

  const onStart = (e) => {
    dragging = true;
    // Eviter preventDefault sur touchstart si non necessaire, mais requis ici pour bloquer le scroll
    if (e.cancelable) e.preventDefault();
    const isMobile = window.innerWidth <= 768;
    document.body.style.cursor = isMobile ? 'row-resize' : 'col-resize';
  };

  const onMove = (e) => {
    if (!dragging) return;
    const rect = split.getBoundingClientRect();
    const isMobile = window.innerWidth <= 768;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    
    if (isMobile) {
      const y = clientY - rect.top;
      const pct = Math.max(15, Math.min(85, (y / rect.height) * 100));
      editorPane.style.flexBasis = `${pct}%`;
    } else {
      const x = clientX - rect.left;
      const pct = Math.max(15, Math.min(85, (x / rect.width) * 100));
      editorPane.style.flexBasis = `${pct}%`;
    }
  };

  const onEnd = () => {
    dragging = false;
    document.body.style.cursor = '';
  };

  splitter.addEventListener('mousedown', onStart);
  splitter.addEventListener('touchstart', onStart, {passive: false});
  window.addEventListener('mousemove', onMove);
  window.addEventListener('touchmove', onMove, {passive: false});
  window.addEventListener('mouseup', onEnd);
  window.addEventListener('touchend', onEnd);
})();

// ---- Assistant IA ----------------------------------------------------------
const modalIa = $('modal-ia');
$('btn-ia').onclick = () => {
  modalIa.style.display = 'flex';
  updatePrompt();
};
$('close-modal').onclick = () => modalIa.style.display = 'none';
window.addEventListener('click', e => { if (e.target === modalIa) modalIa.style.display = 'none'; });

function updatePrompt() {
  const jobDesc = $('ia-job-desc').value.trim();
  const tplName = $('ia-template').value;
  const wantLetter = $('ia-cover-letter').checked;
  const tpl = TEMPLATES[tplName] || TEMPLATES['sobre'];

  let prompt = `Agis en tant qu'expert en recrutement. Je te fournis en pièce jointe mon CV actuel.

Voici l'offre d'emploi à laquelle je postule :
---
${jobDesc || "[Collez votre offre d'emploi ici ou décrivez le poste visé]"}
---

Ton objectif est de rédiger mon nouveau CV${wantLetter ? ' ET MA LETTRE DE MOTIVATION' : ''} optimisé(s) pour ce poste, en utilisant STRICTEMENT la structure HTML fournie ci-dessous.

Règles :
1. Fais d'abord une brève analyse des mots-clés de l'offre et de mon profil.
2. Remplis les balises HTML avec mes informations. Sois concis pour que le CV tienne sur 1 page A4.
3. Ne modifie AUCUNE classe CSS, ne touche pas à la structure.
4. Pour la photo de profil, laisse exactement le tag suivant sans le modifier : src="URL_DE_VOTRE_PHOTO_ICI".
5. Rends UNIQUEMENT le(s) bloc(s) de code HTML final, prêt(s) à être copié(s).

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
    const oldText = btn.textContent;
    const oldBg = btn.style.background;
    btn.textContent = '✅ Copié ! Collez-le dans ChatGPT/Claude';
    btn.style.background = '#5dd39e';
    setTimeout(() => {
      btn.textContent = oldText;
      btn.style.background = oldBg;
    }, 3000);
  });
};

// ---- Insertion Photo Base64 ------------------------------------------------
$('btn-photo').onclick = () => {
  if (htmlModel && !htmlModel.getValue().includes('URL_DE_VOTRE_PHOTO_ICI')) {
    alert("ℹ️ Aucun emplacement automatique de photo détecté.\n\nVotre photo sera insérée exactement là où se trouve actuellement votre curseur clignotant dans le code HTML.\n\nAssurez-vous d'avoir cliqué au bon endroit dans l'éditeur avant de choisir votre image !");
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
    const photoCode = `\n<!-- #region Photo_Base64 -->\n<img src="${base64}" alt="Photo de profil" style="width:80px; border-radius:4px;"/>\n<!-- #endregion -->\n`;

    if (currentHtml.includes('URL_DE_VOTRE_PHOTO_ICI')) {
      let newHtml = currentHtml;
      if (currentHtml.includes('src="URL_DE_VOTRE_PHOTO_ICI"')) {
        newHtml = currentHtml.replace('URL_DE_VOTRE_PHOTO_ICI', base64);
      } else {
        newHtml = currentHtml.replace('<!-- URL_DE_VOTRE_PHOTO_ICI -->', photoCode.trim()).replace('URL_DE_VOTRE_PHOTO_ICI', photoCode.trim());
      }
      htmlModel.setValue(newHtml);
      setStatus('Photo insérée avec succès dans le CV !', 'ok');
    } else {
      insertSnippet(photoCode);
      setStatus('Photo insérée là où se trouvait votre curseur.', 'ok');
    }
    
    // Replier le code Base64 pour ne pas polluer l'éditeur visuellement
    setTimeout(() => {
      if (editor) {
        editor.trigger('fold', 'editor.foldAllMarkerRegions');
      }
    }, 100);
  };
  reader.readAsDataURL(file);
  e.target.value = '';
};
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# PAGE HISTORIQUE
# Utilise Jinja2 pour injecter IS_SERVERLESS côté serveur.
# ---------------------------------------------------------------------------
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
  .error { color: #ff6b6b; padding: 24px; text-align: center; }
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
// Injecté par Flask — true sur Vercel (serverless), false en local
const IS_SERVERLESS = {{ is_serverless | tojson }};
const HISTORY_KEY   = 'cv-history';
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
    if (k === 'class')   node.className = v;
    else if (k === 'onclick') node.onclick = v;
    else if (k === 'text')    node.textContent = v;
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
  // Préférer les URLs Blob permanentes si disponibles
  const pdfHref    = e.pdf_url  || e.pdf_blob_url  || ('/api/history/' + encodeURIComponent(id) + '/pdf');
  const reloadBase = '/?load=' + encodeURIComponent(id);
  const htmlSrc    = e.html_url || e.html_blob_url  || '';
  const reloadHref = htmlSrc
    ? (reloadBase + '&htmlUrl=' + encodeURIComponent(htmlSrc))
    : reloadBase;

  const actions = [
    el('a',      { class: 'btn',         href: pdfHref,    target: '_blank', text: 'Voir PDF' }),
    el('a',      { class: 'btn',         href: reloadHref,                   text: 'Recharger' }),
    !IS_SERVERLESS
      ? el('button', { class: 'ghost', onclick: function() { openLocal(id); }, text: 'Ouvrir local' })
      : null,
    el('button', { class: 'ghost danger', onclick: function() { del(id); },  text: 'Supprimer' }),
  ].filter(Boolean);

  return el('tr', { 'data-id': id }, [
    el('td', { text: fmtDate(e.created_at) }),
    el('td', {}, [el('span', { class: 'badge', text: e.doc_type || '' })]),
    el('td', { text: e.company || '-' }),
    el('td', { text: e.role    || '-' }),
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

function showError(msg) {
  const root = $('root');
  root.replaceChildren();
  root.appendChild(el('div', { class: 'error', text: msg }));
}

async function load() {
  // 1. Priorité : localStorage (Vercel Blob — persistant)
  try {
    const raw    = localStorage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    // Utiliser localStorage si : entrées présentes OU mode serverless
    // (sur Vercel, l'API /api/history ne persiste pas entre les cold starts)
    if (parsed !== null && (parsed.length > 0 || IS_SERVERLESS)) {
      entries = parsed;
      render($('search').value);
      return;
    }
  } catch (_) {}

  // 2. Fallback : API serveur (local dev avec archive persistante)
  try {
    const r = await fetch('/api/history');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    entries = await r.json();
    render($('search').value);
  } catch (err) {
    showError('Impossible de charger l\'historique : ' + err.message);
  }
}

async function del(id) {
  if (!confirm('Supprimer cette entree ?')) return;

  // Supprimer du localStorage
  try {
    const raw  = localStorage.getItem(HISTORY_KEY);
    if (raw) {
      const hist = JSON.parse(raw).filter(function(e) { return e.id !== id; });
      localStorage.setItem(HISTORY_KEY, JSON.stringify(hist));
    }
  } catch (_) {}

  // Supprimer côté serveur (best-effort — ignore les erreurs réseau / 404)
  try {
    await fetch('/api/history/' + encodeURIComponent(id), { method: 'DELETE' });
  } catch (_) {}

  // Recharger la liste depuis la source mise à jour
  await load();
}

async function openLocal(id) {
  try {
    const r = await fetch('/api/history/' + encodeURIComponent(id) + '/open', { method: 'POST' });
    if (!r.ok) {
      const body = await r.json().catch(function() { return {}; });
      alert('Impossible d\'ouvrir le fichier : ' + (body.error || r.status));
    }
  } catch (err) {
    alert('Erreur reseau : ' + err.message);
  }
}

$('search').addEventListener('input', function(e) { render(e.target.value); });
load();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Application Flask
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.route("/")
def index():
    # PAGE est un raw string sans expression Jinja2 — retourné directement
    # pour éviter tout risque d'interprétation accidentelle.
    return Response(PAGE, mimetype="text/html")


@app.route("/history")
def history_page():
    return render_template_string(HISTORY_PAGE, is_serverless=archive._IS_SERVERLESS)


@app.route("/convert", methods=["POST"])
def convert():
    # Limite de taille du corps de requête
    if request.content_length and request.content_length > MAX_HTML_BYTES:
        return jsonify({"error": f"Corps de requête trop grand (max {MAX_HTML_BYTES // 1024} Ko)."}), 413

    data = request.get_json(silent=True) or {}
    html = data.get("html", "")
    if not html.strip():
        return jsonify({"error": "HTML vide."}), 400
    if len(html.encode()) > MAX_HTML_BYTES:
        return jsonify({"error": "HTML trop grand."}), 413

    # Validation des options contre les valeurs autorisées
    fmt    = data.get("format", "A4")
    margin = data.get("margin", "0")
    if fmt not in VALID_FORMATS:
        return jsonify({"error": f"Format invalide : {fmt!r}"}), 400
    if margin not in VALID_MARGINS:
        return jsonify({"error": f"Marge invalide : {margin!r}"}), 400

    background     = bool(data.get("background", True))
    doc_type       = data.get("doc_type", "CV")
    company        = (data.get("company") or "").strip()
    role           = (data.get("role") or "").strip()
    notes          = (data.get("notes") or "").strip()
    job_desc       = (data.get("job_desc") or "").strip()
    custom_filename = (data.get("filename") or "").strip()

    try:
        pdf_bytes = html_to_pdf_bytes(html, page_format=fmt, margin=margin, background=background)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Erreur de rendu PDF : {e}"}), 500

    # Archivage (best-effort : le PDF est retourné même si l'archive échoue)
    entry: dict
    try:
        entry = archive.save_document(
            html=html,
            pdf_bytes=pdf_bytes,
            doc_type=doc_type,
            company=company,
            role=role,
            notes=notes,
            custom_filename=custom_filename,
            job_desc=job_desc,
        )
    except Exception as e:
        # Archivage impossible (disque plein, permissions…) — on retourne quand même le PDF
        import uuid as _uuid
        from datetime import datetime as _dt
        entry = {
            "id": str(_uuid.uuid4()),
            "filename": custom_filename or f"document_{_dt.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            "created_at": _dt.now().isoformat(timespec="seconds"),
        }

    # Upload Vercel Blob (optionnel — dégradation gracieuse)
    pdf_blob_url  = ""
    html_blob_url = ""
    if archive._BLOB_TOKEN:
        try:
            pdf_blob_url  = archive.upload_to_blob(pdf_bytes, entry["filename"], "application/pdf")
            html_filename = Path(entry["filename"]).stem + ".html"
            html_blob_url = archive.upload_to_blob(
                html.encode("utf-8"), html_filename, "text/html"
            )
            # Mettre à jour history.json avec les URLs Blob
            try:
                archive.update_document_blob_urls(entry["id"], pdf_blob_url, html_blob_url)
            except Exception:
                pass
        except Exception:
            pass  # Upload Blob non bloquant

    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=entry["filename"],
    )
    response.headers["X-Archive-Entry"] = _json.dumps({
        "id":         entry.get("id", ""),
        "filename":   entry.get("filename", "document.pdf"),
        "created_at": entry.get("created_at", ""),
    })
    response.headers["X-Blob-PDF-URL"]  = pdf_blob_url
    response.headers["X-Blob-HTML-URL"] = html_blob_url
    response.headers["Access-Control-Expose-Headers"] = (
        "X-Archive-Entry, X-Blob-PDF-URL, X-Blob-HTML-URL"
    )
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
    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=entry["filename"],
    )


@app.route("/api/history/<doc_id>/open", methods=["POST"])
def api_history_open(doc_id):
    # Uniquement disponible en mode local (pas serverless)
    if archive._IS_SERVERLESS:
        return jsonify({"error": "Non disponible en mode serverless."}), 400
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


# ---------------------------------------------------------------------------
# Lanceur local (desktop)
# ---------------------------------------------------------------------------

def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 10.0) -> None:
    """Attend que le serveur Flask accepte des connexions sur le port donné."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)


def lancer_serveur() -> None:
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


def lancer_navigateur() -> None:
    _wait_for_port(PORT)
    webbrowser.open(URL)


def fenetre_controle() -> None:
    if not _HAS_TKINTER:
        print(f"Serveur disponible sur {URL}  (Ctrl-C pour quitter)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            sys.exit(0)
        return

    root = tk.Tk()
    root.title("Convertisseur HTML -> PDF")
    root.resizable(False, False)
    largeur, hauteur = 360, 160
    x = (root.winfo_screenwidth()  - largeur) // 2
    y = (root.winfo_screenheight() - hauteur) // 2
    root.geometry(f"{largeur}x{hauteur}+{x}+{y}")

    tk.Label(root, text="Le serveur tourne sur :", pady=8).pack()
    lien = tk.Label(
        root, text=URL, fg="#1a73e8", cursor="hand2",
        font=("Segoe UI", 10, "underline"),
    )
    lien.pack()
    lien.bind("<Button-1>", lambda _e: webbrowser.open(URL))
    tk.Label(root, text="Fermez cette fenetre pour arreter.", fg="#666", pady=8).pack()

    def quitter() -> None:
        root.destroy()
        sys.exit(0)

    tk.Button(root, text="Quitter", width=14, command=quitter).pack(pady=6)
    root.protocol("WM_DELETE_WINDOW", quitter)
    root.mainloop()


def main() -> None:
    archive.ensure_archive_dir()
    threading.Thread(target=lancer_serveur,    daemon=True).start()
    threading.Thread(target=lancer_navigateur, daemon=True).start()
    fenetre_controle()


if __name__ == "__main__":
    main()
