#!/usr/bin/env python3
"""
GermanSpeak PDF Reader
A standalone Windows .exe PDF reader focused on language learning.

- High-quality PDF rendering with PyMuPDF
- Accurate word-by-word text selection (real highlight, not just rectangle)
- One-click "Speak German" + "Translate + Speak English" using the same
  high-quality approach as the browser extension (Microsoft neural voices via edge-tts
  + Google Translate free endpoint)
- Clean, modern UI with CustomTkinter
- Simple highlight → click big button to speak (exactly as requested)

Build to .exe:
  .\.venv\Scripts\Activate.ps1
  pyinstaller --onefile --windowed --name "GermanSpeak-PDF-Reader" --icon "icons/icon48.jpg" --add-data "icons;icons" app.py

The resulting .exe will be in the dist/ folder.
"""

import os
import sys
import io
import tempfile
import asyncio
import threading
import subprocess
from pathlib import Path

import fitz  # PyMuPDF
import customtkinter as ctk
from PIL import Image, ImageTk
import requests
import edge_tts

# ---------- Constants & Voice Choices (high quality Microsoft Neural voices) ----------
APP_NAME = "GermanSpeak PDF Reader"
BEST_GERMAN_VOICE = "de-DE-KatjaNeural"   # Excellent, clear female neural
BEST_ENGLISH_VOICE = "en-US-JennyNeural"  # Excellent, natural female neural

# Fallback voices if the preferred ones are not available on the user's region
FALLBACK_GERMAN = "de-DE-ConradNeural"
FALLBACK_ENGLISH = "en-US-GuyNeural"

# Google Translate (same free endpoint used by the browser extension)
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

# UI colors (inspired by the original extension)
PRIMARY = "#4f46e5"
PRIMARY_HOVER = "#4338ca"
BG = "#0f172a"
CARD_BG = "#1e293b"
TEXT = "#f1f5f9"
TEXT_SECONDARY = "#94a3b8"
HIGHLIGHT = "#6366f1"  # indigo highlight for selected words


def resource_path(relative_path: str) -> str:
    """Get absolute path for resources (works in dev and PyInstaller onefile)."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def get_icon(size: int = 48) -> str:
    """Return path to a bundled icon (jpg works for CTk)."""
    icon_dir = resource_path("icons")
    candidates = [
        os.path.join(icon_dir, f"icon{size}.jpg"),
        os.path.join(icon_dir, "icon48.jpg"),
        os.path.join(icon_dir, "icon32.jpg"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return ""


# ---------- Translation (exact same logic as the browser extension) ----------
def translate_text(text: str, source_lang: str = "de", target_lang: str = "en") -> dict:
    """Translate using the free Google endpoint (same as the Chrome/Edge extension)."""
    if not text or not text.strip():
        return {"translated": "", "detectedLang": source_lang}

    safe_text = text[:4500]
    params = {
        "client": "gtx",
        "sl": source_lang,
        "tl": target_lang,
        "dt": "t",
        "q": safe_text,
    }
    try:
        resp = requests.get(TRANSLATE_URL, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        translated = ""
        if isinstance(data, list) and data and isinstance(data[0], list):
            translated = "".join(part[0] or "" for part in data[0] if part)
        detected = data[2] if len(data) > 2 and data[2] else source_lang
        return {"translated": translated.strip(), "detectedLang": detected}
    except Exception:
        return {"translated": "(translation unavailable)", "detectedLang": source_lang}


# ---------- High-quality TTS using Microsoft Edge Neural voices (edge-tts) ----------
def _pick_voice(lang: str) -> str:
    if lang.startswith("de"):
        return BEST_GERMAN_VOICE
    return BEST_ENGLISH_VOICE


async def _speak_edge_tts(text: str, voice: str, rate: str = "-5%") -> str:
    """Generate mp3 with edge-tts and return path to temp file."""
    if not text or not text.strip():
        return ""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        path = tmp.name
    await communicate.save(path)
    return path


def speak_async(text: str, lang: str = "de-DE", on_done=None):
    """Run edge-tts in a background thread and play the result with the default player."""
    if not text or not text.strip():
        if on_done:
            on_done()
        return

    voice = _pick_voice(lang)
    rate = "-8%" if lang.startswith("de") else "-3%"   # slightly slower for German clarity

    def worker():
        try:
            mp3_path = asyncio.run(_speak_edge_tts(text, voice, rate))
            if mp3_path and os.path.exists(mp3_path):
                # Play with the user's default media player (non-blocking)
                # This is reliable, uses the excellent neural cloud voices, and requires no extra audio libs.
                try:
                    os.startfile(mp3_path)
                except Exception:
                    # Fallback: open with explorer / shell
                    subprocess.Popen(["explorer", mp3_path], shell=True)
                # Optional: we leave the temp file; Windows will clean %TEMP% eventually.
                # For a cleaner app we could schedule deletion after a delay.
        except Exception as e:
            print(f"[GermanSpeak PDF] TTS error: {e}")
        finally:
            if on_done:
                on_done()

    threading.Thread(target=worker, daemon=True).start()


def stop_all_audio():
    """Best-effort stop of media playback started by os.startfile.
    On Windows this is difficult without killing the player, so we just clean temps
    and tell the user they can pause in the player.
    """
    # We could taskkill common players here, but it's aggressive.
    # For now we just print a hint. Users can pause the media player that popped up.
    print("[GermanSpeak PDF] Stop requested – pause the media player or close it.")


# ---------- The main application ----------
class GermanSpeakPDFReader(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x780")
        self.minsize(900, 620)

        # Theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.doc: fitz.Document | None = None
        self.current_page = 0
        self.zoom = 1.6
        self.page_words: list = []          # list of (x0,y0,x1,y1, text, ...)
        self.selected_words: list = []      # indices into page_words
        self.selection_rects = []           # canvas items for highlights

        self._temp_files = []
        self._is_speaking = False

        self._build_ui()
        self._bind_keys()

        # Try to set icon
        icon = get_icon(48)
        if icon:
            try:
                self.iconphoto(False, ImageTk.PhotoImage(Image.open(icon)))
            except Exception:
                pass

    def _build_ui(self):
        # Top toolbar
        toolbar = ctk.CTkFrame(self, height=52, corner_radius=0)
        toolbar.pack(fill="x", padx=0, pady=0)

        self.open_btn = ctk.CTkButton(toolbar, text="📂 Open PDF", command=self.open_pdf,
                                      width=120, height=36, fg_color=PRIMARY, hover_color=PRIMARY_HOVER)
        self.open_btn.pack(side="left", padx=12, pady=8)

        self.prev_btn = ctk.CTkButton(toolbar, text="◀ Prev", command=self.prev_page, width=80, height=32)
        self.prev_btn.pack(side="left", padx=4)

        self.next_btn = ctk.CTkButton(toolbar, text="Next ▶", command=self.next_page, width=80, height=32)
        self.next_btn.pack(side="left", padx=4)

        self.page_label = ctk.CTkLabel(toolbar, text="Page 0 / 0", width=110)
        self.page_label.pack(side="left", padx=10)

        # Zoom
        ctk.CTkButton(toolbar, text="−", command=lambda: self.set_zoom(self.zoom - 0.2), width=32, height=32).pack(side="left", padx=2)
        self.zoom_label = ctk.CTkLabel(toolbar, text="100%", width=50)
        self.zoom_label.pack(side="left")
        ctk.CTkButton(toolbar, text="+", command=lambda: self.set_zoom(self.zoom + 0.2), width=32, height=32).pack(side="left", padx=2)
        ctk.CTkButton(toolbar, text="Fit", command=self.fit_width, width=50, height=32).pack(side="left", padx=6)

        # Big action buttons (prominent as requested)
        ctk.CTkLabel(toolbar, text="   ").pack(side="left")  # spacer

        self.speak_btn = ctk.CTkButton(
            toolbar, text="🔊 Speak German", command=self.speak_german,
            width=160, height=36, fg_color=PRIMARY, hover_color=PRIMARY_HOVER, font=ctk.CTkFont(size=14, weight="bold")
        )
        self.speak_btn.pack(side="left", padx=6)

        self.translate_btn = ctk.CTkButton(
            toolbar, text="🌐 Translate + Speak EN", command=self.translate_and_speak,
            width=180, height=36, fg_color="#166534", hover_color="#14532d", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.translate_btn.pack(side="left", padx=4)

        self.stop_btn = ctk.CTkButton(
            toolbar, text="⏹ Stop", command=self.stop_speaking,
            width=80, height=36, fg_color="#334155", hover_color="#1e293b"
        )
        self.stop_btn.pack(side="left", padx=6)

        # Main area: PDF viewer + side panel
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # Left: the actual PDF page + selection
        viewer_frame = ctk.CTkFrame(main)
        viewer_frame.pack(side="left", fill="both", expand=True)

        self.canvas = ctk.CTkCanvas(viewer_frame, bg="#111827", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)

        # Bind selection
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Instructions overlay (shown when no PDF)
        self.instruction_label = ctk.CTkLabel(
            viewer_frame,
            text="Open a PDF file\n\nThen click & drag to highlight German text\n\nClick the big purple button to speak",
            font=ctk.CTkFont(size=15),
            text_color=TEXT_SECONDARY
        )
        self.instruction_label.place(relx=0.5, rely=0.5, anchor="center")

        # Right sidebar: results + controls
        side = ctk.CTkFrame(main, width=320)
        side.pack(side="right", fill="y", padx=(6, 0))

        ctk.CTkLabel(side, text="Selected Text", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 4), padx=12, anchor="w")

        self.selected_box = ctk.CTkTextbox(side, height=110, wrap="word", font=ctk.CTkFont(size=13))
        self.selected_box.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(side, text="English Translation", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(10, 4), padx=12, anchor="w")

        self.translation_box = ctk.CTkTextbox(side, height=110, wrap="word", font=ctk.CTkFont(size=13))
        self.translation_box.pack(fill="x", padx=12, pady=4)

        # Quick actions in sidebar
        ctk.CTkButton(side, text="📋 Copy German", command=self.copy_german, height=32).pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkButton(side, text="📋 Copy English", command=self.copy_english, height=32).pack(fill="x", padx=12, pady=4)

        ctk.CTkButton(side, text="Clear Selection", command=self.clear_selection, height=32,
                      fg_color="#334155", hover_color="#1e293b").pack(fill="x", padx=12, pady=(16, 8))

        # Status / tip
        self.status_label = ctk.CTkLabel(side, text="Ready", text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11))
        self.status_label.pack(pady=8, padx=12, anchor="w")

        # Footer tip
        tip = ctk.CTkLabel(self, text="Tip: Highlight → click the big purple button. Works great with Microsoft neural voices.",
                           text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11))
        tip.pack(pady=(0, 6))

    def _bind_keys(self):
        self.bind("<Left>", lambda e: self.prev_page())
        self.bind("<Right>", lambda e: self.next_page())
        self.bind("<Control-o>", lambda e: self.open_pdf())
        self.bind("<Escape>", lambda e: self.clear_selection())
        self.bind("<Control-s>", lambda e: self.speak_german())

    # ---------- PDF handling ----------
    def open_pdf(self):
        path = ctk.filedialog.askopenfilename(
            title="Open PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not path:
            return
        self.load_pdf(path)

    def load_pdf(self, path: str):
        try:
            if self.doc:
                self.doc.close()
            self.doc = fitz.open(path)
            self.current_page = 0
            self.clear_selection()
            self.render_current_page()
            self._update_page_label()
            self.instruction_label.place_forget()
            self.status_label.configure(text=f"Loaded: {Path(path).name}")
        except Exception as e:
            ctk.CTkMessagebox(title="Error", message=f"Could not open PDF:\n{e}", icon="cancel")

    def render_current_page(self):
        if not self.doc:
            return

        page = self.doc[self.current_page]
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        # Convert to PIL Image then to CTk compatible
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Keep reference
        self._current_pil_image = img
        self._current_tk_image = ImageTk.PhotoImage(img)

        # Draw on canvas
        self.canvas.delete("all")
        self.canvas.config(width=img.width, height=img.height)
        self.canvas.create_image(0, 0, anchor="nw", image=self._current_tk_image)

        # Re-extract words for this page (in PDF coordinates)
        self.page_words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, wordno)
        self.selected_words = []
        self.selection_rects = []

        # Redraw any previous selection highlights if we want persistence across zoom (optional)
        self._redraw_highlights()

    def _update_page_label(self):
        if not self.doc:
            self.page_label.configure(text="Page 0 / 0")
            return
        self.page_label.configure(text=f"Page {self.current_page + 1} / {len(self.doc)}")

    def set_zoom(self, new_zoom: float):
        self.zoom = max(0.5, min(new_zoom, 5.0))
        self.zoom_label.configure(text=f"{int(self.zoom * 100)}%")
        if self.doc:
            self.render_current_page()

    def fit_width(self):
        if not self.doc:
            return
        page = self.doc[self.current_page]
        # Rough calculation to fit the viewer width
        avail_width = max(600, self.canvas.winfo_width() - 20)
        self.zoom = avail_width / page.rect.width
        self.zoom_label.configure(text=f"{int(self.zoom * 100)}%")
        self.render_current_page()

    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.clear_selection()
            self.render_current_page()
            self._update_page_label()

    def next_page(self):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.clear_selection()
            self.render_current_page()
            self._update_page_label()

    # ---------- Selection (the heart of "simple highlight") ----------
    def _pdf_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        """Convert PDF point (at current zoom) to canvas pixel."""
        return x * self.zoom, y * self.zoom

    def _canvas_to_pdf(self, x: float, y: float) -> tuple[float, float]:
        return x / self.zoom, y / self.zoom

    def _on_mouse_down(self, event):
        if not self.page_words:
            return
        self._drag_start = (event.x, event.y)
        self.clear_selection(keep_text=False)

    def _on_mouse_drag(self, event):
        if not hasattr(self, "_drag_start") or not self.page_words:
            return

        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y

        # Remove old temp highlight rects
        for item in getattr(self, "_temp_rects", []):
            self.canvas.delete(item)
        self._temp_rects = []

        # Draw live selection rectangle
        rect = self.canvas.create_rectangle(x0, y0, x1, y1, outline=HIGHLIGHT, width=2, dash=(3, 2))
        self._temp_rects.append(rect)

    def _on_mouse_up(self, event):
        if not hasattr(self, "_drag_start") or not self.page_words:
            return

        x0c, y0c = self._drag_start
        x1c, y1c = event.x, event.y

        # Clean live rect
        for item in getattr(self, "_temp_rects", []):
            self.canvas.delete(item)
        self._temp_rects = []

        # Convert to PDF coordinates
        x0, y0 = self._canvas_to_pdf(min(x0c, x1c), min(y0c, y1c))
        x1, y1 = self._canvas_to_pdf(max(x0c, x1c), max(y0c, y1c))

        # Find words completely or partially inside the selection rect
        new_selection = []
        for i, w in enumerate(self.page_words):
            wx0, wy0, wx1, wy1, word = w[0], w[1], w[2], w[3], w[4]
            # Simple intersection test
            if not (wx1 < x0 or wx0 > x1 or wy1 < y0 or wy0 > y1):
                new_selection.append(i)

        if not new_selection:
            self.clear_selection()
            return

        # Sort in reading order (block, line, word number)
        new_selection.sort(key=lambda i: (self.page_words[i][5], self.page_words[i][6], self.page_words[i][7]))

        self.selected_words = new_selection
        self._redraw_highlights()

        # Update the selected text box
        selected_text = self._get_selected_text()
        self.selected_box.delete("1.0", "end")
        self.selected_box.insert("1.0", selected_text)

        # Auto-translate in background for convenience (but user still clicks to speak)
        threading.Thread(target=self._background_translate, args=(selected_text,), daemon=True).start()

        self.status_label.configure(text=f"{len(selected_text.split())} words selected")

    def _redraw_highlights(self):
        # Remove old highlight rectangles
        for item in self.selection_rects:
            self.canvas.delete(item)
        self.selection_rects = []

        if not self.selected_words or not self._current_pil_image:
            return

        for i in self.selected_words:
            w = self.page_words[i]
            x0, y0, x1, y1 = w[0], w[1], w[2], w[3]
            cx0, cy0 = self._pdf_to_canvas(x0, y0)
            cx1, cy1 = self._pdf_to_canvas(x1, y1)

            # Draw semi-transparent highlight (simple rectangle)
            rect = self.canvas.create_rectangle(
                cx0, cy0, cx1, cy1,
                fill=HIGHLIGHT, outline="", stipple="gray50"
            )
            self.selection_rects.append(rect)

    def _get_selected_text(self) -> str:
        if not self.selected_words:
            return ""
        words = [self.page_words[i][4] for i in self.selected_words]
        # Simple joining (good enough for most PDFs)
        return " ".join(words)

    def clear_selection(self, keep_text: bool = True):
        for item in self.selection_rects:
            self.canvas.delete(item)
        self.selection_rects = []
        self.selected_words = []

        if not keep_text:
            self.selected_box.delete("1.0", "end")
            self.translation_box.delete("1.0", "end")

    # ---------- Speak / Translate actions (the core feature) ----------
    def _background_translate(self, text: str):
        if not text.strip():
            return
        result = translate_text(text)
        self.after(0, lambda: self._show_translation(result["translated"]))

    def _show_translation(self, translated: str):
        self.translation_box.delete("1.0", "end")
        self.translation_box.insert("1.0", translated)

    def speak_german(self):
        text = self.selected_box.get("1.0", "end").strip()
        if not text:
            # Fallback to whatever is in the selection box or try current selection
            text = self._get_selected_text()
        if not text:
            self.status_label.configure(text="No text selected")
            return

        self.status_label.configure(text="Speaking German...")
        self._is_speaking = True

        def done():
            self._is_speaking = False
            self.after(0, lambda: self.status_label.configure(text="Done"))

        speak_async(text, lang="de-DE", on_done=done)

    def translate_and_speak(self):
        german = self.selected_box.get("1.0", "end").strip()
        if not german:
            german = self._get_selected_text()
        if not german:
            self.status_label.configure(text="No text selected")
            return

        self.status_label.configure(text="Translating...")

        def after_translate():
            translation = self.translation_box.get("1.0", "end").strip()
            if not translation or translation.startswith("("):
                result = translate_text(german)
                translation = result["translated"]
                self.after(0, lambda: self.translation_box.delete("1.0", "end") or self.translation_box.insert("1.0", translation))

            self.after(0, lambda: self.status_label.configure(text="Speaking English..."))
            speak_async(translation or german, lang="en-US", on_done=lambda: self.after(0, lambda: self.status_label.configure(text="Done")))

        threading.Thread(target=after_translate, daemon=True).start()

    def stop_speaking(self):
        stop_all_audio()
        self._is_speaking = False
        self.status_label.configure(text="Stopped")

    # ---------- Clipboard helpers ----------
    def copy_german(self):
        text = self.selected_box.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_label.configure(text="German copied")

    def copy_english(self):
        text = self.translation_box.get("1.0", "end").strip()
        if text and not text.startswith("("):
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_label.configure(text="English copied")

    def on_closing(self):
        if self.doc:
            self.doc.close()
        self.destroy()


# ---------- Entry point ----------
if __name__ == "__main__":
    app = GermanSpeakPDFReader()

    # Optional: open a PDF from command line
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        try:
            app.after(200, lambda: app.load_pdf(sys.argv[1]))
        except Exception:
            pass

    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
