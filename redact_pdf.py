"""
Redact PDF - Rimozione sicura del testo/immagini sotto i mascheramenti.

Doppia modalita':
  - Con argomenti (es. "Invia a"): elaborazione silenziosa, nessuna finestra.
    Converte le annotazioni gia' presenti (rettangoli, ecc.) in mascheramenti vere.
  - Senza argomenti: interfaccia grafica con drag & drop + editor visuale.
    Doppio clic (o "Apri ed edita") su un file apre l'editor per disegnare le
    mascheramenti col mouse (rettangolo / selezione testo / mano libera) e salvare.

Uso: redact_pdf.exe [file1.pdf file2.pdf ...]
     redact_pdf.exe --selftest   (verifica la logica di redazione, senza GUI)
"""

import sys
import os
import fitz  # PyMuPDF
import traceback
from datetime import datetime

VERSION = "3.1.0"
OUTPUT_SUFFIX = "_redacted"

# Tipi di annotazione trattati come coperture di redazione
REDACT_ANNOT_TYPES = {
    fitz.PDF_ANNOT_SQUARE,
    fitz.PDF_ANNOT_CIRCLE,
    fitz.PDF_ANNOT_INK,
    fitz.PDF_ANNOT_POLYGON,
    fitz.PDF_ANNOT_POLY_LINE,
    fitz.PDF_ANNOT_LINE,
    fitz.PDF_ANNOT_HIGHLIGHT,
    fitz.PDF_ANNOT_STRIKE_OUT,
}


# ─── Logging ───────────────────────────────────────────────────────────

def get_log_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def make_log_file():
    return os.path.join(get_log_dir(), "redact_pdf.log")


def log(log_file, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ─── Core redaction engine ─────────────────────────────────────────────

def get_annot_fill_color(annot):
    colors = annot.colors
    fill = colors.get("fill") if colors else None
    if fill:
        return tuple(fill)
    stroke = colors.get("stroke") if colors else None
    if stroke:
        return tuple(stroke)
    return (0, 0, 0)


def apply_secure_redactions(page, rects_with_colors):
    """UNICO punto in cui si applica davvero la redazione su una pagina.

    Riceve una lista di (rect, color) e applica i mascheramenti con opzioni
    sicure ma che NON distruggono il layout:
      - IMAGE_PIXELS: cancella solo i pixel sotto il riquadro (non l'intera
        immagine): indispensabile per i PDF scansionati.
      - LINE_ART_REMOVE_IF_COVERED: rimuove solo le grafiche vettoriali
        interamente coperte, preservando tabelle/linee solo sfiorate.
    Il contenuto sotto il riquadro resta distrutto davvero. Restituisce il
    numero di riquadri applicati.
    """
    applied = 0
    for rect, color in rects_with_colors:
        r = fitz.Rect(rect)
        r.normalize()
        r &= page.rect
        if r.is_empty or r.width < 1 or r.height < 1:
            continue
        page.add_redact_annot(r, fill=color)
        applied += 1
    if applied:
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_PIXELS,
            graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
        )
    return applied


def mark_to_rects(mark):
    """Converte un segno dell'editor (rect/text/free) nei rettangoli di
    redazione in coordinate PDF (fitz.Rect)."""
    t = mark["type"]
    if t == "rect":
        return [mark["rect"]]
    if t == "text":
        return list(mark["rects"])
    if t == "free":
        pts = mark["points"]
        h = mark["half"]
        if len(pts) == 1:
            x, y = pts[0]
            return [fitz.Rect(x - h, y - h, x + h, y + h)]
        out = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            out.append(fitz.Rect(min(x0, x1) - h, min(y0, y1) - h,
                                 max(x0, x1) + h, max(y0, y1) + h))
        return out
    return []


def process_pdf(input_path, log_file, progress_callback=None):
    """
    Processa un singolo PDF. Restituisce (success, output_path, message).
    progress_callback(percent, text) e' opzionale per la GUI.
    """
    if not os.path.isfile(input_path):
        msg = f"File non trovato: {input_path}"
        log(log_file, f"  ERRORE: {msg}")
        return False, None, msg

    if not input_path.lower().endswith(".pdf"):
        msg = f"Non e' un file PDF: {os.path.basename(input_path)}"
        log(log_file, f"  ERRORE: {msg}")
        return False, None, msg

    base, ext = os.path.splitext(input_path)
    output_path = f"{base}{OUTPUT_SUFFIX}{ext}"

    try:
        doc = fitz.open(input_path)
    except Exception as e:
        msg = f"Impossibile aprire: {e}"
        log(log_file, f"  ERRORE: {msg}")
        return False, None, msg

    total_redactions = 0
    num_pages = len(doc)

    try:
        for page_num in range(num_pages):
            page = doc[page_num]
            annots = list(page.annots()) if page.annots() else []

            redact_rects = []
            annots_to_remove = []

            for annot in annots:
                if annot.type[0] in REDACT_ANNOT_TYPES:
                    redact_rects.append({
                        "rect": annot.rect,
                        "color": get_annot_fill_color(annot),
                    })
                    annots_to_remove.append(annot)

            if redact_rects:
                for annot in annots_to_remove:
                    page.delete_annot(annot)

                for rd in redact_rects:
                    page.add_redact_annot(rd["rect"], fill=rd["color"])

                # IMAGE_PIXELS: cancella SOLO i pixel sotto il riquadro, senza
                #   eliminare l'intera immagine. Sui PDF scansionati la pagina e'
                #   un'unica immagine: con IMAGE_REMOVE bastava un riquadro per
                #   cancellare tutta la scansione (pagina vuota / "spaginata").
                # LINE_ART_REMOVE_IF_COVERED: rimuove solo le grafiche vettoriali
                #   interamente coperte, preservando bordi di tabelle e linee solo
                #   sfiorate (IF_TOUCHED cancellava l'intera tabella se toccata).
                # Il contenuto sotto il riquadro resta comunque distrutto davvero.
                page.apply_redactions(
                    images=fitz.PDF_REDACT_IMAGE_PIXELS,
                    graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                )
                total_redactions += len(redact_rects)
                log(log_file, f"  Pagina {page_num+1}: {len(redact_rects)} mascheramenti")

            if progress_callback:
                pct = int((page_num + 1) / num_pages * 100)
                progress_callback(pct, f"Pagina {page_num+1}/{num_pages}")

        doc.save(output_path, garbage=4, deflate=True)
        doc.close()

        if total_redactions == 0:
            msg = "Nessuna annotazione trovata (il file e' stato copiato invariato)"
        else:
            msg = f"{total_redactions} mascheramenti applicate"

        log(log_file, f"  OK: {msg} -> {output_path}")
        return True, output_path, msg

    except Exception as e:
        doc.close()
        msg = f"Errore: {e}"
        log(log_file, f"  ERRORE: {msg}")
        log(log_file, traceback.format_exc())
        return False, None, msg


# ─── Silent mode (Invia a / command line) ──────────────────────────────

def run_silent(files):
    log_file = make_log_file()
    log(log_file, f"=== Redact PDF v{VERSION} (silent) ===")

    success = 0
    errors = 0
    error_files = []

    for f in files:
        f = f.strip('"')
        log(log_file, f"Apertura: {f}")
        ok, _, _ = process_pdf(f, log_file)
        if ok:
            success += 1
        else:
            errors += 1
            error_files.append(os.path.basename(f))

    log(log_file, f"Completato: {success} OK, {errors} errori su {len(files)} file.")

    if errors > 0:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Errori su {errors} di {len(files)} file:\n"
                + "\n".join(error_files)
                + f"\n\nControlla il log:\n{log_file}",
                "Redact PDF - Errore",
                0x10
            )
        except Exception:
            pass


# ─── GUI mode ──────────────────────────────────────────────────────────

def run_gui():
    try:
        import ctypes
        ctypes.CDLL("libX11.so.6").XInitThreads()
    except Exception:
        pass

    # Windows: rende l'app DPI-aware, cosi' 1 px a schermo = 1 px renderizzato.
    # Senza, su monitor con scaling != 100% i riquadri disegnati risulterebbero
    # spostati rispetto al contenuto. No-op fuori da Windows.
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Win 8.1+
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()       # Win Vista+
    except Exception:
        pass

    import tkinter as tk
    from tkinter import filedialog, messagebox
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    ACCENT  = "#7c6fe0"
    ACCENT2 = "#5a51b5"
    SUCCESS = "#4ec98b"
    ERROR   = "#e05f6f"
    SURFACE = "#2a2a3d"
    BG      = "#1e1e2e"
    BORDER  = "#3a3a50"
    FG      = "#e0e0e0"

    class App:
        def __init__(self, root):
            self.root = root
            self.root.title(f"Redact PDF v{VERSION}")
            self.root.geometry("640x580")
            self.root.resizable(True, True)
            self.root.minsize(500, 480)

            self.files = []
            self.log_file = make_log_file()
            self.processing = False

            try:
                self.root.iconbitmap(default="")
            except Exception:
                pass

            self._build_ui()
            self._setup_dnd()

        def _build_ui(self):
            # ── Title ──
            tf = ctk.CTkFrame(self.root, fg_color="transparent")
            tf.pack(fill="x", padx=16, pady=(14, 4))
            ctk.CTkLabel(tf, text="Redact PDF",
                         font=ctk.CTkFont("Segoe UI", 20, "bold"),
                         text_color=ACCENT).pack()
            ctk.CTkLabel(
                tf,
                text="Trascina i PDF e premi Redact — "
                     "oppure doppio clic su un file per disegnare",
                font=ctk.CTkFont("Segoe UI", 11),
                text_color="#888899"
            ).pack()

            # ── Drop zone ──
            self.drop_frame = ctk.CTkFrame(
                self.root, fg_color=SURFACE,
                border_color=BORDER, border_width=2, corner_radius=8)
            self.drop_frame.pack(fill="both", expand=True, padx=16, pady=(0, 6))

            self.drop_label = ctk.CTkLabel(
                self.drop_frame,
                text="Trascina qui i file PDF\n\noppure clicca Sfoglia",
                font=ctk.CTkFont("Segoe UI", 11), text_color="#666680")
            self.drop_label.pack(expand=True, fill="both")

            # File listbox (nascosta finche' non ci sono file)
            lf = tk.Frame(self.drop_frame, bg=SURFACE)
            self.list_frame = lf
            sb = tk.Scrollbar(lf, bg=BORDER, troughcolor=SURFACE,
                              borderwidth=0, activebackground=ACCENT)
            sb.pack(side="right", fill="y")
            self.file_listbox = tk.Listbox(
                lf, font=("Consolas", 9), fg=FG, bg=BG,
                selectbackground=ACCENT2, selectforeground="white",
                borderwidth=0, highlightthickness=0,
                yscrollcommand=sb.set, selectmode="extended")
            self.file_listbox.pack(fill="both", expand=True)
            sb.config(command=self.file_listbox.yview)
            self.file_listbox.bind("<Double-Button-1>", self._on_listbox_dblclick)

            # ── Buttons row ──
            bf = ctk.CTkFrame(self.root, fg_color="transparent")
            bf.pack(fill="x", padx=16, pady=2)

            def mkbtn(parent, text, cmd, **kw):
                kw.setdefault("font", ctk.CTkFont("Segoe UI", 12))
                kw.setdefault("fg_color", SURFACE)
                kw.setdefault("hover_color", BORDER)
                kw.setdefault("text_color", FG)
                kw.setdefault("corner_radius", 6)
                kw.setdefault("height", 34)
                return ctk.CTkButton(parent, text=text, command=cmd, **kw)

            self.browse_btn = mkbtn(bf, "Sfoglia...", self._browse)
            self.browse_btn.pack(side="left")

            self.edit_btn = mkbtn(
                bf, "Apri ed edita", self._edit_selected,
                font=ctk.CTkFont("Segoe UI", 10, "bold"),
                fg_color=ACCENT2, hover_color=ACCENT, text_color="white")
            self.edit_btn.pack(side="left", padx=(8, 0))

            self.remove_btn = mkbtn(bf, "Rimuovi selezionati",
                                    self._remove_selected)
            self.remove_btn.pack(side="left", padx=(8, 0))

            self.clear_btn = mkbtn(bf, "Svuota", self._clear,
                                   text_color=ERROR)
            self.clear_btn.pack(side="left", padx=(8, 0))

            self.count_label = ctk.CTkLabel(
                bf, text="", font=ctk.CTkFont("Segoe UI", 11),
                text_color="#888899")
            self.count_label.pack(side="right")

            # ── Progress ──
            pf = ctk.CTkFrame(self.root, fg_color="transparent")
            pf.pack(fill="x", padx=16, pady=2)

            self.progress = ctk.CTkProgressBar(
                pf, fg_color=SURFACE, progress_color=ACCENT,
                corner_radius=4, height=8)
            self.progress.set(0)
            self.progress.pack(fill="x")

            self.status_label = ctk.CTkLabel(
                pf, text="", font=ctk.CTkFont("Segoe UI", 11),
                text_color="#888899", anchor="w")
            self.status_label.pack(fill="x", pady=(4, 0))

            # ── Redact button ──
            rf = ctk.CTkFrame(self.root, fg_color="transparent")
            rf.pack(fill="x", padx=16, pady=10)
            self.redact_btn = ctk.CTkButton(
                rf, text="REDACT",
                font=ctk.CTkFont("Segoe UI", 14, "bold"),
                fg_color=ACCENT, hover_color=ACCENT2,
                text_color="white", corner_radius=8,
                height=42, command=self._redact)
            self.redact_btn.pack()

        def _setup_dnd(self):
            try:
                import windnd
                windnd.hook_dropfiles(self.root, func=self._on_drop)
            except Exception:
                pass

        def _on_drop(self, file_list):
            added = 0
            for f in file_list:
                if isinstance(f, bytes):
                    f = f.decode("utf-8", errors="replace")
                f = f.strip()
                if f.lower().endswith(".pdf") and f not in self.files:
                    self.files.append(f)
                    added += 1
            if added:
                self._refresh_list()

        def _browse(self):
            paths = filedialog.askopenfilenames(
                title="Seleziona file PDF", filetypes=[("PDF", "*.pdf")])
            added = 0
            for p in paths:
                if p not in self.files:
                    self.files.append(p)
                    added += 1
            if added:
                self._refresh_list()

        def _remove_selected(self):
            sel = self.file_listbox.curselection()
            if not sel:
                return
            for i in sorted(sel, reverse=True):
                del self.files[i]
            self._refresh_list()

        def _edit_selected(self):
            sel = self.file_listbox.curselection()
            if sel:
                idx = sel[0]
            elif len(self.files) == 1:
                idx = 0
            else:
                self._set_status(
                    "Seleziona un file in lista da aprire nell'editor.", ERROR)
                return
            self._open_editor(self.files[idx])

        def _on_listbox_dblclick(self, event):
            idx = self.file_listbox.nearest(event.y)
            if 0 <= idx < len(self.files):
                self._open_editor(self.files[idx])

        def _open_editor(self, path):
            if self.processing:
                return
            try:
                RedactEditor(self.root, path, self.log_file)
            except Exception as e:
                log(self.log_file, f"Errore apertura editor: {e}")
                log(self.log_file, traceback.format_exc())
                self._set_status(f"Impossibile aprire l'editor: {e}", ERROR)

        def _clear(self):
            self.files.clear()
            self._refresh_list()

        def _refresh_list(self):
            self.file_listbox.delete(0, "end")
            for f in self.files:
                self.file_listbox.insert("end", f"  {os.path.basename(f)}")
            if self.files:
                self.drop_label.pack_forget()
                self.list_frame.pack(fill="both", expand=True)
            else:
                self.list_frame.pack_forget()
                self.drop_label.pack(expand=True, fill="both")
            n = len(self.files)
            self.count_label.configure(
                text=f"{n} file" if n != 1 else "1 file")

        def _set_status(self, text, color="#888899"):
            self.status_label.configure(text=text, text_color=color)
            self.root.update_idletasks()

        def _set_progress(self, value):
            self.progress.set(value / 100)
            self.root.update_idletasks()

        def _set_buttons_state(self, state):
            for w in (self.browse_btn, self.edit_btn,
                      self.remove_btn, self.clear_btn, self.redact_btn):
                w.configure(state=state)

        def _redact(self):
            if not self.files:
                self._set_status("Nessun file da elaborare.", ERROR)
                return
            if self.processing:
                return

            self.processing = True
            self._set_buttons_state("disabled")
            total = len(self.files)
            success = 0
            errors = 0
            log(self.log_file, f"=== Redact PDF v{VERSION} (GUI) ===")

            for i, f in enumerate(self.files):
                basename = os.path.basename(f)
                self._set_status(f"Elaborazione {i+1}/{total}: {basename}...")
                self._set_progress(0)
                log(self.log_file, f"Apertura: {f}")

                def progress_cb(pct, text, _i=i, _tot=total):
                    self._set_progress((_i + pct / 100) / _tot * 100)

                ok, out, msg = process_pdf(f, self.log_file, progress_cb)
                if ok:
                    success += 1
                    self.file_listbox.delete(i)
                    self.file_listbox.insert(i, f"  {basename}  ✓  {msg}")
                    self.file_listbox.itemconfig(i, fg=SUCCESS)
                else:
                    errors += 1
                    self.file_listbox.delete(i)
                    self.file_listbox.insert(i, f"  {basename}  ✗  {msg}")
                    self.file_listbox.itemconfig(i, fg=ERROR)

            self._set_progress(100)
            if errors == 0:
                self._set_status(
                    f"Completato: {success} file elaborati con successo.",
                    SUCCESS)
            else:
                self._set_status(
                    f"Completato: {success} OK, {errors} errori. Vedi log.",
                    ERROR)
            self._set_buttons_state("normal")
            self.processing = False

    class RedactEditor:
        """Editor visuale: apri un PDF, disegna i mascheramenti con il mouse
        (rettangolo / selezione testo / mano libera), poi 'Applica e salva'.
        I segni sono memorizzati in coordinate PDF, quindi restano allineati
        a qualsiasi zoom e su qualsiasi pagina."""

        PEN_PX   = 16
        ZOOM_MIN = 0.2
        ZOOM_MAX = 6.0

        def __init__(self, parent, path, log_file):
            self.parent   = parent
            self.path     = path
            self.log_file = log_file
            self.doc = fitz.open(path)
            if self.doc.page_count == 0:
                self.doc.close()
                raise ValueError("PDF senza pagine")

            self.page_index   = 0
            self.zoom         = 1.0
            self.tool         = "rect"
            self.redact_color = (0, 0, 0)
            self.marks        = {}
            self.history      = []
            self._photo       = None
            self._drag_start  = None
            self._free_points = None
            self._live_ids    = []
            self._color_btn   = None

            self.win = ctk.CTkToplevel(parent)
            self.win.title(f"Editor mascheramenti — {os.path.basename(path)}")
            self.win.geometry("1100x800")
            self.win.minsize(820, 560)
            self.win.protocol("WM_DELETE_WINDOW", self._close)
            self.win.after(50, self.win.lift)

            self._build_ui()
            self._set_tool("rect")
            self.win.update_idletasks()
            self._fit_to_window()
            self._render_page()

            self.win.bind("<Control-z>", lambda e: self._undo())
            self.win.bind("<Control-s>", lambda e: self._save())
            self.win.bind("<Next>",  lambda e: self._go(1))   # PagGiu
            self.win.bind("<Prior>", lambda e: self._go(-1))  # PagSu

        # ── costruzione UI ──────────────────────────────────────────────
        def _build_ui(self):
            def tbtn(parent, text, cmd, **kw):
                kw.setdefault("font", ctk.CTkFont("Segoe UI", 12))
                kw.setdefault("fg_color", SURFACE)
                kw.setdefault("hover_color", BORDER)
                kw.setdefault("text_color", FG)
                kw.setdefault("corner_radius", 6)
                kw.setdefault("height", 34)
                kw.setdefault("width", 0)
                return ctk.CTkButton(parent, text=text, command=cmd, **kw)

            # ── Riga 1: strumenti + colore + annulla/pulisci ──
            tb1 = ctk.CTkFrame(self.win, fg_color=BG, corner_radius=0, height=52)
            tb1.pack(fill="x")
            tb1.pack_propagate(False)

            self.tool_btns = {}
            for key, label in (("rect", "▭ Rettangolo"),
                               ("text", "✎ Testo"),
                               ("free", "〰 Mano libera")):
                b = tbtn(tb1, label, lambda k=key: self._set_tool(k))
                b.pack(side="left", padx=(8, 4), pady=8)
                self.tool_btns[key] = b

            tk.Frame(tb1, bg=BORDER, width=2, height=24).pack(
                side="left", padx=6, pady=11)

            self._color_btn = ctk.CTkButton(
                tb1, text="■ Colore",
                font=ctk.CTkFont("Segoe UI", 12),
                fg_color="#000000", hover_color="#222222",
                text_color="white", corner_radius=6,
                height=34, width=0, command=self._pick_color)
            self._color_btn.pack(side="left", padx=(0, 4), pady=8)

            tk.Frame(tb1, bg=BORDER, width=2, height=24).pack(
                side="left", padx=6, pady=11)

            tbtn(tb1, "↶ Annulla", self._undo).pack(
                side="left", padx=(0, 4), pady=8)
            tbtn(tb1, "✗ Pulisci pagina", self._clear_page).pack(
                side="left", padx=(0, 4), pady=8)

            # ── Riga 2: zoom + navigazione + salva ──
            tb2 = ctk.CTkFrame(self.win, fg_color=SURFACE, corner_radius=0,
                               height=44)
            tb2.pack(fill="x")
            tb2.pack_propagate(False)

            tbtn(tb2, "−", lambda: self._zoom_by(0.8), width=36).pack(
                side="left", padx=(8, 0), pady=5)
            self.zoom_lbl = ctk.CTkLabel(
                tb2, text="100%", font=ctk.CTkFont("Segoe UI", 11),
                text_color=FG, width=52)
            self.zoom_lbl.pack(side="left", padx=2)
            tbtn(tb2, "+", lambda: self._zoom_by(1.25), width=36).pack(
                side="left", padx=(0, 6), pady=5)

            tk.Frame(tb2, bg=BORDER, width=2, height=20).pack(
                side="left", padx=6, pady=12)

            self.prev_btn = tbtn(tb2, "◀ Prec.", lambda: self._go(-1))
            self.prev_btn.pack(side="left", padx=(0, 4), pady=5)
            self.page_lbl = ctk.CTkLabel(
                tb2, text="", font=ctk.CTkFont("Segoe UI", 12),
                text_color=FG, width=140)
            self.page_lbl.pack(side="left", padx=4)
            self.next_btn = tbtn(tb2, "Succ. ▶", lambda: self._go(1))
            self.next_btn.pack(side="left", padx=(0, 4), pady=5)

            self.save_btn = tbtn(
                tb2, "✔ Applica e salva", self._save,
                font=ctk.CTkFont("Segoe UI", 12, "bold"),
                fg_color=ACCENT, hover_color=ACCENT2, text_color="white")
            self.save_btn.pack(side="right", padx=(0, 8), pady=5)

            # ── Canvas ──
            cf = tk.Frame(self.win, bg="#3a3a3a")
            cf.pack(fill="both", expand=True)
            vsb = tk.Scrollbar(cf, orient="vertical")
            vsb.pack(side="right", fill="y")
            hsb = tk.Scrollbar(cf, orient="horizontal")
            hsb.pack(side="bottom", fill="x")
            self.canvas = tk.Canvas(cf, bg="#3a3a3a", highlightthickness=0,
                                    xscrollcommand=hsb.set,
                                    yscrollcommand=vsb.set)
            self.canvas.pack(side="left", fill="both", expand=True)
            vsb.config(command=self.canvas.yview)
            hsb.config(command=self.canvas.xview)
            self.canvas.bind("<ButtonPress-1>",  self._on_press)
            self.canvas.bind("<B1-Motion>",       self._on_drag)
            self.canvas.bind("<ButtonRelease-1>", self._on_release)
            # rotellina verticale (Windows/macOS e Linux)
            self.canvas.bind("<MouseWheel>",   self._on_mousewheel)
            self.canvas.bind("<Button-4>",     self._on_mousewheel)
            self.canvas.bind("<Button-5>",     self._on_mousewheel)
            # rotellina orizzontale con Shift
            self.canvas.bind("<Shift-MouseWheel>", self._on_mousewheel_h)
            self.canvas.bind("<Shift-Button-4>",   self._on_mousewheel_h)
            self.canvas.bind("<Shift-Button-5>",   self._on_mousewheel_h)

            # ── Status bar ──
            self.status = ctk.CTkLabel(
                self.win, text="",
                font=ctk.CTkFont("Segoe UI", 11),
                text_color="#aaaacc", fg_color=SURFACE, anchor="w")
            self.status.pack(fill="x")

        # ── coordinate ──────────────────────────────────────────────────
        def _page(self):
            return self.doc[self.page_index]

        def canvas_to_pdf(self, cx, cy):
            r = self._page().rect
            return (r.x0 + cx / self.zoom, r.y0 + cy / self.zoom)

        def pdf_to_canvas(self, x, y):
            r = self._page().rect
            return ((x - r.x0) * self.zoom, (y - r.y0) * self.zoom)

        def _tk_color(self, rgb):
            r, g, b = [max(0, min(255, int(round(c * 255)))) for c in rgb]
            return f"#{r:02x}{g:02x}{b:02x}"

        def _fit_to_window(self):
            self.zoom = 1.0

        # ── rendering ───────────────────────────────────────────────────
        def _render_page(self):
            page = self._page()
            pix = page.get_pixmap(
                matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
            self._photo = tk.PhotoImage(data=pix.tobytes("ppm"))
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw",
                                     image=self._photo, tags="page")
            self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))
            self._redraw_marks()
            self.page_lbl.configure(
                text=f"Pagina {self.page_index + 1} / {self.doc.page_count}")
            self.zoom_lbl.configure(text=f"{int(self.zoom * 100)}%")
            self.prev_btn.configure(
                state="normal" if self.page_index > 0 else "disabled")
            self.next_btn.configure(
                state="normal" if self.page_index < self.doc.page_count - 1
                else "disabled")

        def _redraw_marks(self):
            self.canvas.delete("mark")
            for mark in self.marks.get(self.page_index, []):
                self._draw_mark(mark)

        def _draw_mark(self, mark):
            color = self._tk_color(mark.get("color", (0, 0, 0)))
            if mark["type"] == "free":
                pts = mark["points"]
                if len(pts) >= 2:
                    flat = []
                    for x, y in pts:
                        cx, cy = self.pdf_to_canvas(x, y)
                        flat.extend((cx, cy))
                    w = max(2, mark["half"] * 2 * self.zoom)
                    self.canvas.create_line(
                        *flat, fill=color, width=w,
                        capstyle="round", joinstyle="round",
                        stipple="gray50", tags="mark")
                    self.canvas.create_line(
                        *flat, fill=ACCENT, width=1, tags="mark")
                else:
                    x, y = pts[0]
                    cx, cy = self.pdf_to_canvas(x, y)
                    rr = mark["half"] * self.zoom
                    self.canvas.create_oval(
                        cx - rr, cy - rr, cx + rr, cy + rr,
                        fill=color, outline=ACCENT,
                        stipple="gray50", tags="mark")
            else:
                for r in mark_to_rects(mark):
                    cx0, cy0 = self.pdf_to_canvas(r.x0, r.y0)
                    cx1, cy1 = self.pdf_to_canvas(r.x1, r.y1)
                    self.canvas.create_rectangle(
                        cx0, cy0, cx1, cy1, fill=color,
                        stipple="gray50", outline=ACCENT, width=1,
                        tags="mark")

        # ── strumenti / eventi ──────────────────────────────────────────
        def _set_tool(self, key):
            self.tool = key
            for k, b in self.tool_btns.items():
                if k == key:
                    b.configure(fg_color=ACCENT, hover_color=ACCENT2,
                                text_color="white")
                else:
                    b.configure(fg_color=SURFACE, hover_color=BORDER,
                                text_color=FG)
            cursor = {"rect": "crosshair", "text": "xterm",
                      "free": "pencil"}.get(key, "crosshair")
            try:
                self.canvas.config(cursor=cursor)
            except Exception:
                self.canvas.config(cursor="crosshair")
            hint = {
                "rect": "Rettangolo: trascina per coprire un'area "
                        "(anche sulle scansioni).",
                "text": "Testo: trascina sul testo da nascondere "
                        "(solo PDF con testo, non scansioni).",
                "free": "Mano libera: tieni premuto e traccia "
                        "sopra l'area da coprire.",
            }[key]
            self._status(hint)

        def _pick_color(self):
            from tkinter import colorchooser
            r, g, b = [int(c * 255) for c in self.redact_color]
            init_hex = f"#{r:02x}{g:02x}{b:02x}"
            result = colorchooser.askcolor(
                color=init_hex,
                title="Colore dell'area redatta",
                parent=self.win)
            if result and result[0]:
                ri, gi, bi = [int(v) for v in result[0]]
                self.redact_color = (ri / 255, gi / 255, bi / 255)
                hex_color = f"#{ri:02x}{gi:02x}{bi:02x}"
                brightness = 0.299 * ri + 0.587 * gi + 0.114 * bi
                fg_text = "white" if brightness < 128 else "black"
                self._color_btn.configure(
                    fg_color=hex_color, hover_color=hex_color,
                    text_color=fg_text)

        def _clear_live(self):
            for i in self._live_ids:
                self.canvas.delete(i)
            self._live_ids = []

        def _on_press(self, event):
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            self._drag_start = (cx, cy)
            self._clear_live()
            if self.tool == "free":
                self._free_points = [(cx, cy)]

        def _on_drag(self, event):
            if self._drag_start is None:
                return
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            self._clear_live()
            if self.tool == "free":
                self._free_points.append((cx, cy))
                if len(self._free_points) >= 2:
                    flat = [v for p in self._free_points for v in p]
                    self._live_ids.append(self.canvas.create_line(
                        *flat, fill="#ff5566", width=self.PEN_PX,
                        capstyle="round", joinstyle="round",
                        stipple="gray50"))
            else:
                x0, y0 = self._drag_start
                self._live_ids.append(self.canvas.create_rectangle(
                    x0, y0, cx, cy, outline="#ff5566", width=2, dash=(4, 2)))

        def _on_release(self, event):
            if self._drag_start is None:
                return
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            x0, y0 = self._drag_start
            self._drag_start = None
            self._clear_live()
            if self.tool == "rect":
                self._add_rect_mark(x0, y0, cx, cy)
            elif self.tool == "text":
                self._add_text_mark(x0, y0, cx, cy)
            elif self.tool == "free":
                self._add_free_mark()
            self._free_points = None

        def _on_mousewheel(self, event):
            if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
                self.canvas.yview_scroll(-1, "units")
            else:
                self.canvas.yview_scroll(1, "units")

        def _on_mousewheel_h(self, event):
            if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
                self.canvas.xview_scroll(-1, "units")
            else:
                self.canvas.xview_scroll(1, "units")

        def _add_rect_mark(self, x0, y0, x1, y1):
            if abs(x1 - x0) < 3 or abs(y1 - y0) < 3:
                return
            p0 = self.canvas_to_pdf(min(x0, x1), min(y0, y1))
            p1 = self.canvas_to_pdf(max(x0, x1), max(y0, y1))
            self._commit_mark({"type": "rect",
                               "rect": fitz.Rect(p0[0], p0[1], p1[0], p1[1]),
                               "color": self.redact_color})

        def _add_text_mark(self, x0, y0, x1, y1):
            if abs(x1 - x0) < 3 or abs(y1 - y0) < 3:
                return
            p0 = self.canvas_to_pdf(min(x0, x1), min(y0, y1))
            p1 = self.canvas_to_pdf(max(x0, x1), max(y0, y1))
            drag = fitz.Rect(p0[0], p0[1], p1[0], p1[1])
            rects = [fitz.Rect(w[:4]) for w in self._page().get_text("words")
                     if fitz.Rect(w[:4]).intersects(drag)]
            if not rects:
                self._status(
                    "Nessun testo qui (è una scansione? usa Rettangolo).",
                    warn=True)
                return
            self._commit_mark({"type": "text", "rects": rects,
                               "color": self.redact_color})

        def _add_free_mark(self):
            pts = self._free_points or []
            if len(pts) < 2:
                return
            pdf_pts = [self.canvas_to_pdf(cx, cy) for cx, cy in pts]
            half = (self.PEN_PX / 2.0) / self.zoom
            self._commit_mark({"type": "free", "points": pdf_pts,
                               "half": half, "color": self.redact_color})

        def _commit_mark(self, mark):
            self.marks.setdefault(self.page_index, []).append(mark)
            self.history.append((self.page_index, mark))
            self._draw_mark(mark)
            n = sum(len(v) for v in self.marks.values())
            self._status(f"Segno aggiunto (totale {n}). Ctrl+Z per annullare.")

        def _undo(self):
            if not self.history:
                return
            pno, mark = self.history.pop()
            lst = self.marks.get(pno, [])
            for i in range(len(lst) - 1, -1, -1):
                if lst[i] is mark:
                    del lst[i]
                    break
            if pno == self.page_index:
                self._redraw_marks()
            else:
                self.page_index = pno
                self._render_page()
            self._status("Annullato.")

        def _clear_page(self):
            if self.marks.get(self.page_index):
                self.marks[self.page_index] = []
                self.history = [(p, m) for (p, m) in self.history
                                if p != self.page_index]
                self._redraw_marks()
                self._status("Segni della pagina rimossi.")

        def _go(self, delta):
            new = self.page_index + delta
            if 0 <= new < self.doc.page_count:
                self.page_index = new
                self._render_page()

        def _zoom_by(self, factor):
            self.zoom = max(self.ZOOM_MIN,
                            min(self.ZOOM_MAX, self.zoom * factor))
            self._render_page()

        def _status(self, text, warn=False):
            self.status.configure(
                text=text, text_color=(ERROR if warn else "#aaaacc"))

        # ── salvataggio ─────────────────────────────────────────────────
        def _save(self):
            base, ext = os.path.splitext(self.path)
            out = f"{base}{OUTPUT_SUFFIX}{ext}"
            log(self.log_file, f"=== Editor v{VERSION}: {self.path} ===")
            try:
                work = fitz.open(self.path)
                applied = 0
                for pno in range(work.page_count):
                    page = work[pno]
                    rects = []
                    for annot in list(page.annots() or []):
                        if annot.type[0] in REDACT_ANNOT_TYPES:
                            rects.append((annot.rect,
                                         get_annot_fill_color(annot)))
                            page.delete_annot(annot)
                    for mark in self.marks.get(pno, []):
                        for r in mark_to_rects(mark):
                            rects.append((r, mark.get("color", (0, 0, 0))))
                    applied += apply_secure_redactions(page, rects)
                work.save(out, garbage=4, deflate=True)
                work.close()
            except Exception as e:
                log(self.log_file, f"  ERRORE: {e}")
                log(self.log_file, traceback.format_exc())
                messagebox.showerror(
                    "Redact PDF",
                    f"Errore durante il salvataggio:\n{e}",
                    parent=self.win)
                return

            log(self.log_file, f"  OK: {applied} mascheramenti -> {out}")
            if applied == 0:
                messagebox.showwarning(
                    "Redact PDF",
                    "Nessuna redazione da applicare.\n"
                    "Disegna almeno un riquadro prima di salvare.",
                    parent=self.win)
                self._status("Nessuna redazione applicata.", warn=True)
            else:
                messagebox.showinfo(
                    "Redact PDF",
                    f"{applied} mascheramenti applicate.\n\nSalvato in:\n{out}",
                    parent=self.win)
                self._status(
                    f"Salvato: {os.path.basename(out)} ({applied} mascheramenti).")

        def _close(self):
            try:
                self.doc.close()
            except Exception:
                pass
            self.win.destroy()

    root = ctk.CTk()
    app = App(root)
    root.mainloop()


# ─── Entry point ───────────────────────────────────────────────────────

def run_selftest():
    """Verifica rapida della logica di redazione, SENZA GUI.
    Uso: python redact_pdf.py --selftest"""
    ok_all = True

    def check(name, cond):
        nonlocal ok_all
        ok_all = ok_all and bool(cond)
        print(f"[{'OK  ' if cond else 'FAIL'}] {name}")

    # 1) Scansione: l'immagine resta, l'area del riquadro viene distrutta
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 595, 842))
    pix.set_rect(pix.irect, (235, 235, 235))
    for y in range(40, 820, 40):
        pix.set_rect(fitz.IRect(30, y, 565, y + 12), (40, 40, 40))
    page.insert_image(page.rect, pixmap=pix)
    apply_secure_redactions(page, [(fitz.Rect(120, 360, 330, 420), (0, 0, 0))])
    imgs = len(page.get_images())
    far = page.get_pixmap(dpi=72, clip=fitz.Rect(30, 600, 565, 700))
    far_distinct = len({far.samples[i] for i in range(0, len(far.samples), far.n)})
    box = page.get_pixmap(dpi=72, clip=fitz.Rect(150, 378, 300, 402))
    box_distinct = len({box.samples[i] for i in range(0, len(box.samples), box.n)})
    check("scansione: immagine preservata", imgs == 1)
    check("scansione: contenuto fuori dal riquadro intatto", far_distinct > 1)
    check("scansione: contenuto sotto il riquadro distrutto", box_distinct == 1)
    doc.close()

    # 2) Mapping coordinate dell'editor, per tutte le rotazioni
    ZOOM = 2.0

    def c2p(pg, cx, cy):
        r = pg.rect
        return (r.x0 + cx / ZOOM, r.y0 + cy / ZOOM)

    def p2c(pg, x, y):
        r = pg.rect
        return ((x - r.x0) * ZOOM, (y - r.y0) * ZOOM)

    for rot in (0, 90, 180, 270):
        d = fitz.open()
        pg = d.new_page(width=400, height=600)
        pg.insert_text((60, 90), "TARGET", fontsize=20)
        pg.insert_text((60, 540), "KEEPME", fontsize=20)
        pg.set_rotation(rot)
        R = (pg.search_for("TARGET") or [None])[0]
        cx0, cy0 = p2c(pg, R.x0, R.y0)
        cx1, cy1 = p2c(pg, R.x1, R.y1)
        q0 = c2p(pg, min(cx0, cx1), min(cy0, cy1))
        q1 = c2p(pg, max(cx0, cx1), max(cy0, cy1))
        apply_secure_redactions(
            pg, [(fitz.Rect(q0[0], q0[1], q1[0], q1[1]), (0, 0, 0))])
        t = pg.get_text()
        check(f"mapping rot {rot}: TARGET redatto e KEEPME intatto",
              "TARGET" not in t and "KEEPME" in t)
        d.close()

    # 3) Selezione testo: parole che intersecano il trascinamento
    d = fitz.open()
    pg = d.new_page(width=400, height=200)
    pg.insert_text((40, 80), "Mario Rossi residente Roma", fontsize=14)
    drag = fitz.Rect(38, 66, 120, 86)
    sel = [w[4] for w in pg.get_text("words")
           if fitz.Rect(w[:4]).intersects(drag)]
    check("selezione testo: trova le parole", "Mario" in sel)
    d.close()

    # 4) Mano libera -> rettangoli di redazione
    free = {"type": "free", "points": [(50, 50), (70, 55), (95, 52)], "half": 6}
    check("mano libera: genera i rettangoli", len(mark_to_rects(free)) == 2)

    print("\nRISULTATO:", "TUTTO OK" if ok_all else "CI SONO ERRORI")
    return 0 if ok_all else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(run_selftest())
    if len(sys.argv) > 1:
        run_silent(sys.argv[1:])
    else:
        run_gui()


if __name__ == "__main__":
    main()
