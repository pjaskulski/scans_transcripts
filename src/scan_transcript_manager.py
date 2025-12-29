""" przeglądarka skanów i transkrypcji """
import os
import re
import json
import csv
import threading
import hashlib
from datetime import datetime
from pathlib import Path
import xml.sax.saxutils as saxutils
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageOps, ImageEnhance
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.widgets.scrolled import ScrolledFrame
from ttkbootstrap.widgets.tableview import Tableview
from docx import Document
from dotenv import load_dotenv
from google import genai
from google.genai import types
from gtts import gTTS
from just_playback import Playback


# ------------------------------- CLASS ----------------------------------------
class ToolTip:
    """ klasa tworząca dymek z podpowiedzią z opóźnieniem (500ms) """
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self.id = None  # ID planowanego zdarzenia .after()

        self.widget.tooltip = self

        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.unschedule)
        self.widget.bind("<ButtonPress>", self.unschedule) # ukrywanie po kliknięciu

    def update_text(self, new_text):
        """ metoda do zmiany treści podpowiedzi po zmianie języka """
        self.text = new_text

    def schedule(self, event=None):
        """ planowanie wyświetlenia dymka po upływie self.delay """
        self.unschedule()
        self.id = self.widget.after(self.delay, self.show_tip)

    def unschedule(self, event=None):
        """ anuluje planowanie i usuwa okno dymka """
        if self.id:
            id_to_cancel = self.id
            self.id = None
            self.widget.after_cancel(id_to_cancel)

        # zamkanie okna jeśli istnieje
        if self.tip_window:
            tw = self.tip_window
            self.tip_window = None
            tw.destroy()

    def show_tip(self):
        """ wyświetlanie okna z dymkiem i podpowiedzią """
        if not self.text:
            return

        # obliczanie pozycji (nad widgetem)
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True) # zawsze nad oknem głównym

        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe1", relief=tk.SOLID, borderwidth=1,
                         font=("Segoe UI", "9", "normal"), padx=8, pady=4)
        label.pack()


class ManuscriptEditor:
    """ główna klasa aplikacji """
    def __init__(self, root):
        self.current_lang = "PL" # domyślny język
        self.current_tts_lang_code = "pl" # domyślny język audio
        self.localization = {} # słownik wersji językowych
        self.local_file = "localization.json"
        self.languages = []
        self.load_lang()

        self.api_key = ""
        self.default_prompt = ""
        self.prompt_text = ""
        self.prompt_filename_var = tk.StringVar(value="Brak (wybierz plik)")
        self.current_folder_var = tk.StringVar(value="Nie wybrano katalogu")
        self.current_prompt_path = None

        self.config_file = "config.json"
        self.font_family = "Consolas"
        self.font_size = 12

        self.load_config()
        self.t = self.localization[self.current_lang]
        self._init_environment()

        self.root = root
        self.root.title(self.t["title"])
        self.root.geometry("1600x900")

        self.MODEL_PRICES = {
            "gemini-3-pro-preview": (2.0, 12.0),
            "gemini-3-flash-preview": (0.5, 3.0),
            "gemini-3-pro-image-preview": (2.0, 12.0),
            "gemini-flash-latest": (0.3, 2.5)
        }

        # języki TTS
        self.tts_languages = {
            self.t["tts_pl"]: "pl",
            self.t["tts_la"]: "la",
            self.t["tts_en"]: "en",
            self.t["tts_de"]: "de",
            self.t["tts_fr"]: "fr",
            self.t["tts_es"]: "es",
            self.t["tts_pt"]: "pt",
            self.t["tts_ru"]: "ru"
        }

        self.file_pairs = []
        self.current_index = 0
        self.original_image = None
        self.processed_image = None
        self.tk_image = None
        self.scale = 1.0
        self.img_x = 0
        self.img_y = 0
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        self.active_filter = "normal"

        self.is_transcribing = False
        self.btn_ai = None

        self.playback = Playback()

        self.is_reading_audio = False

        self.batch_log_label = None
        self.batch_vars = None
        self.batch_progress = None

        self.last_entities = [] # zapamiętana lista nazw własnych dla bieżącej strony

        # główny kontener
        self.paned = ttk.Panedwindow(root, orient=HORIZONTAL)
        self.paned.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # lewy panel (na obraz)
        self.left_frame = ttk.Frame(self.paned)
        self.paned.add(self.left_frame, weight=3)

        # ramka na canvas z obramowaniem
        self.canvas_frame = ttk.Labelframe(self.left_frame, text=self.t["frame_scan"], bootstyle="info")
        self.canvas_frame.pack(fill=BOTH, expand=True)

        # canvas
        self.canvas = tk.Canvas(self.canvas_frame,
                                bg="#2b2b2b",
                                highlightthickness=0,
                                cursor="fleur")
        self.canvas.pack(fill=BOTH, expand=True, padx=2, pady=2)

        # zdarzenia myszy
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)
        self.canvas.bind("<Button-3>", self.show_magnifier)
        self.canvas.bind("<B3-Motion>", self.update_magnifier)
        self.canvas.bind("<ButtonRelease-3>", self.hide_magnifier)

        self.magnifier_win = None
        self.mag_label = None
        self.tk_mag_img = None

        self.dragging_box_tag = None
        self.box_to_data_map = {}  # mapowanie ramek na skanie
        self.resizing_box_tag = None

        self.cursor_resizing = "bottom_right_corner"
        self.cursor_move = "fleur"
        if os.name == 'nt': # Windows
            self.cursor_resizing = "sizenwse" #?
            self.cursor_move = "fleur"

        self.active_box_tag = None
        self.box_action = None

        # pasek statusu pod obrazem
        self.image_tools = ttk.Frame(self.left_frame)
        self.image_tools.pack(fill=X, pady=5)

        # lewa strona paska (instrukcja + Zoom info)
        left_tools = ttk.Frame(self.image_tools)
        left_tools.pack(side=LEFT)

        self.zoom_label = ttk.Label(left_tools, text="Zoom: 100%", font=("Segoe UI", 9, "bold"))
        self.zoom_label.pack(side=LEFT, pady=5)
        self.lbl_left_tools = ttk.Label(left_tools,
                  text=self.t["left_tools"],
                  font=("Segoe UI", 8), bootstyle="secondary")
        self.lbl_left_tools.pack(side=LEFT, pady=5, padx=10)

        # prawa strona paska
        tools_frame = ttk.Frame(self.image_tools)
        tools_frame.pack(side=RIGHT)

        self.btn_fit = ttk.Button(tools_frame, text="<->", command=self.fit_to_width,
                   bootstyle="success-outline", padding=2)
        self.btn_fit.pack(side=LEFT, padx=(5,5))

        self.lbl_filters = ttk.Label(tools_frame, text=self.t["lbl_filters"], font=("Segoe UI", 8))
        self.lbl_filters.pack(side=LEFT)
        self.btn_reset = ttk.Button(tools_frame, text=self.t["filter_reset"], command=lambda: self.apply_filter("normal"),
                   bootstyle="outline-secondary", padding=2)
        self.btn_reset.pack(side=LEFT, padx=1)
        self.btn_contrast = ttk.Button(tools_frame, text=self.t["filter_contrast"], command=lambda: self.apply_filter("contrast"),
                   bootstyle="outline-info", padding=2)
        self.btn_contrast.pack(side=LEFT, padx=1)
        self.btn_inverse = ttk.Button(tools_frame, text=self.t["filter_invert"], command=lambda: self.apply_filter("invert"),
                   bootstyle="outline-dark", padding=2)
        self.btn_inverse.pack(side=LEFT, padx=(1,5))

        # prawy panel (na edytor transkrypcji)
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame, weight=1)

        # pasek ścieżki do katalogu ze skanami
        self.folder_status_frame = ttk.Frame(self.right_frame)
        self.folder_status_frame.pack(fill=X, padx=5, pady=(0, 5))

        self.lbl_folder_status = ttk.Label(self.folder_status_frame, text=self.t["folder_path"],
                  font=("Segoe UI", 8, "bold"))
        self.lbl_folder_status.pack(side=LEFT)

        # etykieta ze ścieżką
        ttk.Label(self.folder_status_frame, textvariable=self.current_folder_var,
                  font=("Segoe UI", 8), bootstyle="dark").pack(side=LEFT, padx=5)

        # przycisk zmiany folderu ze skanami
        self.btn_folder_change = ttk.Button(self.folder_status_frame,
                                       text=self.t["btn_folder_change"],
                                       command=self.select_folder,
                                       bootstyle="link-secondary",
                                       cursor="hand2", padding=0)
        self.btn_folder_change.pack(side=RIGHT)

        # ramka na tekst
        self.editor_frame = ttk.Labelframe(self.right_frame,
                                           text=self.t["frame_trans"],
                                           bootstyle="primary")
        self.editor_frame.pack(fill=BOTH, expand=True, padx=(5,0))

        # wiersz 1: nawigacja i wielkość fontu
        self.header_row1 = ttk.Frame(self.editor_frame)
        self.header_row1.pack(fill=X, padx=5, pady=2)

        self.file_info_var = tk.StringVar(value=self.t["file_info"])
        self.lbl_file_info = ttk.Label(self.header_row1, textvariable=self.file_info_var,
                  font=("Segoe UI", 10, "bold"), bootstyle="inverse-light")
        self.lbl_file_info.pack(side=LEFT, fill=X, expand=True)

        # wyszukiwanie w tekście transkrypcji
        search_frame = ttk.Frame(self.header_row1)
        search_frame.pack(side=LEFT, padx=20)

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var,
                                      width=15, font=("Segoe UI", 9))
        self.search_entry.pack(side=LEFT, padx=2)
        self.search_entry.bind("<Return>", lambda e: self.perform_search())

        self.btn_search = ttk.Button(search_frame, text="→", command=self.perform_search,
                   bootstyle="outline-info", padding=0)
        self.btn_search.pack(side=LEFT)
        self.btn_cancelsearch = ttk.Button(search_frame, text="×", command=self.clear_search,
                   bootstyle="outline-info", padding=0)
        self.btn_cancelsearch.pack(side=LEFT)

        # font pola tekstowego z transkrypcją
        font_tools = ttk.Frame(self.header_row1)
        font_tools.pack(side=RIGHT)
        self.btn_smfont = ttk.Button(font_tools, text="A-", command=lambda: self.change_font_size(-1),
                   bootstyle="outline-secondary", width=3, padding=2)
        self.btn_smfont.pack(side=LEFT, padx=2)
        self.btn_bgfont = ttk.Button(font_tools, text="A+", command=lambda: self.change_font_size(1),
                   bootstyle="outline-secondary", width=3, padding=2)
        self.btn_bgfont.pack(side=LEFT, padx=2)

        self.lang_sel = ttk.Combobox(font_tools, values=self.languages, width=5,
                                     state="readonly")
        self.lang_sel.set(self.current_lang)
        self.lang_sel.bind("<<ComboboxSelected>>", self.change_app_language)
        self.lang_sel.pack(side=LEFT, padx=5)

        # wiersz 2: narzędzia AI (NER/BOX) i TTS (lektor)
        self.header_row2 = ttk.Frame(self.editor_frame)
        self.header_row2.pack(fill=X, padx=5, pady=2)

        # lewa strona wiersza 2: analiza treści
        ai_tools = ttk.Frame(self.header_row2)
        ai_tools.pack(side=LEFT)

        self.btn_ner = ttk.Button(ai_tools, text="NER", command=self.start_ner_analysis,
                                  bootstyle="success-outline", width=3, padding=2)
        self.btn_ner.pack(side=LEFT, padx=2)

        self.btn_box = ttk.Button(ai_tools, text="BOX", command=self.start_coordinates_analysis,
                                  bootstyle="success-outline", width=4, padding=2, state="disabled")
        self.btn_box.pack(side=LEFT, padx=2)

        self.btn_cls = ttk.Button(ai_tools, text="CLS", command=self.clear_all_annotations,
                                  bootstyle="success-outline", width=4, padding=2, state="disabled")
        self.btn_cls.pack(side=LEFT, padx=2)

        self.btn_leg = ttk.Button(ai_tools, text="LEG", command=self.show_legend,
                                  bootstyle="info-outline", width=4, padding=2)
        self.btn_leg.pack(side=LEFT, padx=2)

        self.btn_csv = ttk.Button(ai_tools, text="CSV", command=self.export_ner_to_csv,
                                  bootstyle="success-outline", width=4, padding=2)
        self.btn_csv.pack(side=LEFT, padx=2)

        self.btn_log = ttk.Button(ai_tools, text="LOG", command=self.show_usage_log,
                                  bootstyle="success-outline", width=4, padding=2)
        self.btn_log.pack(side=LEFT, padx=2)

        # prawa strona wiersza 2: lektor (TTS)
        tts_tools = ttk.Frame(self.header_row2)
        tts_tools.pack(side=RIGHT)

        self.lang_combobox = ttk.Combobox(tts_tools, values=list(self.tts_languages.keys()),
                                          state="readonly", width=10, bootstyle="info")
        # ustawienie wartości początkowej na podstawie kodu (np. 'pl' -> 'Polski')
        initial_lang_name = [k for k, v in self.tts_languages.items() if v == self.current_tts_lang_code]
        if initial_lang_name:
            self.lang_combobox.set(initial_lang_name[0])
        else:
            self.lang_combobox.set(self.t["tts_pl"])

        self.lang_combobox.bind("<<ComboboxSelected>>", self.change_tts_language)
        self.lang_combobox.pack(side=LEFT, padx=2)

        self.btn_speak = ttk.Button(tts_tools, text=">", command=self.read_text_aloud,
                                    bootstyle="info-outline", width=3, padding=2)
        self.btn_speak.pack(side=LEFT, padx=2)

        self.btn_pause = ttk.Button(tts_tools, text="||", command=self.pause_reading,
                                    bootstyle="warning-outline", width=3, padding=2, state="disabled")
        self.btn_pause.pack(side=LEFT, padx=2)

        self.btn_stop = ttk.Button(tts_tools, text="■", command=self.stop_reading,
                                   bootstyle="secondary-outline", width=3, padding=2, state="disabled")
        self.btn_stop.pack(side=LEFT, padx=2)

        ttk.Separator(self.editor_frame, orient=HORIZONTAL).pack(fill=X, padx=5, pady=2)

        # pole tekstowe z paskiem przewijania
        self.text_scroll = ttk.Scrollbar(self.editor_frame, orient=VERTICAL)
        self.text_area = tk.Text(self.editor_frame,
                                 font=(self.font_family, self.font_size),
                                 wrap=WORD, undo=True,
                                 bg="#333333", fg="white", insertbackground="white",
                                 yscrollcommand=self.text_scroll.set, bd=0, width=1)

        self.text_scroll.config(command=self.text_area.yview)
        self.text_scroll.pack(side=RIGHT, fill=Y)
        self.text_area.pack(side=LEFT, fill=BOTH, expand=True, padx=5, pady=5)

        # konfiguracja kolorów dla różnych rodzajów nazw własnych (NER)
        self.category_colors = {
            "PERS": "#f4d65f",  # Jasny żółty (Osoby)
            "LOC": "#C1FFC1",   # Jasny zielony (Miejsca)
            "ORG": "#D1EAFF"    # Jasny niebieski (Organizacje)
        }

        # konfiguracja kolorów tagów w edytorze na podstawie słownika
        for category, color in self.category_colors.items():
            self.text_area.tag_configure(category, background=color, foreground="black")

        # konfiguracja dla wyszukiwania w tekście transkrypcji
        self.text_area.tag_configure("search_highlight", background="#00ffff", foreground="black")

        # pasek narzędzi
        self.toolbar = ttk.Frame(self.right_frame, padding=(0, 10, 0, 5))
        self.toolbar.pack(fill=X, padx=(5,0))

        # przyciski
        self.btn_first = ttk.Button(self.toolbar,
                   text="|<",
                   command=self.first_file,
                   bootstyle="outline-secondary")
        self.btn_first.pack(side=LEFT, fill=X, expand=True, padx=2)

        self.btn_prev = ttk.Button(self.toolbar,
                   text="<<",
                   command=self.prev_file,
                   bootstyle="outline-secondary")
        self.btn_prev.pack(side=LEFT, fill=X, expand=True, padx=2)

        self.btn_save = ttk.Button(self.toolbar,
                   text=self.t["btn_save"],
                   command=self.save_current_text,
                   bootstyle="success")
        self.btn_save.pack(side=LEFT, fill=X, expand=True, padx=5)

        # Gemini
        frame_ai = ttk.Frame(self.toolbar)
        frame_ai.pack(side=LEFT, fill=X, expand=True)

        self.btn_ai = ttk.Button(frame_ai,
                                 text="Gemini",
                                 command=self.start_ai_transcription,
                                 bootstyle="danger")
        self.btn_ai.pack(side=LEFT, fill=X, expand=True, padx=2)

        # Gemini seria
        self.btn_seria = ttk.Button(frame_ai,
                                    text=self.t["btn_batch"],
                                    command=self.open_batch_dialog,
                                    bootstyle="danger")
        self.btn_seria.pack(side=LEFT, fill=X, expand=True, padx=2)

        # zapis wyników
        self.btn_txt = ttk.Button(self.toolbar,
                   text="TXT",
                   command=self.export_all_data,
                   bootstyle="info")
        self.btn_txt.pack(side=LEFT, fill=X, expand=True, padx=5)

        self.btn_docx = ttk.Button(self.toolbar,
                   text="DOCX",
                   command=self.export_all_data_docx,
                   bootstyle="info")
        self.btn_docx.pack(side=LEFT, fill=X, expand=True, padx=5)

        self.btn_tei = ttk.Button(self.toolbar,
                   text="TEI",
                   command=self.export_to_tei_xml,
                   bootstyle="info")
        self.btn_tei.pack(side=LEFT, fill=X, expand=True, padx=5)

        self.btn_last = ttk.Button(self.toolbar,
                   text=">|",
                   command=self.last_file,
                   bootstyle="outline-secondary")
        self.btn_last.pack(side=RIGHT, fill=X, expand=True, padx=2)


        self.btn_next = ttk.Button(self.toolbar,
                   text=">>",
                   command=self.next_file,
                   bootstyle="outline-secondary")
        self.btn_next.pack(side=RIGHT, fill=X, expand=True, padx=2)


        # pasek stanu promptu
        self.prompt_status_frame = ttk.Frame(self.right_frame, bootstyle="light")
        self.prompt_status_frame.pack(fill=X, padx=(5,0), pady=(0, 5))

        # etykieta z nazwą bieżącego promptu (pliku z promptem)
        ttk.Label(self.prompt_status_frame, text="Prompt:",
                  font=("Segoe UI", 8, "bold")).pack(side=LEFT)

        ttk.Label(self.prompt_status_frame, textvariable=self.prompt_filename_var,
                  font=("Segoe UI", 8), bootstyle="dark").pack(side=LEFT, padx=(5,5), pady=2)

        # przycisk zmiany promptu
        self.btn_prompt_change = ttk.Button(self.prompt_status_frame, text=self.t["btn_prompt"], command=self.select_prompt_file,
                   bootstyle="link-secondary", cursor="hand2", padding=0)
        self.btn_prompt_change.pack(side=RIGHT, padx=5)

        # przycisk edycji promptu
        self.btn_edit_prompt = ttk.Button(self.prompt_status_frame, text=self.t["btn_edit_prompt"],
                                        command=self.edit_current_prompt,
                                        bootstyle="link-info", cursor="hand2", padding=0)
        self.btn_edit_prompt.pack(side=RIGHT, padx=5)

        # skróty klawiszowe
        self.root.bind("<Control-s>", lambda e: self.save_current_text())
        self.root.bind("<Alt-Left>", lambda e: self.prev_file())
        self.root.bind("<Alt-Right>", lambda e: self.next_file())
        self.root.bind("<Control-q>", lambda e: self.on_close())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # pasek postępu (domyślnie ukryty)
        self.progress_bar = ttk.Progressbar(self.right_frame,
                                            mode='indeterminate',
                                            bootstyle="success-striped")

        # konfiguracja tagu aktywnej linii w edytorze transkrypcji
        self.text_area.tag_configure("active_line", background="#e8e8e8", foreground="black")

        # przesunięcie tagu aktywnej linii na sam dół hierarchii
        self.text_area.tag_lower("active_line")

        # powiązania zdarzeń aktualizujących podświetlenie linii
        self.text_area.bind("<KeyRelease>", self.update_active_line_highlight)
        self.text_area.bind("<ButtonRelease-1>", self.update_active_line_highlight)

        # tooltips
        self.btn_fit_tooltip = ToolTip(self.btn_fit, self.t["tt_btn_fit"])
        self.btn_ner_tooltip = ToolTip(self.btn_ner, self.t["tt_btn_ner"])
        self.btn_box_tooltip = ToolTip(self.btn_box, self.t["tt_btn_box"])
        self.btn_cls_tooltip = ToolTip(self.btn_cls, self.t["tt_btn_cls"])
        self.btn_leg_tooltip = ToolTip(self.btn_leg, self.t["tt_btn_leg"])
        self.btn_csv_tooltip = ToolTip(self.btn_csv, self.t["tt_btn_csv"])
        self.btn_speak_tooltip = ToolTip(self.btn_speak, self.t["tt_btn_speak"])
        self.btn_stop_tooltip = ToolTip(self.btn_stop, self.t["tt_btn_stop"])
        self.btn_pause_tooltip = ToolTip(self.btn_pause, self.t["tt_btn_pause"])

        self.btn_ai_tooltip = ToolTip(self.btn_ai, self.t["tt_btn_ai"])
        self.btn_seria_tooltip = ToolTip(self.btn_seria, self.t["tt_btn_seria"])
        self.btn_txt_tooltip = ToolTip(self.btn_txt, self.t["tt_btn_txt"])
        self.btn_docx_tooltip = ToolTip(self.btn_docx, self.t["tt_btn_docx"])
        self.btn_tei_tooltip = ToolTip(self.btn_tei, self.t["tt_btn_tei"])
        self.btn_save_tooltip = ToolTip(self.btn_save, self.t["tt_btn_save"])
        self.btn_first_tooltip = ToolTip(self.btn_first, self.t["tt_btn_first"])
        self.btn_last_tooltip = ToolTip(self.btn_last, self.t["tt_btn_last"])
        self.btn_prev_tooltip = ToolTip(self.btn_prev, self.t["tt_btn_prev"])
        self.btn_next_tooltip = ToolTip(self.btn_next, self.t["tt_btn_next"])
        self.btn_bgfont_tooltip = ToolTip(self.btn_bgfont, self.t["tt_btn_bgfont"])
        self.btn_smfont_tooltip = ToolTip(self.btn_smfont, self.t["tt_btn_smfont"])
        self.btn_search_tooltip = ToolTip(self.btn_search, self.t["tt_btn_search"])
        self.btn_cancelsearch_tooltip = ToolTip(self.btn_cancelsearch, self.t["tt_btn_cancelsearch"])
        self.lang_combobox_tooltip = ToolTip(self.lang_combobox, self.t["tt_lang_combobox"])

        self.select_folder()


    def export_to_tei_xml(self):
        """ eksportuje transkrypcje z bieżącego folderu do formatu
            TEI-XML z tagowaniem NER (jeżeli jest)
        """
        if not self.file_pairs:
            return

        target_path = filedialog.asksaveasfilename(
            title=self.t["filedialog_tei_title"],
            defaultextension=".xml",
            filetypes=[(self.t["filetype_xml"], "*.xml")],
            parent=self.root
        )
        if not target_path:
            return

        try:
            tei_content = []

            # prosty nagłówek TEI
            tei_content.append('<?xml version="1.0" encoding="UTF-8"?>')
            tei_content.append('<TEI xmlns="http://www.tei-c.org/ns/1.0">')
            tei_content.append('  <teiHeader>')
            tei_content.append('    <fileDesc>')
            tei_content.append('      <titleStmt><title>Eksport z ScansAndTranscriptions</title></titleStmt>')
            tei_content.append('      <publicationStmt><p>Wygenerowano automatycznie</p></publicationStmt>')
            tei_content.append('      <sourceDesc><p>Transkrypcje skanów</p></sourceDesc>')
            tei_content.append('    </fileDesc>')
            tei_content.append('  </teiHeader>')
            tei_content.append('  <text>')
            tei_content.append('    <body>')

            for pair in self.file_pairs:
                if not os.path.exists(pair['txt']):
                    continue

                # wczytanie tekstu i metadanych NER
                with open(pair['txt'], 'r', encoding='utf-8') as f:
                    raw_text = f.read()

                entities = {}
                json_path = os.path.splitext(pair['txt'])[0] + ".json"
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        entities = json.load(f).get("entities", {})

                # przygotowanie tekstu: sklejanie wierszy i słów
                processed_text = self._prepare_text_for_tei(raw_text)

                # tagowanie nazw własnych
                tagged_text = self._tag_entities_tei(processed_text, entities)

                # dodanie strony jako akapitu lub sekcji
                tei_content.append(f'      <div type="page" n="{pair["name"]}">')
                for paragraph in tagged_text.split('\n\n'):
                    if paragraph.strip():
                        tei_content.append(f'        <p>{paragraph.strip()}</p>')
                tei_content.append('      </div>')

            tei_content.append('    </body>')
            tei_content.append('  </text>')
            tei_content.append('</TEI>')

            with open(target_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(tei_content))

            messagebox.showinfo(self.t["msg_csv_ok_title"],
                                self.t["msg_xml_info_text"] + f":\n{os.path.basename(target_path)}")

        except Exception as e:
            messagebox.showerror(self.t["msg_xml_error_title"],
                                 self.t["msg_xml_error_text"] + f": {e}")


    def _prepare_text_for_tei(self, text):
        """ łączenie podzielonych słów i wierszy w logiczne akapity """
        lines = text.splitlines()
        joined_text = ""
        for line in lines:
            line = line.strip()
            if not line:
                joined_text += "\n\n" # nowy akapit
            elif joined_text.endswith("-"):
                joined_text = joined_text[:-1] + line
            else:
                joined_text += (" " if joined_text and not joined_text.endswith("\n\n") else "") + line
        return joined_text


    def _tag_entities_tei(self, text, entities):
        """ otaczanie nazw własnych tagami TEI (persName, placeName, orgName) """
        # mapowanie kategorii na tagi TEI
        tag_map = {
            "PERS": "persName",
            "LOC": "placeName",# LOC jest nieco byt ogólne dla placeName, mogą tu być kraje, państwa itp.
            "ORG": "orgName"
        }

        # znaki specjalne XML (&, <, >)
        escaped_text = saxutils.escape(text)

        # lista wszystkich nazw do zastąpienia, sortowana od najdłuższych
        # (aby uniknąć błędnego tagowania fragmentów nazw, np. "Jan" w "Jan Kowalski")
        all_names = []
        for cat, names in entities.items():
            if cat in tag_map:
                for name in names:
                    all_names.append((name, tag_map[cat]))

        all_names.sort(key=lambda x: len(x[0]), reverse=True)

        for name, tag in all_names:
            escaped_name = saxutils.escape(name)
            # regex z word boundary (\b), aby nie tagować środków innych słów
            pattern = re.compile(re.escape(escaped_name), re.IGNORECASE)
            escaped_text = pattern.sub(f'<{tag}>{escaped_name}</tag>', escaped_text)

        # tag zamknięcia
        for _, tag in all_names:
            escaped_text = escaped_text.replace('</tag>', f'</{tag}>')

        return escaped_text


    def change_app_language(self, event):
        """ zmiana języka interfejsu użytkownika """
        tmp = self.lang_sel.get()
        if tmp != self.current_lang:
            self.current_lang = tmp
            self.t = self.localization[self.current_lang]
            self.save_config()
            self.update_ui_text()
        self.lang_sel.selection_clear()


    def update_ui_text(self):
        """odświeżnie tekstów we wszystkich widżetach po zmianie języka"""

        self.tts_languages = {
            self.t["tts_pl"]: "pl",
            self.t["tts_la"]: "la",
            self.t["tts_en"]: "en",
            self.t["tts_de"]: "de",
            self.t["tts_fr"]: "fr",
            self.t["tts_es"]: "es",
            self.t["tts_pt"]: "pt",
            self.t["tts_ru"]: "ru"
        }

        self.root.title(self.t["title"])

        self.lbl_left_tools.config(text=self.t["left_tools"])

        self.canvas_frame.config(text=self.t["frame_scan"])
        self.editor_frame.config(text=self.t["frame_trans"])

        self.lbl_filters.config(text=self.t["lbl_filters"])
        self.btn_reset.config(text=self.t["filter_reset"])
        self.btn_contrast.config(text=self.t["filter_contrast"])
        self.btn_inverse.config(text=self.t["filter_invert"])
        self.btn_save.config(text=self.t["btn_save"])
        self.lbl_folder_status.config(text=self.t["folder_path"])
        self.btn_folder_change.config(text=self.t["btn_folder_change"])
        self.btn_seria.config(text=self.t["btn_batch"])
        self.btn_prompt_change.config(text=self.t["btn_prompt"])
        self.btn_edit_prompt.config(text=self.t["btn_edit_prompt"])

        self.refresh_tooltips()


    def refresh_tooltips(self):
        """ odświeżanie podpowiedzi w aktualnym języku interfejsu """
        self.btn_fit_tooltip.update_text(self.t["tt_btn_fit"])
        self.btn_ner_tooltip.update_text(self.t["tt_btn_ner"])
        self.btn_box_tooltip.update_text(self.t["tt_btn_box"])
        self.btn_cls_tooltip.update_text(self.t["tt_btn_cls"])
        self.btn_leg_tooltip.update_text(self.t["tt_btn_leg"])
        self.btn_csv_tooltip.update_text(self.t["tt_btn_csv"])
        self.btn_speak_tooltip.update_text(self.t["tt_btn_speak"])
        self.btn_stop_tooltip.update_text(self.t["tt_btn_stop"])
        self.btn_pause_tooltip.update_text(self.t["tt_btn_pause"])

        self.btn_ai_tooltip.update_text(self.t["tt_btn_ai"])
        self.btn_seria_tooltip.update_text(self.t["tt_btn_seria"])
        self.btn_txt_tooltip.update_text(self.t["tt_btn_txt"])
        self.btn_docx_tooltip.update_text(self.t["tt_btn_docx"])
        self.btn_save_tooltip.update_text(self.t["tt_btn_save"])
        self.btn_first_tooltip.update_text(self.t["tt_btn_first"])
        self.btn_last_tooltip.update_text(self.t["tt_btn_last"])
        self.btn_prev_tooltip.update_text(self.t["tt_btn_prev"])
        self.btn_next_tooltip.update_text(self.t["tt_btn_next"])
        self.btn_bgfont_tooltip.update_text(self.t["tt_btn_bgfont"])
        self.btn_smfont_tooltip.update_text(self.t["tt_btn_smfont"])
        self.btn_search_tooltip.update_text(self.t["tt_btn_search"])
        self.btn_cancelsearch_tooltip.update_text(self.t["tt_btn_cancelsearch"])
        self.lang_combobox_tooltip.update_text(self.t["tt_lang_combobox"])


    def show_usage_log(self):
        """ wyświetlenie okna z historią zużycia tokenów i podsumowaniem kosztów"""
        if not self.file_pairs:
            return

        folder = os.path.dirname(self.file_pairs[0]['img'])
        log_path = os.path.join(folder, "tokens.log")

        if not os.path.exists(log_path):
            messagebox.showinfo("Log", self.t["msg_log_file"])
            return

        log_win = tk.Toplevel(self.root)
        log_win.title(self.t["log_win_title"])
        log_win.geometry("900x500")

        # wykorzystanie elementu Tableview
        columns = [
            {"text": self.t["table_data"], "stretch": True},
            {"text": self.t["table_model"], "stretch": True},
            {"text": self.t["table_input"], "stretch": False},
            {"text": self.t["table_output"], "stretch": False},
            {"text": self.t["table_cost"], "stretch": False}
        ]

        row_data = []
        total_cost = 0.0

        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(";")
                if len(parts) == 5:
                    row_data.append(tuple(parts))
                    total_cost += float(parts[4])

        tv = Tableview(log_win, coldata=columns, rowdata=row_data, paginated=True,
                       searchable=True, bootstyle="info")
        tv.pack(fill=BOTH, expand=True, padx=10, pady=10)

        footer = ttk.Label(log_win, text=self.t["total_cost"] + f": ${total_cost:.4f}",
                           font=("Segoe UI", 10, "bold"))
        footer.pack(pady=10)


    def _log_api_usage(self, model_name, usage_metadata):
        """ obliczanie kosztu użycia API i zapis w logu w bieżącym folderze ze skanami"""
        if not self.file_pairs or not usage_metadata:
            return

        folder = os.path.dirname(self.file_pairs[0]['img'])
        log_path = os.path.join(folder, "tokens.log")

        in_tokens = usage_metadata.prompt_token_count
        out_tokens = usage_metadata.candidates_token_count

        prices = self.MODEL_PRICES.get(model_name, (0.0, 0.0))
        cost = (in_tokens / 1_000_000 * prices[0]) + (out_tokens / 1_000_000 * prices[1])

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"{now};{model_name};{in_tokens};{out_tokens};{cost:.6f}\n"

        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            print(self.t["msg_log_error"] + f": {e}")


    def export_ner_to_csv(self):
        """ eksport NER do CSV z mianownikiem i kontekstem z całego katalogu """
        if not self.file_pairs:
            return

        target_path = filedialog.asksaveasfilename(
            title=self.t["file_dialog_csv"],
            defaultextension=".csv",
            filetypes=[(self.t["file_type_csv"], "*.csv")],
            parent=self.root
        )
        if not target_path:
            return

        all_data_to_process = []
        unique_names = set()

        for pair in self.file_pairs:
            json_path = os.path.splitext(pair['txt'])[0] + ".json"
            txt_path = pair['txt']

            if os.path.exists(json_path) and os.path.exists(txt_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        entities = json.load(f).get("entities", {})

                    for cat, names in entities.items():
                        for name in names:
                            all_data_to_process.append({
                                'orig': name,
                                'cat': cat,
                                'file': os.path.basename(pair['img']),
                            })
                            unique_names.add(name)
                except Exception as e:
                    print(self.t["msg_csv_error"] + f" {pair['name']}: {e}")

        if not all_data_to_process:
            messagebox.showinfo(self.t["msg_csv_info_title"], self.t["msg_csv_info_text"])
            return

        self.btn_ai.config(state="disabled")
        threading.Thread(target=self._ner_export_worker,
                         args=(list(unique_names), all_data_to_process, target_path),
                         daemon=True).start()


    def _ner_export_worker(self, names_list, full_records, target_path):
        """ wątek AI: mianownik + zapis 5 kolumn do CSV """
        try:
            nominative_map = {}
            client = genai.Client(api_key=self.api_key)

            # przetwarzanie paczek nazw przez Gemini
            for i in range(0, len(names_list), 50):
                batch = names_list[i:i+50]
                prompt = (
                    "Dla podanej listy nazw własnych z dokumentów historycznych, "
                    "podaj ich formę w mianowniku, nie zmieniaj rodzaju nazw (męski, żeński, nijaki). "
                    "Zwróć WYŁĄCZNIE czysty JSON: {\"oryginał\": \"mianownik\", ...}. "
                    f"Lista: {', '.join(batch)}"
                )

                config = types.GenerateContentConfig(
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                )

                model="gemini-flash-latest" # lub gemini-3-flash-preview

                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )

                if response.usage_metadata:
                    self._log_api_usage(model, response.usage_metadata)

                if response.text:
                    json_str = response.text.replace("```json", "").replace("```", "").strip()
                    nominative_map.update(json.loads(json_str))

            # zapis do CSV (separator średnik)
            with open(target_path, 'w', encoding='utf-8', newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                writer.writerow([self.t["csv_column_orgname"],
                                 self.t["csv_column_nominative"],
                                 self.t["csv_column_category"],
                                 self.t["csv_column_file"]])

                for rec in full_records:
                    base_name = nominative_map.get(rec['orig'], rec['orig'])
                    writer.writerow([rec['orig'], base_name, rec['cat'], rec['file']])

            self.root.after(0, lambda: messagebox.showinfo(self.t["msg_csv_ok_title"],
                                                           self.t["msg_csv_ok_text"] + f":\n{target_path}"))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror(self.t["msg_csv_error_text"], str(e)))
        finally:
            self.root.after(0, lambda: self.btn_ai.config(state="normal", text="Gemini"))


    def update_active_line_highlight(self, event=None):
        """ podświetlanie linii, w której aktualnie znajduje się kursor """
        # usuwanie starego podświetlenia
        self.text_area.tag_remove("active_line", "1.0", tk.END)

        # pobieranie początku i końca bieżącej linii
        line_start = self.text_area.index("insert linestart")
        line_end = self.text_area.index("insert lineend + 1c")

        # nakładanie tagu
        self.text_area.tag_add("active_line", line_start, line_end)

        # active_line jest zawsze pod kategoriami NER
        for tag in ["PERS", "LOC", "ORG"]:
            self.text_area.tag_raise(tag, "active_line")


    def show_legend(self):
        """ wyświetlanie małego okna z opisem kolorów NER """
        leg_win = tk.Toplevel(self.root)
        leg_win.title(self.t["leg_win_title"])
        leg_win.geometry("550x240")
        leg_win.resizable(False, False)
        leg_win.transient(self.root)

        # główny kontener z marginesem
        container = ttk.Frame(leg_win, padding=15)
        container.pack(fill=BOTH, expand=True)

        ttk.Label(container, text=self.t["label_ner_category"],
                  font=("Segoe UI", 10, "bold")).pack(pady=(0, 10))

        # definicje opisów dla kategorii
        descriptions = {
            "PERS": self.t["desc_ner_pers"],
            "LOC": self.t["desc_ner_loc"],
            "ORG": self.t["desc_ner_org"]
        }

        for cat, color in self.category_colors.items():
            row = ttk.Frame(container)
            row.pack(fill=X, pady=3)

            cv = tk.Canvas(row, width=18, height=18, highlightthickness=0, bd=0)
            cv.pack(side=LEFT, padx=(0, 10))
            cv.create_rectangle(0, 0, 18, 18, fill=color, outline="gray")

            # nazwa kategorii i opis
            ttk.Label(row, text=f"{cat}: ", font=("Segoe UI", 9, "bold")).pack(side=LEFT)
            ttk.Label(row, text=descriptions.get(cat, ""), font=("Segoe UI", 8)).pack(side=LEFT)

        # przycisk zamknięcia okna
        btn_leg_close = ttk.Button(container, text=self.t["btn_leg_close"], command=leg_win.destroy,
                   bootstyle="secondary-link")
        btn_leg_close.pack(side=BOTTOM, pady=(10, 0))


    def clear_all_annotations(self):
        """ usuwanie wszystkich ramek ze skanu i podświetlenia z tekstu """
        # czyszczenie skanu
        self.canvas.delete("ner_box")

        # czyszczenie podświetleń w tekście (NER + wyszukiwanie)
        for tag in ["PERS", "LOC", "ORG", "search_highlight"]:
            self.text_area.tag_remove(tag, "1.0", tk.END)

        # resetowanie stanu przycisków
        self.btn_cls.config(state="disabled")
        self.btn_box.config(state="disabled")


    def _calculate_checksum(self, text):
        """ suma kontrolna SHA-256 dla tekstu transkrypcji """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()


    def _get_ner_json_path(self):
        """ ścieżka do pliku .json z metadanymi dla aktualnego skanu """
        if not self.file_pairs:
            return None
        txt_path = self.file_pairs[self.current_index]['txt']
        return os.path.splitext(txt_path)[0] + ".json"


    def clear_search(self):
        """ czyści wyniki wyszukiwania """
        self.text_area.tag_remove("search_highlight", "1.0", tk.END)
        self.search_var.set("")


    def perform_search(self):
        """ wyszukuje i podświetla frazę w tekście transkrypcji """
        # czyszczenie poprzednich wyników wyszukiwania
        self.text_area.tag_remove("search_highlight", "1.0", tk.END)
        # czyszczenie kolorowania nazw własnych
        for tag in ["PERS", "LOC", "ORG"]:
            self.text_area.tag_remove(tag, "1.0", tk.END)

        query = self.search_var.get().strip()
        if not query:
            return

        start_pos = "1.0"
        count = 0
        while True:
            # szukanie frazy (nocase=True dla ignorowania wielkości liter)
            start_pos = self.text_area.search(query, start_pos, stopindex=tk.END, nocase=True)
            if not start_pos:
                break

            # obliczanie końca frazy
            end_pos = f"{start_pos}+{len(query)}c"
            self.text_area.tag_add("search_highlight", start_pos, end_pos)

            # przewijanie do pierwszego znalezionego wyniku
            if count == 0:
                self.text_area.see(start_pos)

            start_pos = end_pos
            count += 1

        if count == 0:
            # mignięcie ramką entry na czerwono przy braku wyników
            self.search_entry.config(bootstyle="danger")
            self.root.after(500, lambda: self.search_entry.config(bootstyle="default"))


    def _parse_coordinates_response(self, text):
        """ wyodrębnia nazwy i współrzędne [y1, x1, y2, x2] z odpowiedzi modelu """
        results = []
        # wyszukiwanie wzorca: nazwa, nazwa_kategorii [ymin, xmin, ymax, xmax]
        pattern = r"(.*?)\s*,(.*?)\s*\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]"
        matches = re.findall(pattern, text)

        for m in matches:
            results.append({
                'name': m[0].strip(),
                'category': m[1].strip(),
                'coords': [int(x) for x in m[2:]]
            })
        return results


    def _on_text_modified(self, event):
        """
        automatyczne usuwanie podświetlenia nazw własnych i ramek ze skanu
        przy edycji tekstu
        """
        for tag in ["PERS", "LOC", "ORG"]:
            self.text_area.tag_remove(tag, "1.0", tk.END)
        self.canvas.delete("ner_box") # usuwanie ramek z obrazu


    def start_ner_analysis(self):
        """ inicjacja procesu ekstrakcji nazw własnych przez AI lub
            wczytanie nazw własnych z pliku metadanych, w osobnym wątku
        """
        text = self.text_area.get(1.0, tk.END).strip()
        if not text or self.is_transcribing:
            return

        self.btn_ner.config(state="disabled")

        current_checksum = self._calculate_checksum(text)
        json_path = self._get_ner_json_path()

        # próba wczytania metadanych z json
        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # wczytywanie jeżeli suma kontrolna się zgadza
                if cache_data.get("checksum") == current_checksum:
                    self.last_entities = cache_data.get("entities", {})
                    self.text_area.tag_remove("PERS", "1.0", tk.END) # czyszczenie poprzednich
                    self.text_area.tag_remove("LOC", "1.0", tk.END)
                    self.text_area.tag_remove("ORG", "1.0", tk.END)
                    self._apply_ner_categories(self.last_entities)
                    self.btn_ner.config(state="normal")
                    self.btn_cls.config(state="normal")
                    return

            except Exception as e:
                print(self.t["msg_ner_metadata_error"] + f": {e}")

        # wywołanie AI jeżeli brak pliku json z metadanymi
        # suma kontrolna przekazywana do wątku, w celu zapisu w json po analizie AI
        thread = threading.Thread(target=self._ner_worker,
                                  args=(text, current_checksum), daemon=True)
        thread.start()


    def _ner_worker(self, text, checksum):
        """ dodatkowa analiza tekstu przez Gemini w celu uzyskania listy nazw własnych:
            osoby, miejsca, instytucje """
        try:
            client = genai.Client(api_key=self.api_key)

            prompt = """
Jesteś ekspertem w dziedzinie historii i paleografii XVIII, XIX oraz XX wieku. Twoim zadaniem
jest ekstrakcja nazw własnych z transkrypcji dokumentów historycznych.

Zasady klasyfikacji:
1. PERS (Osoby): Wyodrębnij nazwy osób, mogą to być pełne imiona i nazwiska, ale także zapisy
   samych nazwisk lub imion, zapisy inicjałów np. A. T., zapisy nazw stosowane w średniowieczu
   np. Jan z Dąbrówki, uwzględnij także nazwy narodów lub plemion. DOŁĄCZ do nazwy towarzyszące im
   tytuły szlacheckie (np. hr., margrabia), stopnie wojskowe (np. kpt., gen.),
   funkcje urzędowe (np. rządzca, wójt) oraz zwroty grzecznościowe (np. JW Pan, Ob.),
   jeśli występują bezpośrednio przy nazwisku.
2. LOC (Geografia): Wyodrębnij nazwy miast, wsi, krajów, państw, folwarków, majątków ziemskich, rzek,
   jezior, guberni oraz konkretne nazwy ulic i placów.
3. ORG (Organizacje): Wyodrębnij nazwy urzędów, instytucji, pułków wojskowych, parafii, komitetów, stowarzyszeń,
   fabryk i towarzystw (np. "Towarzystwo Kredytowe Ziemskie").

Instrukcje techniczne:
- Rekonstrukcja: Jeśli nazwa jest podzielona między wiersze (np. "Krak-" i "ów"),
  połącz ją w jedno słowo bez dywizu ("Kraków").
- Normalizacja: Zwróć nazwy w takiej formie (deklinacji), w jakiej występują w tekście, ale usuń
  znaki podziału wiersza.
- Czystość: Ignoruj nazwy pospolite, chyba że są częścią nazwy własnej.

Zwróć wynik WYŁĄCZNIE jako JSON w formacie:
{
  "PERS": ["nazwa1", ...],
  "LOC": ["nazwa1", ...],
  "ORG": ["nazwa1", ...]
}
"""

            config = types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )

            model = "gemini-flash-latest" # lub gemini-3-flash-preview

            response = client.models.generate_content(
                model=model,
                contents=prompt + "\nTekst: " + text,
                config=config
            )

            if response.usage_metadata:
                self._log_api_usage(model, response.usage_metadata)

            if response.text:
                json_str = response.text.replace("```json", "").replace("```", "").strip()
                entities_dict = json.loads(json_str)
                self.last_entities = entities_dict

                # zapis metdanych NER do pliku *.json z usunięciem ewentualnych współrzędnych ramek
                # nowe nazwy własne oznaczają konjieczność wyszukania nowych ramek na skanie
                self._save_ner_cache(entities=entities_dict, coordinates=[], checksum=checksum)

                self.root.after(0, self._apply_ner_categories, entities_dict)
        except Exception as e:
            print(self.t["msg_ner_error"] + f": {e}")
        finally:
            self.root.after(0, lambda: self.btn_ner.config(state="normal"))


    def _save_ner_cache(self, entities=None, coordinates=None, checksum=None, tts_checksum=None):
        """ zapis wyników NER, współrzędnych i sum kontrolnych do pliku .json """
        json_path = self._get_ner_json_path()
        if not json_path:
            return

        # jeśli plik istnieje jest wczytywany, aby nie stracić danych
        cache_data = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
            except Exception as e:
                print(e)

        # aktualizacja pól, które zostały przekazane
        if checksum:
            cache_data["checksum"] = checksum
        if entities:
            cache_data["entities"] = entities
        if coordinates is not None:
            # usuwanie jeżeli przekazano pustą listę (czyli odświeżono NER)
            if coordinates == []:
                cache_data.pop("coordinates", None)
            else:
                cache_data["coordinates"] = coordinates
        if tts_checksum:
            cache_data["tts_checksum"] = tts_checksum

        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(self.t["msg_ner_json_error"] + f": {e}")


    def _apply_ner_categories(self, entities_dict):
        """ podświetlenie nazw własnych z podziałem na kolory i obsługą rozbitych słów """
        # czyszczenie poprzednich tagów
        for tag in ["PERS", "LOC", "ORG"]:
            self.text_area.tag_remove(tag, "1.0", tk.END)

        for category, names in entities_dict.items():
            for name in names:
                # wzorzec regex, który pozwala znaleźć np. "Krak-ów" szukając "Kraków"
                search_pattern = ""
                name_len = len(name)

                for i, char in enumerate(name):
                    search_pattern += re.escape(char)
                    # jeżeli to nie jest ostatni znak, dodaje elastyczne dopasowanie rozbić
                    if i < name_len - 1:
                        # opcjonalny myślnik, spacje i nową linię
                        search_pattern += r"(?:-?\s*\n?\s*)"

                start_pos = "1.0"
                while True:
                    match_count = tk.IntVar()
                    start_pos = self.text_area.search(search_pattern, start_pos,
                                                     stopindex=tk.END, nocase=True,
                                                     regexp=True, count=match_count)
                    if not start_pos:
                        break

                    # koniec na podstawie faktycznej liczby znalezionych znaków
                    end_pos = f"{start_pos}+{match_count.get()}c"

                    # kolor odpowiedni dla kategorii
                    self.text_area.tag_add(category, start_pos, end_pos)
                    start_pos = end_pos

        if any(entities_dict.values()):
            self.btn_box.config(state="normal")
            self.btn_cls.config(state="normal")


    def start_coordinates_analysis(self):
        """ uruchamianie rysowania lokalizacji nazw na obrazie """
        if not self.last_entities or not self.original_image:
            return

        text = self.text_area.get(1.0, tk.END).strip()
        current_checksum = self._calculate_checksum(text)
        json_path = self._get_ner_json_path()

        # odczytywanie metadanych z pliku json
        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # jeśli suma kontrolna się zgadza i istnieją metadane
                if cache_data.get("checksum") == current_checksum and "coordinates" in cache_data:
                    self._draw_boxes_only(cache_data["coordinates"])
                    return

            except Exception as e:
                print(e)

        # brak metadanych - wywołanie AI
        self.btn_box.config(state="disabled", text="..." )
        threading.Thread(target=self._box_worker, args=(current_checksum,), daemon=True).start()


    def _box_worker(self, checksum):
        try:
            client = genai.Client(api_key=self.api_key)
            current_pair = self.file_pairs[self.current_index]
            with open(current_pair['img'], 'rb') as f:
                image_bytes = f.read()

            entities_to_find = []
            for cat, names in self.last_entities.items():
                for name in names:
                    entities_to_find.append((name, cat))

            entities_str = ""
            for entity in entities_to_find:
                entity_name, entity_cat = entity
                entities_str += f"{entity_name},{entity_cat}\n"

            prompt = f"""
Na załączonym obrazie znajdź lokalizację następujących nazw,
(podanych w formie listy par: nazwa_do_wyszukania, kategoria_nazwy, każda para w osobnym wierszu np.
Felicjan Słomkowski, PERS
Gniezno, LOC):

{entities_str}.

Uwzględnij tylko i wyłącznie nazwy z listy, inne zignoruj.
Dla każdej nazwy podaj współrzędne ramki w formacie:

nazwa, nazwa_kategorii [ymin, xmin, ymax, xmax]

na przykład:
Krakowa, LOC [ymin, xmin, ymax, xmax]
Henryk Walezy, PERS [ymin, xmin, ymax, xmax]
...

Wszystkie współrzędne w skali 0-1000.
Zwróć tylko listę tych danych bez żadnych dodatkowych komentarzy.
"""

            config = types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                image_config=types.ImageConfig(
                    image_size="1K",
                ),
                response_modalities=[
                    "TEXT"
                ]
            )

            model = "gemini-3-pro-image-preview"

            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')
                ],
                config=config
            )

            if response.usage_metadata:
                self._log_api_usage(model, response.usage_metadata)

            if response.text:
                coordinates_data = self._parse_coordinates_response(response.text)

                # zapis współrzędnych ramek do pliku JSON z metadanymi
                self._save_ner_cache(entities=None, coordinates=coordinates_data, checksum=checksum)

                self.root.after(0, self._draw_boxes_only, coordinates_data)

        except Exception as e:
            print(self.t["msg_box_error"] + f": {e}")
        finally:
            self.root.after(0, lambda: self.btn_box.config(state="normal", text="BOX"))


    def _draw_boxes_only(self, entities_data):
        """ rysowanie ramki na canvasie """
        self.canvas.delete("ner_box")
        self.box_to_data_map = {}
        orig_w, orig_h = self.original_image.width, self.original_image.height

        for i, item in enumerate(entities_data):
            name = item['name']
            c = item['coords']

            cat = item.get('category', '?') # kategoria nazwy własnej
            bg_color = self.category_colors.get(cat, "#fbfaf7")
            line_color = "#ff0000"

            x1 = (c[1] * orig_w / 1000) * self.scale + self.img_x
            y1 = (c[0] * orig_h / 1000) * self.scale + self.img_y
            x2 = (c[3] * orig_w / 1000) * self.scale + self.img_x
            y2 = (c[2] * orig_h / 1000) * self.scale + self.img_y

            entity_tag = f"box_{i}"

            # główna ramka - tag "main_rect"
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=line_color, width=3,
                                         fill=line_color, stipple="gray12",
                                         tags=("ner_box", entity_tag, "main_rect"))

            # tekst etykiety ramki
            text_id = self.canvas.create_text(x1, y1 - 2, text=f"{name}", anchor="sw",
                                             fill="black", font=("Segoe UI", 9, "bold"),
                                             tags=("ner_box", entity_tag, "label_text"))

            # tło etykiety ramki - tag "label_bg"
            bbox = self.canvas.bbox(text_id)
            bg_id = self.canvas.create_rectangle(bbox, fill=bg_color, outline=line_color,
                                                tags=("ner_box", entity_tag, "label_bg"))
            self.canvas.tag_raise(text_id, bg_id)

            # uchwyt ramki
            h_size = 4
            self.canvas.create_rectangle(x2 - h_size, y2 - h_size, x2 + h_size, y2 + h_size,
                                         fill="white", outline=line_color, width=1,
                                         tags=("ner_box", entity_tag, "resize_handle"))

            # przypisanie przycików i klawiszy
            self.canvas.tag_bind(entity_tag, "<Button-1>", lambda e, t=entity_tag: self._on_box_press(e, t))
            self.canvas.tag_bind(entity_tag, "<B1-Motion>", self._on_box_drag)
            self.canvas.tag_bind(entity_tag, "<ButtonRelease-1>", self._on_box_release)
            self.canvas.tag_bind(entity_tag, "<Control-Button-1>", lambda e, t=entity_tag: self._on_box_delete(e, t))
            self.canvas.tag_bind(entity_tag, "<Motion>", lambda e, t=entity_tag: self._on_box_hover(e, t))

            self.box_to_data_map[entity_tag] = i


    def _on_box_hover(self, event, entity_tag):
        """ weryfikacja czy kursor jest nad uchwytem lub ramką """
        # pobieranie ID obiektu bezpośrednio pod myszą
        item_under_mouse = self.canvas.find_closest(event.x, event.y)[0]
        tags = self.canvas.gettags(item_under_mouse)

        if "resize_handle" in tags:
            self.canvas.config(cursor=self.cursor_resizing)
        else:
            self.canvas.config(cursor=self.cursor_move)
        return "break"


    def _on_box_resize_start(self, event, entity_tag):
        """ inicjacja zmiany rozmiaru i blokada ruchu obrazu """
        self.resizing_box_tag = entity_tag
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y
        # kursor zmiany rozmiaru
        self.canvas.config(cursor=self.cursor_resizing)
        return "break" # blokowanie przesuwanie skanu


    def _on_box_drag(self, event):
        """ wykonuje przesuwanie lub zmianę rozmiaru zależnie od box_action """
        if not hasattr(self, 'active_box_tag') or self.active_box_tag is None:
            return

        dx = event.x - self.last_mouse_x
        dy = event.y - self.last_mouse_y

        # wszystkie elementy należące do tej konkretnej nazwy własnej
        items = self.canvas.find_withtag(self.active_box_tag)

        rect_id = None
        handle_id = None

        # szukanie konkretnie po tagach nadanych w _draw_boxes_only
        for item in items:
            tags = self.canvas.gettags(item)
            if "resize_handle" in tags:
                handle_id = item
            elif "main_rect" in tags:  # by nie "złapać" żółtego tła etykiety
                rect_id = item

        if self.box_action == "move":
            # przesuwanie - całą grupą (ramka, etykieta, uchwyt)
            self.canvas.move(self.active_box_tag, dx, dy)

        elif self.box_action == "resize" and rect_id and handle_id:
            # zmiana rozmiaru: aktualizacja dolnego prawego rogu głównej ramki
            coords = self.canvas.coords(rect_id) # [x1, y1, x2, y2]

            # nowe współrzędne (minimalna wielkość 10x10)
            new_x2 = max(coords[0] + 10, event.x)
            new_y2 = max(coords[1] + 10, event.y)

            # zmiana rozmiaru głównej ramki (czerwonej)
            self.canvas.coords(rect_id, coords[0], coords[1], new_x2, new_y2)

            # przesunięcie białego kwadracika (uchwytu), by podążał za nowym rogiem
            h_s = 4
            self.canvas.coords(handle_id, new_x2 - h_s, new_y2 - h_s, new_x2 + h_s, new_y2 + h_s)

            # tło etykiety i tekst zostają w lewym górnym rogu (coords[0], coords[1])
            # zmiana rozmiaru oznacza w aplikacji tylko rozciąganie w dół/prawo.

        self.last_mouse_x = event.x
        self.last_mouse_y = event.y
        return "break"


    def _on_box_release(self, event):
        """ finalizacja operacji i zapis do JSON """
        # ujednolicony tag aktywnego obiektu
        tag = getattr(self, 'active_box_tag', None)
        if not tag:
            return

        items = self.canvas.find_withtag(tag)
        rect_id = None

        # szukanie głównej ramki po tagu
        for item in items:
            if "main_rect" in self.canvas.gettags(item):
                rect_id = item
                break

        if rect_id:
            coords = self.canvas.coords(rect_id)
            orig_w = self.original_image.width
            orig_h = self.original_image.height

            # przeliczenie na skalę modelu: 0-1000
            x1_model = int(((coords[0] - self.img_x) / self.scale) * 1000 / orig_w)
            y1_model = int(((coords[1] - self.img_y) / self.scale) * 1000 / orig_h)
            x2_model = int(((coords[2] - self.img_x) / self.scale) * 1000 / orig_w)
            y2_model = int(((coords[3] - self.img_y) / self.scale) * 1000 / orig_h)

            json_path = self._get_ner_json_path()
            if json_path and os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)

                    idx = self.box_to_data_map[tag]
                    cache_data["coordinates"][idx]["coords"] = [y1_model, x1_model, y2_model, x2_model]

                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=4)

                except Exception as e:
                    print(self.t["msg_json_save_error"] + f": {e}")

        # resetowanie stanu
        self.canvas.config(cursor="")
        self.active_box_tag = None
        self.box_action = None


    def _on_box_delete(self, event, entity_tag):
        """ usuwanie ramki z obrazu i aktualizacja pliku JSON """
        # indeks ramki z mapy
        idx = self.box_to_data_map.get(entity_tag)
        if idx is None:
            return

        # potwierdzenie usuwania
        # if not messagebox.askyesno("Usuwanie", "Czy usunąć tę ramkę ze skanu?", parent=self.root):
        #     return

        # aktualizacja pliku JSON
        json_path = self._get_ner_json_path()
        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                if "coordinates" in cache_data:
                    # usuwanie elementu o konkretnym indeksie
                    removed_item = cache_data["coordinates"].pop(idx)

                    # zapis zaktualizowango pliku
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=4)

                    # odrysowanie ramek, aby zaktualizować indeksy w box_to_data_map
                    self._draw_boxes_only(cache_data["coordinates"])

                    #print(f"Usunięto ramkę dla: {removed_item.get('name')}")
            except Exception as e:
                messagebox.showerror(self.t["msg_error_title"], self.t["msg_json_update_error"] + f": {e}")


    def _on_box_press(self, event, entity_tag):
        """ rozpoznaje czy użytkownik chce przesuwać, czy zmieniać rozmiar """
        self.active_box_tag = entity_tag
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

        # sprawdzanie co dokładnie kliknięto
        item_under_mouse = self.canvas.find_closest(event.x, event.y)[0]
        tags = self.canvas.gettags(item_under_mouse)

        if "resize_handle" in tags:
            self.box_action = "resize"
            self.canvas.config(cursor=self.cursor_resizing)
        else:
            self.box_action = "move"
            self.canvas.config(cursor=self.cursor_move)

        return "break" # blokada ruchu skanu


    def change_tts_language(self, event):
        """ zmienia język TTS na podstawie wyboru z listy """
        selected_name = self.lang_combobox.get()
        if selected_name in self.tts_languages:
            self.current_tts_lang_code = self.tts_languages[selected_name]
            self.save_config()


    def pause_reading(self):
        """ obsługa wstrzymywania i wznawiania odtwarzania """
        if self.playback.active:
            if self.playback.paused:
                self.playback.resume()
                self.btn_pause.config(text="||")
            else:
                self.playback.pause()
                self.btn_pause.config(text=">")

    def read_text_aloud(self):
        """ przygotowanie tekstu i uruchamienie wątku TTS """
        try:
            text_to_read = self.text_area.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        except tk.TclError:
            text_to_read = self.text_area.get(1.0, tk.END).strip()

        if not text_to_read:
            return

        if self.is_reading_audio:
            self.stop_reading()

        self.is_reading_audio = True
        self.btn_speak.config(state="disabled")
        self.btn_pause.config(state="disabled", text="||")
        self.btn_stop.config(state="normal")

        threading.Thread(target=self._tts_worker, args=(text_to_read,), daemon=True).start()


    def _tts_worker(self, text):
        """ kod wykonywany w wątku - tworzenie audio i start odtwarzania,
            jeżeli aktualnhy plik audio jest w pliku, odtwarzanie z pliku bez
            nowego generowania
        """
        try:
            lang_to_use = self.current_tts_lang_code
            current_checksum = self._calculate_checksum(text)

            # ścieżki
            pair = self.file_pairs[self.current_index]
            mp3_path = os.path.splitext(pair['img'])[0] + ".mp3"
            json_path = self._get_ner_json_path()

            needs_generation = True

            # sprawdanie czy plik MP3 istnieje i czy suma kontrolna się zgadza
            if os.path.exists(mp3_path) and os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                        if cache_data.get("tts_checksum") == current_checksum:
                            needs_generation = False

                except Exception as e:
                    print(self.t["msg_tts_cache_error"] + f": {e}")

            # generowanie pliku tylko jeśli to konieczne
            if needs_generation:
                tts = gTTS(text=text, lang=lang_to_use)
                tts.save(mp3_path)
                # zapis nową sumę kontrolną audio w JSON
                self._save_ner_cache(tts_checksum=current_checksum)

            # odtwarzanie
            if self.is_reading_audio:
                self.playback.load_file(mp3_path)
                self.playback.play()

                # odblokowanie pauzy po rozpoczęciu odtwarzania
                self.root.after(0, lambda: self.btn_pause.config(state="normal"))
                self.root.after(100, self._check_audio_status)

        except Exception as e:
            print(self.t["msg_tts_error"] + f": {e}")
            self.root.after(0, self.stop_reading)


    def _check_audio_status(self):
        """ sprawdzanie stanu odtwarzania """
        if not self.is_reading_audio:
            return

        if self.playback.active:
            self.root.after(100, self._check_audio_status)
        else:
            self.stop_reading()

    def stop_reading(self):
        """ pełne zatrzymanie i reset interfejsu """
        try:
            self.playback.stop()
        except Exception as e:
            print(e)

        self.is_reading_audio = False
        self.btn_speak.config(state="normal")
        self.btn_pause.config(state="disabled", text="||")
        self.btn_stop.config(state="disabled")


    def apply_filter(self, mode):
        """ zastosuj filtr dla bieżącego skanu """
        if not self.original_image: return
        self.active_filter = mode
        img = self.original_image.copy()

        if mode == "invert":
            if img.mode != 'RGB': img = img.convert('RGB')
            img = ImageOps.invert(img)
        elif mode == "contrast":
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)
            img = ImageEnhance.Sharpness(img).enhance(1.5)

        self.processed_image = img
        self.redraw_image()


    def load_lang(self):
        """ wczytywanie wersji językowych z pliku JSON """
        localization_path = Path('..') / 'config' / self.local_file
        if localization_path.exists():
            try:
                with open(localization_path, 'r', encoding='utf-8') as f:
                    self.localization = json.load(f)
                    for key, value in self.localization.items():
                        self.languages.append(key)

            except Exception as e:
                print(self.t["msg_lang_file_error"] + f": {e}")


    def load_config(self):
        """ wczytywanie ustawień z pliku JSON """
        config_path = Path('..') / 'config' / self.config_file
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.font_size = config.get("font_size", 12)
                    # wczytanie języka audio
                    self.current_tts_lang_code = config.get("tts_lang", "pl")
                    # wczytanie języka interfejsu
                    self.current_lang = config.get("current_lang", "PL")
                    # domyślny prompt
                    self.default_prompt = config.get("default_prompt",
                                                     "prompt_handwritten_pol_xx_century.txt")

                    # opcjonalny api key w pliku config
                    if not self.api_key:
                        self.api_key = config.get("api_key", "")
            except Exception as e:
                print(self.t["msg_config_file_error"] + f": {e}")


    def save_config(self):
        """ zapisywanie ustawienia do pliku JSON """
        config_path = Path('..') / 'config' / self.config_file
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                config["font_size"] = self.font_size
                config["tts_lang"] = self.current_tts_lang_code
                config["current_lang"] = self.current_lang
                config["default_prompt"] = self.default_prompt
        else:
            config = {
                "font_size": self.font_size,
                "tts_lang": self.current_tts_lang_code,
                "current_lang": self.current_lang,
                "default_prompt": self.default_prompt,
                "api_key": ""
            }

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f)
        except Exception as e:
            print(self.t["msg_save_config_file_error"] + f": {e}")


    def change_font_size(self, delta):
        """ zmiana rozmiar fontu edytora i zapis do pliku z configiem """
        new_size = self.font_size + delta
        if new_size < 6:
            new_size = 6
        if new_size > 72:
            new_size = 72

        self.font_size = new_size
        self.text_area.configure(font=(self.font_family, self.font_size))

        self.save_config()


    def on_text_zoom(self, event):
        """ zmiana rozmaru fontu"""
        delta = 0
        if event.num == 5 or event.delta < 0:
            delta = -1
        elif event.num == 4 or event.delta > 0:
            delta = 1

        self.change_font_size(delta)
        return "break"


    def _init_environment(self):
        """ ładowanie zmiennych środowiskowych i promptu """
        load_dotenv()

        if not self.api_key:
            self.api_key = os.environ.get("GEMINI_API_KEY")

        if self.default_prompt:
            self.prompt_filename_var.set(self.default_prompt)
        else:
            self.prompt_filename_var.set("")

        if self.default_prompt:
            prompt_path = Path('..') / "prompt" / self.default_prompt
            if os.path.exists(prompt_path):
                try:
                    with open(prompt_path, 'r', encoding='utf-8') as f:
                        self.prompt_text = f.read()
                    self.prompt_filename_var.set(f"{self.default_prompt}")
                    self.current_prompt_path = str(prompt_path)
                except Exception as e:
                    messagebox.showerror(self.t["msg_error_title"],
                                         self.t["msg_file_prompt_error"] + f" {self.default_prompt}: {e}", parent=self.root)
            else:
                messagebox.showerror(self.t["msg_prompt_file_missing"], str(e), parent=self.root)


    def select_folder(self):
        """ wybór folderu """
        if self.is_transcribing:
            return

        initial_dir = os.getcwd() # domyślnie bieżący katalog

        folder_path = filedialog.askdirectory(
            title=self.t["select_folder_title"],
            initialdir=initial_dir,
            parent=self.root
        )

        if folder_path:
            display_path = folder_path
            if len(display_path) > 40:
                display_path = "..." + display_path[-37:] # ostatnie 37 znaków
            self.current_folder_var.set(display_path)

            # załadowanie plików
            self.load_file_list(folder_path)


    def load_file_list(self, folder):
        """ ładowanie listy plików skanów ze wskazanego folderu"""
        try:
            all_files = os.listdir(folder)
            images = [f for f in all_files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            images.sort()

            self.file_pairs = []
            for img in images:
                base = os.path.splitext(img)[0]
                self.file_pairs.append({
                    'img': os.path.join(folder, img),
                    'txt': os.path.join(folder, base + ".txt"),
                    'name': base
                })

            if not self.file_pairs:
                messagebox.showinfo("Info", self.t["scan_files_missing"], parent=self.root)
                self.original_image = None
                self.processed_image = None
                self.canvas.delete("all")
                self.text_area.delete(1.0, tk.END)
                self.file_info_var.set(self.t["scan_folder_empty"])
                return

            self.current_index = 0
            self.load_pair(0)
        except Exception as e:
            messagebox.showerror(self.t["msg_error_title"],
                                 self.t["msg_folder_scan_error"] + f": {e}", parent=self.root)


    def load_pair(self, index):
        """ ładowanie par plików: skan i transkrypcja """
        if not self.file_pairs:
            return
        pair = self.file_pairs[index]

        # reset
        self.last_entities = []
        self.btn_box.config(state="disabled")
        self.btn_cls.config(state="disabled")
        self.canvas.delete("ner_box")

        # aktualizacja nagłówka
        self.file_info_var.set(f"[{index + 1}/{len(self.file_pairs)}] {pair['name']}")

        # skan
        try:
            self.original_image = Image.open(pair['img'])
            self.processed_image = self.original_image.copy()
            self.active_filter = "normal"

            # obsługa dopasowania obrazu do szerokości canvas
            canvas_w = self.canvas.winfo_width()

            # jeśli szerokość canvasu jest jednak jeszcze nieznana
            if canvas_w <= 1:
                # fallback: np. 60% szerokości okna
                canvas_w = self.root.winfo_width() * 0.6

            # obliczanie skali tak, by obraz zajął całą szerokość (z małym marginesem 10px)
            self.scale = (canvas_w - 10) / self.original_image.width

            # Ograniczenie, by skan nie był zbyt wielki przy małych plikach
            if self.scale > 2.0: self.scale = 2.0

            self.img_x, self.img_y = 0, 0
            self.redraw_image()
        except Exception as e:
            print(e)

        # tekst
        self.text_area.delete(1.0, tk.END)
        if os.path.exists(pair['txt']):
            try:
                with open(pair['txt'], 'r', encoding='utf-8') as f:
                    self.text_area.insert(tk.END, f.read())
            except Exception as e:
                print(e)

        self.text_area.focus_set()
        self.text_area.mark_set("insert", "1.0")
        self.text_area.see("1.0")
        self.root.after(10, self.update_active_line_highlight)


    def redraw_image(self):
        """ odrysowywanie obrazu """
        source_img = self.processed_image if self.processed_image else self.original_image
        if not source_img:
            return

        w, h = int(source_img.width * self.scale), int(source_img.height * self.scale)
        try:
            resized = source_img.resize((w, h), Image.Resampling.BILINEAR)
            self.tk_image = ImageTk.PhotoImage(resized)
            self.canvas.delete("all")
            self.canvas.create_image(self.img_x, self.img_y, image=self.tk_image, anchor="nw")
            self.zoom_label.config(text=f"Zoom: {int(self.scale * 100)}%")
        except Exception as e:
            print(self.t["msg_redraw_error"] + f": {e}")


    def fit_to_width(self):
        """ wymusza dopasowanie obrazu do aktualnej szerokości panelu """
        if not self.original_image:
            return

        self.canvas.delete("ner_box")

        canvas_w = self.canvas.winfo_width()
        if canvas_w > 1:
            self.scale = (canvas_w - 10) / self.original_image.width
            self.img_x, self.img_y = 0, 0
            self.redraw_image()


    def load_prompt_content(self, filepath):
        """ wczytuje treść promptu z pliku """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.prompt_text = f.read()

            filename = os.path.basename(filepath)
            self.prompt_filename_var.set(f"{filename}")
            self.current_prompt_path = filepath
            return True
        except Exception as e:
            messagebox.showerror(self.t["msg_load_prompt_error_title"],
                                 self.t["msg_load_prompt_error_text"] + f":\n{e}", parent=self.root)
            return False


    def select_prompt_file(self):
        """ okno dialogowe wyboru pliku promptu """
        prompt_path = Path('..') / 'prompt'
        filename = filedialog.askopenfilename(
            title=self.t["select_prompt_title"],
            initialdir=prompt_path,
            filetypes=[(self.t["file_type_text"], "*.txt"), (self.t["file_type_all"], "*.*")],
            parent=self.root
        )

        self.root.focus_set()
        self.root.update_idletasks()

        if filename:
            self.load_prompt_content(filename)


    def on_mouse_down(self, event):
        """ obsługa myszy - naciśnięcie klawisza """
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y


    def on_mouse_drag(self, event):
        """ obsługa myszy - przesuwanie """
        dx = event.x - self.last_mouse_x
        dy = event.y - self.last_mouse_y
        self.img_x += dx
        self.img_y += dy
        self.canvas.move("all", dx, dy)
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y


    def on_mouse_wheel(self, event):
        """ obsługa myszy - skrolowanie kółkiem - zoom """
        factor = 0.9 if (event.num == 4 or event.delta > 0) else 1.1
        self.scale *= factor
        self.scale = max(self.scale, 0.05)
        self.scale = min(self.scale, 10.0)
        self.redraw_image()


    def save_current_text(self, silent=False):
        """
        zapis bieżącej zawartości pola tekstowego w pliku,
        parametr 'silent=True' wyłącza 'mruganie' etykietą (przy przełączaniu stron).
        """
        if not self.file_pairs:
            return
        pair = self.file_pairs[self.current_index]
        content = self.text_area.get(1.0, tk.END).strip()
        if content:
            content += "\n"

        try:
            with open(pair['txt'], 'w', encoding='utf-8') as f:
                f.write(content)

            # komunikat tylko jeśli nie jest to tryb silent
            if not silent:
                original_text = self.file_info_var.get()
                if self.t["text_saved"] not in original_text:
                    self.file_info_var.set(original_text + " " + self.t["text_saved"])
                    self.root.after(1000, lambda: self.refresh_label_safely(self.current_index))

        except Exception as e:
            messagebox.showerror(self.t["text_save_error"], str(e), parent=self.root)


    def refresh_label_safely(self, expected_index):
        """ pomocnicza funkcja przywracająca czystą nazwę pliku po zniknięciu komunikatu """
        if self.current_index == expected_index and self.file_pairs:
            pair = self.file_pairs[self.current_index]
            self.file_info_var.set(f"[{self.current_index + 1}/{len(self.file_pairs)}] {pair['name']}")


    def first_file(self):
        """ przejście do pierwszego pliku """
        if self.is_transcribing:
            return

        self.save_current_text(silent=True)
        if self.current_index != 0:
            self.current_index = 0
            self.load_pair(self.current_index)


    def next_file(self):
        """ przejście do następnego pliku """
        if self.is_transcribing:
            return

        self.save_current_text(silent=True)
        if self.current_index < len(self.file_pairs) - 1:
            self.current_index += 1
            self.load_pair(self.current_index)


    def prev_file(self):
        """ przejście do poprzedniego pliku """
        if self.is_transcribing:
            return

        self.save_current_text(silent=True)
        if self.current_index > 0:
            self.current_index -= 1
            self.load_pair(self.current_index)


    def last_file(self):
        """ przejście do ostatniego pliku """
        if self.is_transcribing:
            return

        self.save_current_text(silent=True)
        if self.current_index < len(self.file_pairs) - 1:
            self.current_index = len(self.file_pairs) - 1
            self.load_pair(self.current_index)


    def export_all_data(self):
        """ eksport wszystkich transkrypcji do jednego pliku txt """
        self.save_current_text(silent=True)

        if not self.file_pairs:
            messagebox.showwarning(self.t["msg_export_txt_missing_title"],
                                   self.t["msg_export_txt_missing_text"], parent=self.root)
            return

        target_path = filedialog.asksaveasfilename(
            title=self.t["file_dialog_export_txt_title"],
            defaultextension=".txt",
            filetypes=[(self.t["msg_export_txt_text"], "*.txt")],
            parent=self.root
        )

        if not target_path:
            return

        try:
            merged_content = []

            for pair in self.file_pairs:
                txt_path = pair['txt']
                if os.path.exists(txt_path):
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        text_content = f.read().strip()
                        if text_content:
                            merged_content.append(text_content)

            final_text = "\n\n".join(merged_content)

            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(final_text)

            messagebox.showinfo(self.t["msg_csv_ok_title"],
                                self.t["msg_export_txt_text"] + f":\n{os.path.basename(target_path)}",
                                parent=self.root)

        except Exception as e:
            messagebox.showerror(self.t["msg_export_error_title"],
                                 self.t["msg_export_error_text"] + f":\n{e}", parent=self.root)


    def export_all_data_docx(self):
        """ eksport do pliku docx z łączeniem wyrazów """
        self.save_current_text(True)
        if not self.file_pairs:
            return

        path = filedialog.asksaveasfilename(
            title=self.t["file_dialog_export_docx_title"],
            defaultextension=".docx",
            filetypes=[(self.t["file_type_docx"], "*.docx")],
            parent=self.root)

        if not path:
            return

        try:
            doc = Document()

            for pair in self.file_pairs:
                if os.path.exists(pair['txt']):
                    all_lines = []
                    with open(pair['txt'], 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        all_lines.extend([line.strip() for line in lines])

                    full_text = ""
                    for line in all_lines:
                        if not line:
                            full_text += '\n\n'

                        if full_text == "":
                            full_text = line
                        else:
                            if full_text.endswith("-"):
                                full_text = full_text[:-1] + line
                            else:
                                full_text += " " + line

                    doc.add_paragraph(full_text)

            doc.save(path)

            messagebox.showinfo(self.t["msg_csv_ok_title"],
                                self.t["msg_export_docx_text"] + f":\n{os.path.basename(path)}",
                                parent=self.root)

        except Exception as e:
            messagebox.showerror(self.t["msg_export_error_title"], str(e), parent=self.root)


    def on_close(self):
        """ bezpieczne zamknięcie aplikacji z zapisem """
        try:
            self.save_current_text(silent=True)
        except Exception as e:
            print(e)

        self.root.destroy()


    def show_magnifier(self, event):
        """ utworzenie okna lupy po naciśnięciu prawego przycisku myszy """
        if not self.original_image:
            return

        # ustawienia lupy
        self.MAG_WIDTH, self.MAG_HEIGHT = 750, 300
        self.ZOOM_FACTOR = 2.0

        # tworzenie okna
        self.magnifier_win = tk.Toplevel(self.root)
        self.magnifier_win.overrideredirect(True) # Usunięcie ramek
        self.magnifier_win.attributes("-topmost", True) # Zawsze na wierzchu

        # tworzenie etykiety na obraz
        frame = ttk.Frame(self.magnifier_win, bootstyle="info", padding=2)
        frame.pack(fill=BOTH, expand=True)
        self.mag_label = ttk.Label(frame, background="white")
        self.mag_label.pack(fill=BOTH, expand=True)

        # pierwsza aktualizacja pozycji i zawartości
        self.update_magnifier(event)


    def update_magnifier(self, event):
        """ aktualizacja pozycji okna i wycinany fragment obrazu podczas ruchu myszy """
        if not self.magnifier_win or not self.original_image:
            return

        src = self.processed_image if self.processed_image else self.original_image

        # pozycjonowanie okna względem kursora systemowego
        pos_x = int(event.x_root - (self.MAG_WIDTH / 2))
        pos_y = int(event.y_root - (self.MAG_HEIGHT / 2))
        self.magnifier_win.geometry(f"{self.MAG_WIDTH}x{self.MAG_HEIGHT}+{pos_x}+{pos_y}")

        # obliczanie fragmentu do wycięcia z oryginału
        # przeliczanie współrzędnych canvasu na współrzędne oryginalnego obrazu
        orig_x = (event.x - self.img_x) / self.scale
        orig_y = (event.y - self.img_y) / self.scale

        crop_w = self.MAG_WIDTH / self.ZOOM_FACTOR
        crop_h = self.MAG_HEIGHT / self.ZOOM_FACTOR

        x1, y1 = orig_x - (crop_w / 2), orig_y - (crop_h / 2)
        x2, y2 = x1 + crop_w, y1 + crop_h

        try:
            # wycięcie i skalowanie
            region = src.crop((x1, y1, x2, y2))
            magnified_img = region.resize((self.MAG_WIDTH, self.MAG_HEIGHT), Image.Resampling.BILINEAR)

            # referencja do obrazu, by nie został usunięty przez garbage collector
            self.tk_mag_img = ImageTk.PhotoImage(magnified_img)
            self.mag_label.config(image=self.tk_mag_img)
        except Exception as e:
            # ignorowanie drobnych błędów dla funkcji crop
            print(e)


    def hide_magnifier(self, event):
        """ zamykanie okna lupy po zwolnieniu prawego przycisku myszy """
        if self.magnifier_win:
            self.magnifier_win.destroy()
            self.magnifier_win = None
            self.tk_mag_img = None


    def open_batch_dialog(self):
        """ otwiera okno dialogowe do przetwarzania seryjnego """
        if self.is_transcribing:
            messagebox.showwarning(self.t["msg_warning"],
                                   self.t["msg_batch_warning_text"], parent=self.root)
            return

        if not self.file_pairs:
            messagebox.showinfo(self.t["msg_missing_files"],
                                self.t["msg_missing_files_text"], parent=self.root)
            return

        # tworzenie okna dialogowego
        batch_win = tk.Toplevel(self.root)
        batch_win.title(self.t["batch_win_title"])
        batch_win.geometry("700x700")
        batch_win.transient(self.root)

        # nagłówek
        ttk.Label(batch_win, text=self.t["batch_label_text"], font=("Segoe UI", 12, "bold")).pack(pady=10)
        ttk.Label(batch_win, text=self.t["batch_label_info"],
                  bootstyle="secondary", font=("Segoe UI", 9)).pack(pady=(0, 10))

        # kontener na listę z przewijaniem
        list_frame = ScrolledFrame(batch_win, autohide=False)
        list_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)

        self.batch_vars = [] # pary (indeks_pliku, zmienna_boolean)

        for idx, pair in enumerate(self.file_pairs):
            txt_path = pair['txt']

            # logika domyślnego zaznaczania
            should_select = False
            status_text = ""

            if not os.path.exists(txt_path):
                should_select = True
                status_text = self.t["batch_status_text1"]
            elif os.path.getsize(txt_path) == 0:
                should_select = True
                status_text = self.t["batch_status_text2"]
            else:
                status_text = self.t["batch_status_text3"]

            var = tk.BooleanVar(value=should_select)
            self.batch_vars.append((idx, var))

            # wiersz dla pliku
            row = ttk.Frame(list_frame)
            row.pack(fill=X, pady=2)

            cb = ttk.Checkbutton(row, text=f"{pair['name']} {status_text}", variable=var, bootstyle="round-toggle")
            cb.pack(side=LEFT)

        # panel przycisków sterujących
        btn_panel = ttk.Frame(batch_win, padding=10)
        btn_panel.pack(fill=X, side=BOTTOM)

        # logi postępu
        self.batch_log_label = ttk.Label(batch_win, text=self.t["batch_log_label"], bootstyle="inverse-secondary")
        self.batch_log_label.pack(fill=X, side=BOTTOM, padx=10)

        self.batch_progress = ttk.Progressbar(batch_win, mode='determinate', bootstyle="success-striped")
        self.batch_progress.pack(fill=X, side=BOTTOM, padx=10, pady=5)

        # funkcje przycisków
        def select_all():
            for _, v in self.batch_vars:
                v.set(True)

        def select_none():
            for _, v in self.batch_vars:
                v.set(False)

        def start_batch():
            selected_indices = [idx for idx, var in self.batch_vars if var.get()]
            if not selected_indices:
                messagebox.showwarning("Info", self.t["batch_no_files_selected"], parent=batch_win)
                return

            # blokada przycisków
            btn_start.config(state="disabled")

            # uruchomienie wątku
            self.is_transcribing = True
            thread = threading.Thread(target=self._batch_worker, args=(selected_indices, batch_win, btn_start))
            thread.daemon = True
            thread.start()

        ttk.Button(btn_panel, text=self.t["batch_select_all"], command=select_all,
                   bootstyle="outline-secondary").pack(side=LEFT, padx=5)
        ttk.Button(btn_panel, text=self.t["batch_unselect_all"], command=select_none,
                   bootstyle="outline-secondary").pack(side=LEFT, padx=5)

        btn_start = ttk.Button(btn_panel, text=self.t["btn_start"], command=start_batch,
                               bootstyle="danger")
        btn_start.pack(side=RIGHT, padx=5)


    def _batch_worker(self, selected_indices, window, btn_start):
        """ wątek przetwarzający listę plików """
        total = len(selected_indices)
        errors = 0

        for i, idx in enumerate(selected_indices):
            # czy okno nie zostało zamknięte
            if not window.winfo_exists():
                break

            pair = self.file_pairs[idx]
            img_path = pair['img']
            txt_path = pair['txt']

            # aktualizacja GUI
            progress_pct = (i / total) * 100
            msg = self.t["batch_process_text"] + f" [{i+1}/{total}]: {pair['name']}..."

            self.root.after(0, lambda m=msg, v=progress_pct: self._update_batch_ui(m, v))

            try:
                # wywołanie API (ta sama metoda co przy pojedynczym pliku)
                result_text = self._call_gemini_api(img_path)

                # zapis do pliku
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(result_text + '\n')

            except Exception as e:
                errors += 1
                print(self.t["batch_worker_file_error"] + f" {pair['name']}: {e}")

        self.is_transcribing = False

        # zakończono
        if window.winfo_exists():
            final_msg = self.t["batch_final_msg1"] + f": {total}. " + self.t["batch_final_msg2"] + f": {errors}."
            self.root.after(0, lambda: self._update_batch_ui(final_msg, 100))
            self.root.after(0, lambda: btn_start.config(state="normal"))
            self.root.after(0, lambda: messagebox.showinfo(self.t["batch_final_msg_title"], final_msg, parent=window))

            # odświeżanie widok w głównym oknie (jeśli aktualnie wyświetlany plik był zmieniony)
            self.root.after(0, lambda: self.load_pair(self.current_index))


    def _update_batch_ui(self, message, progress_value):
        """ pomocnicza funkcja do aktualizacji UI w oknie batch """
        try:
            self.batch_log_label.config(text=message)
            self.batch_progress['value'] = progress_value
        except Exception as e:
            print(e)


    def _call_gemini_api(self, image_path):
        """ wspólna funkcja wołająca API, zwraca tekst transkrypcji """
        client = genai.Client(api_key=self.api_key)

        with open(image_path, 'rb') as f:
            image_bytes = f.read()

        model = "gemini-3-pro-preview"

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=self.prompt_text),
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')
                ]
            )
        ]

        generate_content_config = types.GenerateContentConfig(
            temperature=0,
            thinkingConfig=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config
        )

        if response.usage_metadata:
            self._log_api_usage(model, response.usage_metadata)

        return response.text


    def start_ai_transcription(self):
        """ inicjuje proces transkrypcji w tle """
        if not self.file_pairs or self.is_transcribing:
            return

        if not self.prompt_text:
            messagebox.showerror(self.t["prompt_config_error1"],
                                 self.t["prompt_config_error2"],
                                 parent=self.root)
            return

        if not self.api_key:
            messagebox.showerror(self.t["apikey_config_error1"],
                                 self.t["apikey_config_error2"],
                                 parent=self.root)
            return

        # blokada interfejsu
        self.is_transcribing = True
        self.btn_ai.config(state="disabled", text=self.t["btn_ai_process"])
        self.text_area.config(state="disabled") # bg="#222222" ?
        self.progress_bar.pack(fill=X, pady=(0, 10), before=self.editor_frame)
        self.progress_bar.start(10)

        current_pair = self.file_pairs[self.current_index]
        img_path = current_pair['img']

        # uruchomienie wątku
        thread = threading.Thread(target=self._single_worker, args=(img_path,))
        thread.daemon = True
        thread.start()


    def _single_worker(self, image_path):
        """ wątek dla pojedynczego pliku z obsługą strumieniowania """
        try:
            client = genai.Client(api_key=self.api_key)

            with open(image_path, 'rb') as f:
                image_bytes = f.read()

            model = "gemini-3-pro-preview"

            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=self.prompt_text),
                        types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')
                    ]
                )
            ]

            generate_content_config = types.GenerateContentConfig(
                temperature=0,
                thinkingConfig=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )

            # czyszczenie pola tekstowego przed startem strumienia (w wątku głównym)
            self.root.after(0, lambda: self.text_area.delete(1.0, tk.END))

            # iteracja po strumieniu odpowiedzi
            loop_usage_metadata = None
            for response in client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config
            ):
                if response.text:
                    # przekazanie fragmentu tekstu do aktualizacji UI
                    self.root.after(0, self._append_stream_text, response.text)
                    if response.usage_metadata:
                        loop_usage_metadata = response.usage_metadata

            if loop_usage_metadata:
                self.root.after(0, lambda: self._log_api_usage(model, loop_usage_metadata))

            self.root.after(0, self._single_finished, True, "")
        except Exception as e:
            self.root.after(0, self._single_finished, False, str(e))


    def _append_stream_text(self, text):
        """ dodawanie fragmentu tekstu do edytora w czasie rzeczywistym """
        self.text_area.config(state="normal")
        self.text_area.insert(tk.END, text)
        self.text_area.see(tk.END)
        self.text_area.config(state="disabled") # blokada powraca na czas trwania procesu


    def _single_finished(self, success, content):
        """ aktualizacja GUI po zakończeniu pracy wątku """
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.is_transcribing = False
        self.btn_ai.config(state="normal", text="Gemini")
        self.text_area.config(state="normal")

        if success:
            # zapisywanie finalnej wersji po zakończeniu strumieniowania
            self.save_current_text(True)
            messagebox.showinfo(self.t["msg_csv_ok_title"],
                                self.t["msg_transcription_ok"],
                                parent=self.root)
            self.root.focus_set()
        else:
            messagebox.showerror(self.t["msg_transcription_error_title"],
                                 f"Info:\n{content}",
                                 parent=self.root)
            self.root.focus_set()


    def edit_current_prompt(self):
        """ Otwiera okno edycji aktualnego promptu """
        if not self.current_prompt_path or not os.path.exists(self.current_prompt_path):
            messagebox.showwarning(self.t["msg_edit_prompt_error_title"],
                                   self.t["msg_edit_prompt_error_text"], parent=self.root)
            return

        # okno edytora
        edit_win = tk.Toplevel(self.root)
        edit_win.title(self.t["edit_win_title"] + f": {os.path.basename(self.current_prompt_path)}")
        edit_win.geometry("850x600")
        edit_win.transient(self.root)

        # panel na przyciski
        btn_frame = ttk.Frame(edit_win)
        btn_frame.pack(side=BOTTOM, fill=X, pady=15)

        def save_prompt_changes():
            """ zapis zmodyfikowanego promptu na dysku """
            new_content = txt_edit.get(1.0, tk.END).strip()
            if not new_content:
                messagebox.showwarning(self.t["msg_error_title"],
                                       self.t["msg_save_prompt_empty"],
                                       parent=edit_win)
                return

            try:
                with open(self.current_prompt_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                self.prompt_text = new_content
                messagebox.showinfo(self.t["msg_save_prompt_title"],
                                    self.t["msg_save_prompt_text"],
                                    parent=edit_win)
                edit_win.destroy()
            except Exception as e:
                messagebox.showerror(self.t["msg_save_prompy_error_title"],
                                     str(e), parent=edit_win)

        def restore_from_file():
            """ przywrócenie pierwotnej wersji promptu z pliku """
            if messagebox.askyesno(self.t["msg_prompt_restore_title"],
                                   self.t["msg_prompt_restore_text"],
                                   parent=edit_win):
                try:
                    with open(self.current_prompt_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    txt_edit.delete(1.0, tk.END)
                    txt_edit.insert(tk.END, content)
                except Exception as e:
                    messagebox.showerror(self.t["msg_error_title"],
                                         self.t["msg_prompt_restore_error"] + f": {e}", parent=edit_win)

        def on_close_prompt_edit():
            """ funkcja sprawdzająca zmiany przy zamykaniu okna """
            current_content = txt_edit.get(1.0, tk.END).strip()
            # porównanie z tekstem zapisanym w pamięci aplikacji
            if current_content != self.prompt_text.strip():
                if messagebox.askyesno(self.t["msg_on_close_title"],
                                       self.t["msg_on_close_text"],
                                       parent=edit_win):
                    edit_win.destroy()
            else:
                edit_win.destroy()

        edit_win.protocol("WM_DELETE_WINDOW", on_close_prompt_edit)

        # przycisk zapisu
        btn_save = ttk.Button(btn_frame, text=self.t["btn_save_prompt"],
                              command=save_prompt_changes, bootstyle="success")
        btn_save.pack(side=RIGHT, padx=20)

        # przycisk przywracania z dysku
        btn_restore = ttk.Button(btn_frame, text=self.t["btn_restore_prompt"],
                                 command=restore_from_file, bootstyle="outline-secondary")
        btn_restore.pack(side=LEFT, padx=20)

        text_container = ttk.Frame(edit_win)
        text_container.pack(fill=BOTH, expand=True, padx=15, pady=(15, 0))

        scrollbar = ttk.Scrollbar(text_container, orient=VERTICAL)
        scrollbar.pack(side=RIGHT, fill=Y)

        # pole tekstowe
        txt_edit = tk.Text(text_container, font=("Consolas", 11), wrap=WORD, undo=True, yscrollcommand=scrollbar.set)
        txt_edit.insert(tk.END, self.prompt_text)
        txt_edit.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar.config(command=txt_edit.yview)

        txt_edit.focus_set()


# ----------------------------------- MAIN -------------------------------------
if __name__ == "__main__":
    # dostępne motywy: "superhero", "journal" (jasny), "darkly", "solar", "minty"
    app_window = ttk.Window(themename="journal", className="ScansAndTranscriptions")
    app = ManuscriptEditor(app_window)
    app_window.mainloop()
