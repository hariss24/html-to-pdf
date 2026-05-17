"""Tests pour pdf_engine.py."""
import os
import pytest
from unittest.mock import patch, MagicMock


# ---- Imports conditionnels --------------------------------------------------

import pdf_engine


# ---- Validation des paramètres ----------------------------------------------

def test_invalid_format_raises():
    with pytest.raises(ValueError, match="Format non supporté"):
        pdf_engine.html_to_pdf_bytes("<html></html>", page_format="A0")


def test_invalid_margin_raises():
    with pytest.raises(ValueError, match="Marge non supportée"):
        pdf_engine.html_to_pdf_bytes("<html></html>", margin="3px")


def test_valid_formats_accepted():
    """Tous les formats de la whitelist ne lèvent pas de ValueError."""
    for fmt in pdf_engine.VALID_FORMATS:
        with patch.object(pdf_engine, "_playwright_render", return_value=b"%PDF"):
            with patch.object(pdf_engine, "_want_weasyprint", False):
                with patch.object(pdf_engine, "_PLAYWRIGHT_AVAILABLE", True):
                    result = pdf_engine.html_to_pdf_bytes("<html></html>", page_format=fmt)
                    assert result == b"%PDF"


def test_valid_margins_accepted():
    """Toutes les marges de la whitelist ne lèvent pas de ValueError."""
    for margin in pdf_engine.VALID_MARGINS:
        with patch.object(pdf_engine, "_playwright_render", return_value=b"%PDF"):
            with patch.object(pdf_engine, "_want_weasyprint", False):
                with patch.object(pdf_engine, "_PLAYWRIGHT_AVAILABLE", True):
                    result = pdf_engine.html_to_pdf_bytes("<html></html>", margin=margin)
                    assert result == b"%PDF"


# ---- Sélection du backend ---------------------------------------------------

def test_uses_weasyprint_when_env_set():
    with patch.object(pdf_engine, "_want_weasyprint", True):
        with patch.object(pdf_engine, "_weasyprint_render", return_value=b"WP") as mock_wp:
            result = pdf_engine.html_to_pdf_bytes("<html></html>")
            mock_wp.assert_called_once()
            assert result == b"WP"


def test_uses_weasyprint_when_playwright_unavailable():
    with patch.object(pdf_engine, "_want_weasyprint", False):
        with patch.object(pdf_engine, "_PLAYWRIGHT_AVAILABLE", False):
            with patch.object(pdf_engine, "_weasyprint_render", return_value=b"WP") as mock_wp:
                result = pdf_engine.html_to_pdf_bytes("<html></html>")
                mock_wp.assert_called_once()
                assert result == b"WP"


def test_uses_playwright_by_default():
    with patch.object(pdf_engine, "_want_weasyprint", False):
        with patch.object(pdf_engine, "_PLAYWRIGHT_AVAILABLE", True):
            with patch.object(pdf_engine, "_playwright_render", return_value=b"PW") as mock_pw:
                result = pdf_engine.html_to_pdf_bytes("<html></html>")
                mock_pw.assert_called_once()
                assert result == b"PW"


# ---- Whitelist constants ----------------------------------------------------

def test_valid_formats_whitelist():
    assert "A4" in pdf_engine.VALID_FORMATS
    assert "Letter" in pdf_engine.VALID_FORMATS
    assert "A0" not in pdf_engine.VALID_FORMATS


def test_valid_margins_whitelist():
    assert "0" in pdf_engine.VALID_MARGINS
    assert "10mm" in pdf_engine.VALID_MARGINS
    assert "3px" not in pdf_engine.VALID_MARGINS
    assert "50mm" not in pdf_engine.VALID_MARGINS


# ---- Playwright render (mock) -----------------------------------------------

def test_playwright_render_passes_format_and_margin():
    """Vérifie que _playwright_render transmet les bons paramètres à page.pdf()."""
    mock_page = MagicMock()
    mock_page.pdf.return_value = b"%PDF-playwright"
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_sync_playwright = MagicMock()
    mock_sync_playwright.return_value.__enter__ = MagicMock(return_value=mock_p)
    mock_sync_playwright.return_value.__exit__ = MagicMock(return_value=False)

    mock_pw_module = MagicMock()
    mock_pw_module.sync_playwright = mock_sync_playwright

    with patch.dict("sys.modules", {
        "playwright": MagicMock(),
        "playwright.sync_api": mock_pw_module,
    }):
        result = pdf_engine._playwright_render("<html></html>", "A4", "10mm", True)

    mock_page.pdf.assert_called_once()
    call_kwargs = mock_page.pdf.call_args.kwargs
    assert call_kwargs["format"] == "A4"
    assert call_kwargs["print_background"] is True
    assert call_kwargs["margin"]["top"] == "10mm"


# ---- WeasyPrint render (mock) -----------------------------------------------

def test_weasyprint_render_zero_margin_no_stylesheet():
    """Avec margin='0', aucune feuille de style supplémentaire ne doit être injectée."""
    mock_html_instance = MagicMock()
    mock_html_instance.write_pdf.return_value = b"%PDF-weasyprint"

    mock_html_class = MagicMock(return_value=mock_html_instance)

    with patch.dict("sys.modules", {"weasyprint": MagicMock(HTML=mock_html_class, CSS=MagicMock())}):
        result = pdf_engine._weasyprint_render("<html></html>", "A4", "0")

    mock_html_instance.write_pdf.assert_called_once_with(stylesheets=None)
    assert result == b"%PDF-weasyprint"


def test_weasyprint_render_margin_injects_stylesheet():
    """Avec une marge non nulle, une feuille de style @page doit être injectée."""
    mock_css_instance = MagicMock()
    mock_html_instance = MagicMock()
    mock_html_instance.write_pdf.return_value = b"%PDF-weasyprint"

    mock_weasyprint = MagicMock()
    mock_weasyprint.HTML.return_value   = mock_html_instance
    mock_weasyprint.CSS.return_value    = mock_css_instance

    with patch.dict("sys.modules", {"weasyprint": mock_weasyprint}):
        pdf_engine._weasyprint_render("<html></html>", "A4", "15mm")

    mock_weasyprint.CSS.assert_called_once()
    css_string_arg = mock_weasyprint.CSS.call_args.kwargs.get("string", "")
    assert "15mm" in css_string_arg
    assert "@page" in css_string_arg

    call_kwargs = mock_html_instance.write_pdf.call_args.kwargs
    assert call_kwargs.get("stylesheets") is not None
