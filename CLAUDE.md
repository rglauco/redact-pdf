# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Converts PDF annotations (Square, Circle, Ink, Polygon, PolyLine, Line, Highlight, StrikeOut) into true redactions that permanently remove the underlying text and images. Built for Windows corporate deployment via GPO.

Since v3.0 the GUI also includes a **visual editor**: open a PDF and draw redactions directly with the mouse (rectangle / text-selection / freehand), no external annotator needed.

## Running the script

```bash
# GUI mode (no args)
python redact_pdf.py

# Silent/batch mode
python redact_pdf.py file1.pdf file2.pdf

# Headless self-test of the redaction logic (no GUI)
python redact_pdf.py --selftest
```

## Building the Windows EXE

Run on a Windows machine with Python 3.8+:

```
build.bat
```

Dependencies installed by build: `PyMuPDF`, `windnd`, `pyinstaller`. Output: `dist\redact_pdf.exe`.

## Architecture

Single-file Python script (`redact_pdf.py`) with two execution modes selected at startup via `sys.argv`:

- **Silent mode** (`run_silent`): no window, processes files from CLI args, shows a Windows MessageBox only on errors via `ctypes.windll`
- **GUI mode** (`run_gui`): tkinter app with drag & drop (via optional `windnd`), file listbox, progress bar. Double-clicking a listed file (or the **"Apri ed edita"** button) opens the visual editor.

**Core engine** (`process_pdf`): opens the PDF with PyMuPDF (`fitz`), collects all annotations whose type is in `REDACT_ANNOT_TYPES`, deletes the original annotations, then redacts via the shared `apply_secure_redactions()` helper.

**`apply_secure_redactions(page, rects_with_colors)`**: the single place that actually applies redactions. Uses `PDF_REDACT_IMAGE_PIXELS` (erase only the pixels under the box, not the whole image — critical for scanned PDFs where the page is one big image) and `PDF_REDACT_LINE_ART_REMOVE_IF_COVERED` (drop only fully-covered vector art, preserving touched table borders). Both `process_pdf` and the editor go through it, so security and layout-preservation behave identically.

**Visual editor** (`RedactEditor`, nested in `run_gui`): a `Toplevel` with a `Canvas` showing the rendered page (`page.get_pixmap` → `tk.PhotoImage` PPM). Marks are stored per-page in **PDF coordinates** (dicts: `{"type": "rect"|"text"|"free", ...}`), so they stay aligned across zoom and rotation. `mark_to_rects()` converts a mark to redaction rects; text-tool marks snap to words via `page.get_text("words")`; freehand becomes a chain of thick segment-rects. Save reopens the original from disk (leaving the editing session untouched) and runs the same `apply_secure_redactions()` pipeline. On Windows the GUI calls `SetProcessDpiAwareness` so 1 screen px = 1 rendered px (otherwise drawn boxes drift under display scaling).

`windnd` is optional — drag & drop silently degrades to the Browse button if the package is absent.

## Deployment

`deploy_gpo.bat` runs as a GPO logon script and creates a `.lnk` shortcut in each user's `SendTo` folder pointing to the EXE on a network share (`\\SERVER\tools$\RedactPDF\redact_pdf.exe`). Update the `EXE_PATH` variable in that file when the share path changes.

Log file (`redact_pdf.log`) is written alongside the EXE (or alongside the `.py` when running from source).
