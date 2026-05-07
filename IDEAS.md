# UX improvement ideas for html-to-pdf

Brainstorm dump for future iterations. Goal: very user-friendly tool for the
Claude desktop → HTML → PDF workflow.

## A. Saisie flexible

1. **Champ CSS séparé** *(idée user)* — onglets `HTML / CSS` dans Monaco. Si CSS rempli, injecté en `<style>` à la conversion. Permet à Claude de générer juste le body et de garder un CSS perso.
2. **Presets de thème CSS** — boutons "Moderne / Classique / Élégant / Minimal" qui chargent une feuille CSS prête. Switch de look en un clic.
3. **Mode "body-only"** auto-détecté — si on colle juste `<body>...</body>`, l'app wrappe avec template HTML + CSS courant.

## B. Vitesse et feedback

4. **Onglet preview HTML | PDF** — second onglet dans le panneau droit affichant le PDF généré (PDF.js). Plus fidèle que la preview HTML.
5. **Page-break visuel** — lignes pointillées sur la preview à chaque saut de page A4.
6. **Compteur live** — "≈ 2 pages, 1.4 MB" calculé pendant l'édition.
7. **Toggle "@media print"** sur la preview pour simuler le rendu PDF sans cliquer Convertir.

## C. Intégration Claude (workflow)

8. **"Coller depuis presse-papier"** — bouton qui remplit l'éditeur instantanément.
9. **"Copier prompt Claude"** — génère un prompt depuis les métadonnées (`Génère-moi un CV pour {role} chez {company}…`) et le copie.
10. **Drag & drop d'un .html / .md** dans l'éditeur pour le charger.

## D. Productivité quotidienne

11. **Raccourcis clavier** — `Ctrl+Enter` = convertir, `Ctrl+S` = save draft explicite, `Ctrl+P` = toggle preview.
12. **Sidebar "Récents"** dans l'éditeur — 5 derniers documents accessibles sans quitter l'écran principal.
13. **Toast notifications** au lieu du `#status` discret.
14. **Bouton "Ouvrir dossier d'archive"** dans le header.

## E. Qualité de rendu

15. **Linter CSS print** — avertit si pas de `@page`, polices non déclarées, image trop grande.
16. **Avertissement "backgrounds"** — si CSS utilise `background-color` mais la case "include backgrounds" est décochée.

## F. Polish

17. **Empty state** — premier lancement charge un template CV exemple + tutoriel court.
18. **Light/Dark toggle** sur l'UI.

---

## Top 5 picks (proposés à implémenter en premier)

| # | Feature | Effort | Impact |
|---|---------|--------|--------|
| 1 | Champ CSS séparé + presets de thème (A1+A2) | Moyen | 🔥🔥🔥 |
| 2 | Raccourcis clavier (Ctrl+Enter) + toast (D11+D13) | Faible | 🔥🔥 |
| 3 | Onglet preview PDF (PDF.js) + page-breaks visuels (B4+B5) | Moyen | 🔥🔥🔥 |
| 4 | "Copier prompt Claude" + drag&drop fichier (C9+C10) | Faible | 🔥🔥 |
| 5 | Sidebar récents dans l'éditeur (D12) | Faible | 🔥 |

Décision en attente de l'utilisateur : valider ce top 5 ou repiocher.
