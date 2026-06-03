"""
Test suite per redact_pdf.py.

Copre:
  - mark_to_rects (funzione pura, nessun PDF)
  - apply_secure_redactions (su PDF creati in memoria)
  - process_pdf su vector.pdf (testo nativo)
  - process_pdf su scan.pdf (PDF scansionato / immagini)
  - casi limite: file inesistente, non-PDF, nessuna annotazione, rettangolo vuoto
"""

import os
import sys
import shutil
import tempfile

import fitz
import pytest

# Aggiungi la root del progetto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import redact_pdf as rp

RESOURCES = os.path.join(os.path.dirname(__file__), "resources")
VECTOR_PDF = os.path.join(RESOURCES, "vector.pdf")
SCAN_PDF   = os.path.join(RESOURCES, "scan.pdf")


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_dir(tmp_path):
    """Directory temporanea pulita per ogni test."""
    return tmp_path


def _copy_pdf(src: str, dest_dir) -> str:
    """Copia un PDF in dest_dir e restituisce il percorso della copia."""
    dst = os.path.join(dest_dir, os.path.basename(src))
    shutil.copy2(src, dst)
    return dst


def _add_square_annot(pdf_path: str, page_index: int, rect: fitz.Rect,
                      fill=(0, 0, 0)) -> None:
    """Aggiunge un'annotazione Square a un PDF esistente (in-place)."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    annot = page.add_rect_annot(rect)
    annot.set_colors(fill=fill, stroke=fill)
    annot.update()
    tmp = pdf_path + ".tmp"
    doc.save(tmp)
    doc.close()
    os.replace(tmp, pdf_path)


def _output_path(pdf_path: str) -> str:
    base, ext = os.path.splitext(pdf_path)
    return f"{base}{rp.OUTPUT_SUFFIX}{ext}"


# ─── mark_to_rects ────────────────────────────────────────────────────────────

class TestMarkToRects:
    def test_rect_mark(self):
        r = fitz.Rect(10, 20, 100, 50)
        mark = {"type": "rect", "rect": r}
        result = rp.mark_to_rects(mark)
        assert result == [r]

    def test_text_mark(self):
        rects = [fitz.Rect(0, 0, 50, 10), fitz.Rect(0, 12, 80, 22)]
        mark = {"type": "text", "rects": rects}
        result = rp.mark_to_rects(mark)
        assert result == rects

    def test_free_single_point(self):
        mark = {"type": "free", "points": [(50, 50)], "half": 5}
        result = rp.mark_to_rects(mark)
        assert len(result) == 1
        r = result[0]
        assert r.x0 == pytest.approx(45)
        assert r.y0 == pytest.approx(45)
        assert r.x1 == pytest.approx(55)
        assert r.y1 == pytest.approx(55)

    def test_free_two_points(self):
        mark = {"type": "free", "points": [(10, 10), (30, 30)], "half": 3}
        result = rp.mark_to_rects(mark)
        assert len(result) == 1
        r = result[0]
        assert r.x0 == pytest.approx(7)
        assert r.y0 == pytest.approx(7)
        assert r.x1 == pytest.approx(33)
        assert r.y1 == pytest.approx(33)

    def test_free_three_points_produces_two_rects(self):
        mark = {"type": "free", "points": [(0, 0), (10, 0), (20, 0)], "half": 2}
        result = rp.mark_to_rects(mark)
        assert len(result) == 2

    def test_unknown_type_returns_empty(self):
        mark = {"type": "unknown"}
        assert rp.mark_to_rects(mark) == []


# ─── apply_secure_redactions ──────────────────────────────────────────────────

class TestApplySecureRedactions:
    def _make_text_pdf(self) -> fitz.Document:
        """Crea un documento in memoria con del testo noto."""
        doc = fitz.open()
        page = doc.new_page(width=200, height=100)
        page.insert_text((10, 50), "hello world", fontsize=12)
        return doc

    def test_empty_list_returns_zero(self):
        doc = self._make_text_pdf()
        applied = rp.apply_secure_redactions(doc[0], [])
        assert applied == 0

    def test_covers_text(self):
        doc = self._make_text_pdf()
        page = doc[0]
        # Testo "hello world" attorno a y≈50; copri tutta la pagina per sicurezza
        rect = fitz.Rect(0, 0, 200, 100)
        applied = rp.apply_secure_redactions(page, [(rect, (0, 0, 0))])
        assert applied == 1
        text_after = page.get_text().strip()
        assert text_after == ""

    def test_empty_rect_skipped(self):
        doc = self._make_text_pdf()
        empty = fitz.Rect(50, 50, 50, 50)   # larghezza = 0
        applied = rp.apply_secure_redactions(doc[0], [(empty, (0, 0, 0))])
        assert applied == 0

    def test_out_of_page_rect_skipped(self):
        doc = self._make_text_pdf()
        outside = fitz.Rect(300, 300, 500, 500)
        applied = rp.apply_secure_redactions(doc[0], [(outside, (0, 0, 0))])
        assert applied == 0

    def test_multiple_rects(self):
        doc = self._make_text_pdf()
        page = doc[0]
        r1 = fitz.Rect(0, 0, 50, 100)
        r2 = fitz.Rect(50, 0, 200, 100)
        applied = rp.apply_secure_redactions(page, [(r1, (1, 1, 1)), (r2, (0, 0, 0))])
        assert applied == 2


# ─── process_pdf: casi limite ─────────────────────────────────────────────────

class TestProcessPdfEdgeCases:
    def test_file_not_found(self, tmp_dir):
        ok, out, msg = rp.process_pdf("/nonexistent/path.pdf", os.devnull)
        assert not ok
        assert out is None
        assert "non trovato" in msg.lower()

    def test_non_pdf_extension(self, tmp_dir):
        txt = os.path.join(tmp_dir, "file.txt")
        open(txt, "w").close()
        ok, out, msg = rp.process_pdf(txt, os.devnull)
        assert not ok

    def test_no_annotations_produces_output(self, tmp_dir):
        """Un PDF senza annotazioni deve essere copiato e segnalato correttamente."""
        src = _copy_pdf(VECTOR_PDF, tmp_dir)
        ok, out, msg = rp.process_pdf(src, os.devnull)
        assert ok
        assert out and os.path.isfile(out)
        assert "nessuna" in msg.lower()


# ─── process_pdf: PDF vettoriale (testo nativo) ───────────────────────────────

class TestProcessPdfVector:
    """
    Verifica che dopo la redazione il testo coperto non sia più estraibile.
    Usa vector.pdf (5 pagine, testo nativo).
    """

    # "Introduction" appare una sola volta su pagina 1 (0-indexed)
    # bbox esatta: (59.5, 130.2, 202.3, 161.5) → rettangolo con margine
    TARGET_WORD  = "Introduction"
    TARGET_PAGE  = 1
    TARGET_RECT  = fitz.Rect(55, 126, 210, 166)

    def test_redacted_text_removed(self, tmp_dir):
        src = _copy_pdf(VECTOR_PDF, tmp_dir)
        _add_square_annot(src, self.TARGET_PAGE, self.TARGET_RECT)

        ok, out, msg = rp.process_pdf(src, os.devnull)
        assert ok, f"process_pdf ha fallito: {msg}"
        assert out and os.path.isfile(out)

        doc = fitz.open(out)
        page = doc[self.TARGET_PAGE]
        words = [w[4] for w in page.get_text("words")]
        doc.close()

        assert self.TARGET_WORD not in words, (
            f"'{self.TARGET_WORD}' ancora presente dopo la redazione"
        )

    def test_text_outside_rect_preserved(self, tmp_dir):
        """Le parole fuori dal riquadro devono sopravvivere."""
        src = _copy_pdf(VECTOR_PDF, tmp_dir)
        _add_square_annot(src, self.TARGET_PAGE, self.TARGET_RECT)

        ok, out, _ = rp.process_pdf(src, os.devnull)
        assert ok

        doc = fitz.open(out)
        page = doc[self.TARGET_PAGE]
        words = [w[4] for w in page.get_text("words")]
        doc.close()

        assert "Sample" in words, "Parole fuori dalla redazione scomparse"

    def test_other_pages_untouched(self, tmp_dir):
        """Le pagine senza annotazioni devono mantenere il loro testo."""
        src = _copy_pdf(VECTOR_PDF, tmp_dir)
        _add_square_annot(src, self.TARGET_PAGE, self.TARGET_RECT)

        ok, out, _ = rp.process_pdf(src, os.devnull)
        assert ok

        doc_orig = fitz.open(VECTOR_PDF)
        doc_out  = fitz.open(out)

        for pg in range(len(doc_orig)):
            if pg == self.TARGET_PAGE:
                continue
            orig_words = {w[4] for w in doc_orig[pg].get_text("words")}
            out_words  = {w[4] for w in doc_out[pg].get_text("words")}
            assert orig_words == out_words, f"Pagina {pg} ha perso del testo"

        doc_orig.close()
        doc_out.close()

    def test_no_residual_annotations(self, tmp_dir):
        """Nel PDF di output non devono rimanere annotazioni di tipo Square."""
        src = _copy_pdf(VECTOR_PDF, tmp_dir)
        _add_square_annot(src, self.TARGET_PAGE, self.TARGET_RECT)

        ok, out, _ = rp.process_pdf(src, os.devnull)
        assert ok

        doc = fitz.open(out)
        for pg in doc:
            annots = list(pg.annots())
            square_annots = [a for a in annots if a.type[0] == fitz.PDF_ANNOT_SQUARE]
            assert square_annots == [], f"Annotazione Square residua a pagina {pg.number}"
        doc.close()

    def test_output_page_count_unchanged(self, tmp_dir):
        src = _copy_pdf(VECTOR_PDF, tmp_dir)
        _add_square_annot(src, self.TARGET_PAGE, self.TARGET_RECT)

        ok, out, _ = rp.process_pdf(src, os.devnull)
        assert ok

        doc_orig = fitz.open(VECTOR_PDF)
        doc_out  = fitz.open(out)
        assert len(doc_out) == len(doc_orig)
        doc_orig.close()
        doc_out.close()


# ─── process_pdf: PDF scansionato (immagini) ──────────────────────────────────

class TestProcessPdfScan:
    """
    Verifica la redazione su scan.pdf (8 pagine, ogni pagina è un'immagine).
    Controlla che i pixel sotto il riquadro cambino colore e che il resto
    dell'immagine rimanga intatto (IMAGE_PIXELS vs IMAGE_REMOVE).
    """

    TARGET_PAGE = 0
    # Riquadro che copre area con contenuto scuro (pixel ~41 a (120,120))
    TARGET_RECT = fitz.Rect(100, 100, 200, 200)

    def _render_page(self, pdf_path: str, page_index: int) -> fitz.Pixmap:
        doc = fitz.open(pdf_path)
        pix = doc[page_index].get_pixmap()
        doc.close()
        return pix

    def test_process_succeeds(self, tmp_dir):
        src = _copy_pdf(SCAN_PDF, tmp_dir)
        _add_square_annot(src, self.TARGET_PAGE, self.TARGET_RECT)

        ok, out, msg = rp.process_pdf(src, os.devnull)
        assert ok, f"process_pdf ha fallito: {msg}"
        assert out and os.path.isfile(out)

    def test_redacted_pixels_changed(self, tmp_dir):
        """I pixel sotto il riquadro devono diventare neri (fill nero) rispetto all'originale."""
        # pix_before dal PDF originale senza annotazione
        pix_before = self._render_page(SCAN_PDF, self.TARGET_PAGE)

        src = _copy_pdf(SCAN_PDF, tmp_dir)
        _add_square_annot(src, self.TARGET_PAGE, self.TARGET_RECT)
        ok, out, _ = rp.process_pdf(src, os.devnull)
        assert ok

        pix_after = self._render_page(out, self.TARGET_PAGE)

        # Centro del riquadro di redazione
        cx = int((self.TARGET_RECT.x0 + self.TARGET_RECT.x1) / 2)
        cy = int((self.TARGET_RECT.y0 + self.TARGET_RECT.y1) / 2)
        before_pixel = pix_before.pixel(cx, cy)
        after_pixel  = pix_after.pixel(cx, cy)

        # Dopo la redazione i pixel devono essere neri (fill default = nero)
        assert all(c == 0 for c in after_pixel[:3]), (
            f"I pixel al centro della redazione non sono diventati neri: {after_pixel}"
        )
        # E devono essere diversi dall'originale (che non era già tutto nero)
        assert before_pixel != after_pixel, (
            f"I pixel non sono cambiati (erano già {before_pixel}?)"
        )

    def test_image_not_fully_erased(self, tmp_dir):
        """Con IMAGE_PIXELS solo la zona coperta viene cancellata; l'immagine rimane."""
        src = _copy_pdf(SCAN_PDF, tmp_dir)
        _add_square_annot(src, self.TARGET_PAGE, self.TARGET_RECT)

        ok, out, _ = rp.process_pdf(src, os.devnull)
        assert ok

        # L'immagine di pagina deve ancora essere presente nel PDF
        doc = fitz.open(out)
        images = doc[self.TARGET_PAGE].get_images()
        doc.close()
        assert len(images) >= 1, "L'immagine della pagina scansionata è scomparsa (IMAGE_REMOVE?)"

    def test_output_page_count_unchanged(self, tmp_dir):
        src = _copy_pdf(SCAN_PDF, tmp_dir)
        _add_square_annot(src, self.TARGET_PAGE, self.TARGET_RECT)

        ok, out, _ = rp.process_pdf(src, os.devnull)
        assert ok

        doc_orig = fitz.open(SCAN_PDF)
        doc_out  = fitz.open(out)
        assert len(doc_out) == len(doc_orig)
        doc_orig.close()
        doc_out.close()
