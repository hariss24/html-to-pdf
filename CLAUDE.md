# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Install (Python 3.10+):
```bash
pip install -r requirements.txt
python -m playwright install chromium   # required, ~250 MB Chromium binary
```

Run the web UI (opens browser on http://127.0.0.1:5050 + a tkinter control window):
```bash
python app.py
```

Run the MCP server standalone (it speaks stdio JSON-RPC, useful for debugging — Claude desktop spawns it on its own):
```bash
python mcp_server.py
```

Quick syntax check across all Python modules:
```bash
python -m py_compile app.py mcp_server.py archive.py pdf_engine.py
```

There is no test suite. When validating changes, write a temporary `test_*.py` script that exercises the relevant entry point (Flask via `urllib.request` against `http://127.0.0.1:5050`, MCP via `subprocess.Popen` + JSON-RPC over stdin/stdout), run it, then delete it.

## Architecture

Two independent frontends share a single rendering and archival backend:

```
Browser ──HTTP──▶ app.py (Flask + tkinter)        ┐
                                                   ├──▶ pdf_engine.html_to_pdf_bytes()  (sync Playwright)
Claude desktop ──stdio MCP──▶ mcp_server.py       ┘   ──▶ archive.save_document()       (filesystem + history.json)
```

`pdf_engine.py` is the **only** place that talks to Playwright. It exposes one sync function `html_to_pdf_bytes(html, page_format, margin, background) -> bytes`. Anything that needs PDF rendering must go through it — do not call `sync_playwright` elsewhere.

`archive.py` is the **only** place that writes to disk under `~/Documents/CV-Archive/`. It owns the `history.json` schema (id, created_at, doc_type, company, role, notes, filename, pdf_path, html_path) and the smart filename pattern `{doc_type}_Hariss_{company}_{YYYY-MM-DD}.pdf`. Writes are atomic (`.json.tmp` + rename) so the web UI and the MCP server can both write concurrently without corruption.

`app.py` is a single Flask file. The two HTML pages (`PAGE`, `HISTORY_PAGE`) are inline triple-quoted strings — there is no `templates/` directory. The main page uses Monaco editor (loaded from a CDN, no build step) on the left and a sandboxed `<iframe srcdoc>` preview on the right; both stay in sync via a 400 ms debounce. The Flask server runs in a daemon thread while a tkinter "Quitter" window owns the main thread.

`mcp_server.py` uses `FastMCP` and exposes `convert_html_to_pdf`, `list_recent_documents`, `get_archive_dir`. Tool functions are `async` and wrap the sync Playwright call with `await asyncio.to_thread(html_to_pdf_bytes, ...)` — calling sync Playwright directly inside the asyncio loop raises "use the Async API instead". Logs must go to stderr (`print(..., file=sys.stderr)`); stdout is reserved for the MCP protocol.

## Conventions and gotchas

- `PAGE` in `app.py` is a **raw string** (`r"""..."""`) because the inline JS contains regex literals with `\w` and `\s` — without `r`, Python 3.12+ emits `SyntaxWarning`.
- The web UI's `/convert` endpoint always archives. Don't add a "skip archive" flag — the archive is the single source of truth used by `/history` and the MCP `list_recent_documents` tool.
- The `X-Archive-Entry` response header on `/convert` carries the new entry's `{id, filename, created_at}` so the browser can name the download properly.
- `OWNER = "Hariss"` in `archive.py` is hardcoded into filenames. Change it there if reusing the project for someone else.
- `app.py` calls `os.startfile()` and `subprocess.run(["explorer", "/select,", ...])` — Windows-only. They will silently fail or be skipped on other platforms.
- Local launcher `C:\Users\tahet\cv_pdf_web.pyw` (outside this repo) is a thin wrapper that prepends this directory to `sys.path`, `chdir`s into it, and calls `app.main()`. Double-clicking it on Windows uses `pythonw.exe` and avoids the console window.

## MCP integration

Claude desktop config lives at `%APPDATA%\Claude\claude_desktop_config.json` (Windows). The `mcpServers.html-to-pdf` entry already points to `mcp_server.py`. After any change to `mcp_server.py`, restart Claude desktop fully (not just close window) to pick it up.
