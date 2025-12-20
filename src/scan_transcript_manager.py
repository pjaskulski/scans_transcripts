""" przeglądarka skanów i transkrypcji """
import os
import json
import threading
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageOps, ImageEnhance
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.widgets.scrolled import ScrolledFrame
from docx import Document
from dotenv import load_dotenv
from google import genai
from google.genai import types
from gtts import gTTS
from just_playback import Playback


# ------------------------------- CLASS ----------------------------------------
class ManuscriptEditor:
    """ główna klasa aplikacji """
    def __init__(self, root):
        self.root = root
        self.root.title("Przeglądarka Skanów i Transkrypcji")
        self.root.geometry("1600x900")

        self.api_key = ""
        self.prompt_text = ""
        self.prompt_filename_var = tk.StringVar(value="Brak (wybierz plik)")
        self.current_folder_var = tk.StringVar(value="Nie wybrano katalogu")
        self.current_prompt_path = None

        self._init_environment()

        self.config_file = "config.json"
        self.font_family = "Consolas"
        self.font_size = 12

        # języki TTS
        self.tts_languages = {
            "Polski": "pl",
            "Łacina": "la",
            "Angielski": "en",
            "Niemiecki": "de",
            "Francuski": "fr",
            "Hiszpański": "es",
            "Portugalski": "pt",
            "Rosyjski": "ru"
        }
        self.current_tts_lang_code = "pl" # domyślny

        self.load_config()

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

        # główny kontener
        self.paned = ttk.Panedwindow(root, orient=HORIZONTAL)
        self.paned.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # lewy panel (na obraz)
        self.left_frame = ttk.Frame(self.paned)
        self.paned.add(self.left_frame, weight=3)

        # ramka na canvas z obramowaniem
        self.canvas_frame = ttk.Labelframe(self.left_frame, text="Skan", bootstyle="info")
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

        # pasek statusu pod obrazem
        self.image_tools = ttk.Frame(self.left_frame)
        self.image_tools.pack(fill=X, pady=5)

        # lewa strona paska (Instrukcja + Zoom info)
        left_tools = ttk.Frame(self.image_tools)
        left_tools.pack(side=LEFT)

        self.zoom_label = ttk.Label(left_tools, text="Zoom: 100%", font=("Segoe UI", 9, "bold"))
        self.zoom_label.pack(side=LEFT, pady=5)
        ttk.Label(left_tools,
                  text="LPM: Przesuwanie | Scroll: Zoom | RPM: okno lupy",
                  font=("Segoe UI", 8), bootstyle="secondary").pack(side=LEFT, pady=5, padx=10)

        # prawa strona paska
        tools_frame = ttk.Frame(self.image_tools)
        tools_frame.pack(side=RIGHT)

        ttk.Label(tools_frame, text="Filtry: ", font=("Segoe UI", 8)).pack(side=LEFT)
        ttk.Button(tools_frame, text="Reset", command=lambda: self.apply_filter("normal"),
                   bootstyle="outline-secondary", padding=2).pack(side=LEFT, padx=1)
        ttk.Button(tools_frame, text="Kontrast", command=lambda: self.apply_filter("contrast"),
                   bootstyle="outline-info", padding=2).pack(side=LEFT, padx=1)
        ttk.Button(tools_frame, text="Negatyw", command=lambda: self.apply_filter("invert"),
                   bootstyle="outline-dark", padding=2).pack(side=LEFT, padx=(1,5))

        # prawy panel (na edytor transkrypcji)
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame, weight=1)

        # pasek ścieżki do Katalogu
        self.folder_status_frame = ttk.Frame(self.right_frame)
        self.folder_status_frame.pack(fill=X, padx=5, pady=(0, 5))

        ttk.Label(self.folder_status_frame, text="Katalog:",
                  font=("Segoe UI", 8, "bold")).pack(side=LEFT)

        # etykieta ze ścieżką
        ttk.Label(self.folder_status_frame, textvariable=self.current_folder_var,
                  font=("Segoe UI", 8), bootstyle="dark").pack(side=LEFT, padx=5)

        # przycisk zmiany folderu ze skanami
        ttk.Button(self.folder_status_frame, text="[ZMIEŃ]", command=self.select_folder,
                   bootstyle="link-secondary", cursor="hand2", padding=0).pack(side=RIGHT)

        # ramka na tekst
        self.editor_frame = ttk.Labelframe(self.right_frame,
                                           text="Transkrypcja",
                                           bootstyle="primary")
        self.editor_frame.pack(fill=BOTH, expand=True, padx=(5,0))

        self.editor_header = ttk.Frame(self.editor_frame)
        self.editor_header.pack(fill=X, padx=5, pady=5)

        # informacja o pliku
        self.file_info_var = tk.StringVar(value="Brak pliku")
        ttk.Label(self.editor_header,
                  textvariable=self.file_info_var,
                  font=("Segoe UI", 10, "bold"),
                  bootstyle="inverse-light").pack(side=LEFT, fill=X, expand=True)

        # Kontener na przyciski narzędziowe edytora
        editor_tools = ttk.Frame(self.editor_header)
        editor_tools.pack(side=RIGHT)

        # przycisk NER (podświetlanie nazw własnych)
        self.btn_ner = ttk.Button(editor_tools, text="NER", command=self.start_ner_analysis,
                                  bootstyle="success-outline", width=3, padding=2)
        self.btn_ner.pack(side=LEFT, padx=(3,3))

        # wybór języka (Combobox)
        self.lang_combobox = ttk.Combobox(editor_tools, values=list(self.tts_languages.keys()), state="readonly", width=10, bootstyle="info")

        # ustawienie wartości początkowej na podstawie kodu (np. 'pl' -> 'Polski')
        initial_lang_name = [k for k, v in self.tts_languages.items() if v == self.current_tts_lang_code]
        if initial_lang_name:
            self.lang_combobox.set(initial_lang_name[0])
        else:
            self.lang_combobox.set("Polski")

        self.lang_combobox.bind("<<ComboboxSelected>>", self.change_tts_language)
        self.lang_combobox.pack(side=LEFT, padx=2)

        # przycisk startu
        self.btn_speak = ttk.Button(editor_tools, text="▶", command=self.read_text_aloud,
                                    bootstyle="info-outline", width=3, padding=2)
        self.btn_speak.pack(side=LEFT, padx=2)

        # przycisk pauzy - domyślnie wyłączony
        self.btn_pause = ttk.Button(editor_tools, text="||", command=self.pause_reading,
                                    bootstyle="info-outline", width=3, padding=2, state="disabled")
        self.btn_pause.pack(side=LEFT, padx=2)

        # przycisk stopu
        self.btn_stop = ttk.Button(editor_tools, text="■", command=self.stop_reading,
                                   bootstyle="info-outline", width=3, padding=2, state="disabled")
        self.btn_stop.pack(side=LEFT, padx=2)

        ttk.Separator(editor_tools, orient=VERTICAL).pack(side=LEFT, padx=5, fill=Y)

        # Sekcja Fontu
        ttk.Button(editor_tools, text="A-", command=lambda: self.change_font_size(-1),
                   bootstyle="outline-secondary", width=3, padding=2).pack(side=LEFT, padx=2)
        ttk.Button(editor_tools, text="A+", command=lambda: self.change_font_size(1),
                   bootstyle="outline-secondary", width=3, padding=2).pack(side=LEFT, padx=2)

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

        # konfiguracja stylu podświetlenia dla NER (żółte tło)
        self.text_area.tag_configure("entity_highlight", background="#ffcc00", foreground="black")

        # powiązanie dowolnego klawisza z usunięciem podświetleń
        #self.text_area.bind("<KeyPress>", self._on_text_modified)

        # pasek narzędzi
        self.toolbar = ttk.Frame(self.right_frame, padding=(0, 10, 0, 5))
        self.toolbar.pack(fill=X, padx=(5,0))

        # przyciski
        ttk.Button(self.toolbar,
                   text="|<",
                   command=self.first_file,
                   bootstyle="outline-secondary").pack(side=LEFT, fill=X, expand=True, padx=2)

        ttk.Button(self.toolbar,
                   text="<<",
                   command=self.prev_file,
                   bootstyle="outline-secondary").pack(side=LEFT, fill=X, expand=True, padx=2)

        ttk.Button(self.toolbar,
                   text="ZAPISZ",
                   command=self.save_current_text,
                   bootstyle="success").pack(side=LEFT, fill=X, expand=True, padx=5)

        # Gemini
        frame_ai = ttk.Frame(self.toolbar)
        frame_ai.pack(side=LEFT, fill=X, expand=True)

        self.btn_ai = ttk.Button(frame_ai,
                                 text="Gemini",
                                 command=self.start_ai_transcription,
                                 bootstyle="danger")
        self.btn_ai.pack(side=LEFT, fill=X, expand=True, padx=2)

        # Gemini seria
        ttk.Button(frame_ai, text="Seria", command=self.open_batch_dialog,
                   bootstyle="danger").pack(side=LEFT, fill=X, expand=True, padx=2)

        # zapis wyników
        ttk.Button(self.toolbar,
                   text="TXT",
                   command=self.export_all_data,
                   bootstyle="info").pack(side=LEFT, fill=X, expand=True, padx=5)

        ttk.Button(self.toolbar,
                   text="DOCX",
                   command=self.export_all_data_docx,
                   bootstyle="info").pack(side=LEFT, fill=X, expand=True, padx=5)

        ttk.Button(self.toolbar,
                   text=">|",
                   command=self.last_file,
                   bootstyle="outline-secondary").pack(side=RIGHT, fill=X, expand=True, padx=2)

        ttk.Button(self.toolbar,
                   text=">>",
                   command=self.next_file,
                   bootstyle="outline-secondary").pack(side=RIGHT, fill=X, expand=True, padx=2)


        # pasek stanu promptu
        self.prompt_status_frame = ttk.Frame(self.right_frame, bootstyle="light")
        self.prompt_status_frame.pack(fill=X, padx=(5,0), pady=(0, 5))

        # etykieta z nazwą bieżącego promptu (pliku z promptem)
        ttk.Label(self.prompt_status_frame, text="Prompt:",
                  font=("Segoe UI", 8, "bold")).pack(side=LEFT)

        ttk.Label(self.prompt_status_frame, textvariable=self.prompt_filename_var,
                  font=("Segoe UI", 8), bootstyle="dark").pack(side=LEFT, padx=(5,5), pady=2)

        # przycisk zmiany promptu
        ttk.Button(self.prompt_status_frame, text="[ZMIEŃ]", command=self.select_prompt_file,
                   bootstyle="link-secondary", cursor="hand2", padding=0).pack(side=RIGHT, padx=5)

        # przycisk edycji promptu
        self.btn_edit_prompt = ttk.Button(self.prompt_status_frame, text="[EDYTUJ]",
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

        self.select_folder()


    def _on_text_modified(self, event):
        """
        automatyczne usuwanie podświetlenia nazw własnych przy edycji tekstu
        """
        # usuwanie tagów tylko jeśli faktycznie istnieją w edytorze
        if self.text_area.tag_ranges("entity_highlight"):
            self.text_area.tag_remove("entity_highlight", "1.0", tk.END)

    def start_ner_analysis(self):
        """
        inicjacja procesu ekstrakcji nazw własnych w osobnym wątku
        """
        text = self.text_area.get(1.0, tk.END).strip()
        if not text or self.is_transcribing:
            return

        self.btn_ner.config(state="disabled")
        self.text_area.tag_remove("entity_highlight", "1.0", tk.END)

        # wykorzystanie wątku zapobiega zawieszeniu interfejsu
        thread = threading.Thread(target=self._ner_worker, args=(text,), daemon=True)
        thread.start()

    def _ner_worker(self, text):
        """
        dodatkowa analiza tekstu przez Gemini w celu uzyskania listy nazw własnych
        """
        try:
            client = genai.Client(api_key=self.api_key)

            prompt = (
                "Z poniższego tekstu wypisz wyłącznie nazwy własne (osoby, miejscowości, instytucje). "
                "Zwróć je jako listę słów oddzielonych przecinkami, bez żadnego dodatkowego komentarza, "
                "w takiej formie w jakiej występują w tekście. "
                "Tekst: " + text
            )

            config = types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )

            response = client.models.generate_content(
                model="gemini-flash-latest", # gemini-flash-lite-latest lub gemini-flash-latest
                contents=prompt,
                config=config
            )

            if response.text:
                # przekształcenie odpowiedzi na listę unikalnych fraz
                entities = [e.strip() for e in response.text.split(",") if len(e.strip()) > 2]
                self.root.after(0, self._apply_ner_highlights, entities)

        except Exception as e:
            print(f"Błąd NER: {e}")
        finally:
            self.root.after(0, lambda: self.btn_ner.config(state="normal"))

    def _apply_ner_highlights(self, entities):
        """
        podświetlenie nazw własnych w tekście w edytorze
        """
        for entity in entities:
            start_pos = "1.0"
            while True:
                # wyszukiwanie frazy bez względu na wielkość liter
                start_pos = self.text_area.search(entity, start_pos, stopindex=tk.END, nocase=True)
                if not start_pos:
                    break

                # obliczanie zakresu i nakładanie tagu
                end_pos = f"{start_pos}+{len(entity)}c"
                self.text_area.tag_add("entity_highlight", start_pos, end_pos)
                start_pos = end_pos

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
        """ kod wykonywany w wątku - tworzenie audio i start odtwarzania """
        try:
            lang_to_use = self.current_tts_lang_code

            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, "manuscript_tts_temp.mp3")

            tts = gTTS(text=text, lang=lang_to_use)
            tts.save(temp_path)

            if self.is_reading_audio:
                self.playback.load_file(temp_path)
                self.playback.play()

                # odblokowanie pauzy po rozpoczęciu odtwarzania
                self.root.after(0, lambda: self.btn_pause.config(state="normal"))
                self.root.after(100, self._check_audio_status)

        except Exception as e:
            print(f"Błąd TTS: {e}")
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


    def load_config(self):
        """ wczytywanie ustawień z pliku JSON """
        config_path = Path('..') / 'config' / self.config_file
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.font_size = config.get("font_size", 12)
                    self.current_tts_lang_code = config.get("tts_lang", "pl") # wczytanie języka

                    # optional api key in config file
                    if not self.api_key:
                        self.api_key = config.get("api_key", "")
            except Exception as e:
                print(f"Błąd wczytywania pliku konfiguracyjnego: {e}")


    def save_config(self):
        """ zapisywanie ustawienia do pliku JSON """
        config_path = Path('..') / 'config' / self.config_file
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                config["font_size"] = self.font_size
        else:
            config = {
                "font_size": self.font_size,
                "tts_lang": self.current_tts_lang_code,
                "api_key": ""
            }

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f)
        except Exception as e:
            print(f"Błąd zapisu pliku konfiguracyjnego: {e}")


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

        self.api_key = os.environ.get("GEMINI_API_KEY")

        self.prompt_filename_var.set("Brak (wybierz plik)")

        default_prompt = "prompt_handwritten_pol_xx_century.txt"
        prompt_path = Path('..') / "prompt" / default_prompt
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    self.prompt_text = f.read()
                self.prompt_filename_var.set(f"{default_prompt}")
                self.current_prompt_path = str(prompt_path)
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można wczytać {default_prompt}: {e}", parent=self.root)
        else:
            messagebox.showerror("Przed użyciem Gemini wskaż plik z promptem.", str(e), parent=self.root)


    def select_folder(self):
        """ wybór folderu """
        if self.is_transcribing:
            return

        initial_dir = os.getcwd() # domyślnie bieżący katalog

        folder_path = filedialog.askdirectory(
            title="Wybierz folder ze skanami",
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
                messagebox.showinfo("Info", "Brak skanów w folderze.", parent=self.root)
                self.original_image = None
                self.processed_image = None
                self.canvas.delete("all")
                self.text_area.delete(1.0, tk.END)
                self.file_info_var.set("Brak plików")
                return

            self.current_index = 0
            self.load_pair(0)
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można odczytać folderu: {e}", parent=self.root)


    def load_pair(self, index):
        """ ładowanie par plików: skan i transkrypcja """
        if not self.file_pairs:
            return
        pair = self.file_pairs[index]

        # aktualizacja nagłówka
        self.file_info_var.set(f"[{index + 1}/{len(self.file_pairs)}] {pair['name']}")

        # skan
        try:
            self.original_image = Image.open(pair['img'])
            self.processed_image = self.original_image.copy()
            self.active_filter = "normal"
            self.scale = 1.0
            # skalowanie jeśli obraz jest bardzo duży
            if self.original_image.width > 1400:
                self.scale = 1400 / self.original_image.width

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
            print(f"Błąd rysowania: {e}")


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
            messagebox.showerror("Błąd promptu", f"Nie można wczytać pliku:\n{e}", parent=self.root)
            return False


    def select_prompt_file(self):
        """ okno dialogowe wyboru pliku promptu """
        prompt_path = Path('..') / 'prompt'
        filename = filedialog.askopenfilename(
            title="Wybierz plik z promptem",
            initialdir=prompt_path,
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")],
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
                if "[ZAPISANO!]" not in original_text:
                    self.file_info_var.set(original_text + " [ZAPISANO!]")
                    self.root.after(1000, lambda: self.refresh_label_safely(self.current_index))

        except Exception as e:
            messagebox.showerror("Błąd zapisu", str(e), parent=self.root)


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
            messagebox.showwarning("Brak danych", "Brak plików do eksportu.", parent=self.root)
            return

        target_path = filedialog.asksaveasfilename(
            title="Wybierz miejsce zapisu scalonego pliku TXT",
            defaultextension=".txt",
            filetypes=[("Plik tekstowy", "*.txt")],
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

            messagebox.showinfo("Sukces",
                                f"Utworzono plik:\n{os.path.basename(target_path)}", parent=self.root)

        except Exception as e:
            messagebox.showerror("Błąd eksportu", f"Wystąpił błąd podczas zapisu:\n{e}", parent=self.root)


    def export_all_data_docx(self):
        """ eksport do pliku docx z łączeniem wyrazów """
        self.save_current_text(True)
        if not self.file_pairs:
            return

        path = filedialog.asksaveasfilename(
            title="Wybierz miejsce zapisu scalonego pliku DOCX",
            defaultextension=".docx",
            filetypes=[("dokument Word", "*.docx")],
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

            messagebox.showinfo("Sukces",
                                f"Utworzono plik DOCX:\n{os.path.basename(path)}", parent=self.root)

        except Exception as e:
            messagebox.showerror("Błąd eksportu", str(e), parent=self.root)


    def on_close(self):
        """ bezpieczne zamknięcie aplikacji z zapisem """
        try:
            self.save_current_text(silent=True)
        except Exception as e:
            print(e)

        self.root.destroy()


    def show_magnifier(self, event):
        """ wyświetlanie lupę (okno powiększające) w miejscu kursora """
        src = self.processed_image if self.processed_image else self.original_image
        if not src:
            return

        # ustawienia lupy
        MAG_WIDTH, MAG_HEIGHT = 750, 300  # rozmiar okna lupy
        ZOOM_FACTOR = 2.0                 # powiększenie względem oryginału (200%)

        # współrzędne kliknięcia względem oryginalnego obrazu
        # event.x/y -  współrzędne na canvas
        # self.img_x/y -  przesunięcie obrazu (panning)
        # self.scale - aktualny zoom głównego widoku

        # pozycja pixela oryginału
        orig_x = (event.x - self.img_x) / self.scale
        orig_y = (event.y - self.img_y) / self.scale

        # obszar do wycięcia z oryginału
        crop_w = MAG_WIDTH / ZOOM_FACTOR
        crop_h = MAG_HEIGHT / ZOOM_FACTOR

        x1 = orig_x - (crop_w / 2)
        y1 = orig_y - (crop_h / 2)
        x2 = x1 + crop_w
        y2 = y1 + crop_h

        try:
            # wycięcie i przeskalowanie
            region = src.crop((x1, y1, x2, y2))

            # skalowanie do rozmiaru okna lupy
            magnified_img = region.resize((MAG_WIDTH, MAG_HEIGHT), Image.Resampling.BILINEAR)
            tk_mag_img = ImageTk.PhotoImage(magnified_img)

            # okno lupy
            top = tk.Toplevel(self.root)
            top.transient(self.root) # info dla menedżera okien, że okno jest "pomocnicze" dla głównego
            top.overrideredirect(True) # usunięcie belki tytułowej i ramek

            # pozycjonowanie okna - wycentrowane na kursorze
            pos_x = int(event.x_root - (MAG_WIDTH / 2))
            pos_y = int(event.y_root - (MAG_HEIGHT / 2))
            top.geometry(f"{MAG_WIDTH}x{MAG_HEIGHT}+{pos_x}+{pos_y}")

            frame = ttk.Frame(top, bootstyle="info", padding=2)
            frame.pack(fill=BOTH, expand=True)

            # etykieta z obrazem
            label = ttk.Label(frame, image=tk_mag_img, background="white")
            label.image = tk_mag_img # zachowanie referencji
            label.pack(fill=BOTH, expand=True)

            # zamykanie lupy
            def close_magnifier(_=None):
                top.destroy()

            # przejęcie focusu, aby zadziałał Esc i FocusOut
            top.focus_set()

            # zamknięcie przy kliknięciu lewym przyciskiem myszy wewnątrz,
            # Esc, lub utracie fokusu (klik na zewnątrznej kontrolce np. polu tekstowym)
            top.bind("<Button-1>", close_magnifier)
            top.bind("<Escape>", close_magnifier)
            top.bind("<FocusOut>", close_magnifier)

        except Exception as e:
            print(f"Błąd lupy: {e}")


    def open_batch_dialog(self):
        """ otwiera okno dialogowe do przetwarzania seryjnego """
        if self.is_transcribing:
            messagebox.showwarning("Uwaga", "Trwa przetwarzanie. Poczekaj na zakończenie.", parent=self.root)
            return

        if not self.file_pairs:
            messagebox.showinfo("Brak plików", "Brak plików do przetworzenia.", parent=self.root)
            return

        # tworzenie okna dialogowego
        batch_win = tk.Toplevel(self.root)
        batch_win.title("Przetwarzanie Seryjne")
        batch_win.geometry("700x700")
        batch_win.transient(self.root)

        # nagłówek
        ttk.Label(batch_win, text="Wybierz pliki do transkrypcji:", font=("Segoe UI", 12, "bold")).pack(pady=10)
        ttk.Label(batch_win, text="Zaznaczono domyślnie pliki bez transkrypcji lub puste.",
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
                status_text = "(brak txt)"
            elif os.path.getsize(txt_path) == 0:
                should_select = True
                status_text = "(pusty plik)"
            else:
                status_text = "(gotowy)"

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
        self.batch_log_label = ttk.Label(batch_win, text="Oczekiwanie na start...", bootstyle="inverse-secondary")
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
                messagebox.showwarning("Info", "Nie wybrano żadnych plików.", parent=batch_win)
                return

            # blokada przycisków
            btn_start.config(state="disabled")

            # uruchomienie wątku
            self.is_transcribing = True
            thread = threading.Thread(target=self._batch_worker, args=(selected_indices, batch_win, btn_start))
            thread.daemon = True
            thread.start()

        ttk.Button(btn_panel, text="Zaznacz wszystkie", command=select_all, bootstyle="outline-secondary").pack(side=LEFT, padx=5)
        ttk.Button(btn_panel, text="Odznacz wszystkie", command=select_none, bootstyle="outline-secondary").pack(side=LEFT, padx=5)

        btn_start = ttk.Button(btn_panel, text="URUCHOM PRZETWARZANIE", command=start_batch, bootstyle="danger")
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
            msg = f"Przetwarzanie [{i+1}/{total}]: {pair['name']}..."

            self.root.after(0, lambda m=msg, v=progress_pct: self._update_batch_ui(m, v))

            try:
                # wywołanie API (ta sama metoda co przy pojedynczym pliku)
                result_text = self._call_gemini_api(img_path)

                # zapis do pliku
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(result_text + '\n')

            except Exception as e:
                errors += 1
                print(f"Błąd przy pliku {pair['name']}: {e}")

        self.is_transcribing = False

        # zakończono
        if window.winfo_exists():
            final_msg = f"Zakończono! Przetworzono: {total}. Błędy: {errors}."
            self.root.after(0, lambda: self._update_batch_ui(final_msg, 100))
            self.root.after(0, lambda: btn_start.config(state="normal"))
            self.root.after(0, lambda: messagebox.showinfo("Koniec", final_msg, parent=window))

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

        model_name = "gemini-3-pro-preview"

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
            model=model_name,
            contents=contents,
            config=generate_content_config
        )

        return response.text


    def start_ai_transcription(self):
        """ inicjuje proces transkrypcji w tle """
        if not self.file_pairs or self.is_transcribing:
            return

        if not self.prompt_text:
            messagebox.showerror("Błąd konfiguracji",
                                 "Brak promptu.",
                                 parent=self.root)
            return

        if not self.api_key:
            messagebox.showerror("Błąd konfiguracji",
                                 "Brak klucza GEMINI_API_KEY w pliku .env lub w config.json",
                                 parent=self.root)
            return

        # blokada interfejsu
        self.is_transcribing = True
        self.btn_ai.config(state="disabled", text="Przetwarzanie...")
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

            model_name = "gemini-3-pro-preview"

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
            for response in client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=generate_content_config
            ):
                if response.text:
                    # przekazanie fragmentu tekstu do aktualizacji UI
                    self.root.after(0, self._append_stream_text, response.text)

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
            messagebox.showinfo("Sukces",
                                "Transkrypcja zakończona pomyślnie.",
                                parent=self.root)
            self.root.focus_set()
        else:
            messagebox.showerror("Błąd transkrypcji",
                                 f"Info:\n{content}",
                                 parent=self.root)
            self.root.focus_set()


    def edit_current_prompt(self):
        """ Otwiera okno edycji aktualnego promptu """
        if not self.current_prompt_path or not os.path.exists(self.current_prompt_path):
            messagebox.showwarning("Brak pliku promptu", "Przed edycją należy wybrać plik promptu.", parent=self.root)
            return

        # okno edytora
        edit_win = tk.Toplevel(self.root)
        edit_win.title(f"Edycja: {os.path.basename(self.current_prompt_path)}")
        edit_win.geometry("850x600")
        edit_win.transient(self.root)

        # panel na przyciski
        btn_frame = ttk.Frame(edit_win)
        btn_frame.pack(side=BOTTOM, fill=X, pady=15)

        def save_prompt_changes():
            """ zapis zmodyfikowanego promptu na dysku """
            new_content = txt_edit.get(1.0, tk.END).strip()
            if not new_content:
                messagebox.showwarning("Błąd", "Prompt nie może być pusty.", parent=edit_win)
                return

            try:
                with open(self.current_prompt_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                self.prompt_text = new_content
                messagebox.showinfo("Zapisano", "Zmiany w prompcie zostały zapisane.", parent=edit_win)
                edit_win.destroy()
            except Exception as e:
                messagebox.showerror("Błąd zapisu", str(e), parent=edit_win)

        def restore_from_file():
            """ przywrócenie pierwotnej wersji promptu z pliku """
            if messagebox.askyesno("Potwierdzenie",
                                   "Wczytać treść promptu z pliku i zastąpić bieżącą zawartość edytora?",
                                   parent=edit_win):
                try:
                    with open(self.current_prompt_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    txt_edit.delete(1.0, tk.END)
                    txt_edit.insert(tk.END, content)
                except Exception as e:
                    messagebox.showerror("Błąd", f"Nie udało się wczytać pliku: {e}", parent=edit_win)

        def on_close_prompt_edit():
            """ funkcja sprawdzająca zmiany przy zamykaniu okna """
            current_content = txt_edit.get(1.0, tk.END).strip()
            # porównanie z tekstem zapisanym w pamięci aplikacji
            if current_content != self.prompt_text.strip():
                if messagebox.askyesno("Niezapisane zmiany",
                                       "Wprowadzone zmiany nie zostały zapisane. Czy na pewno chcesz zamknąć okno i utracić zmiany?",
                                       parent=edit_win):
                    edit_win.destroy()
            else:
                edit_win.destroy()

        edit_win.protocol("WM_DELETE_WINDOW", on_close_prompt_edit)

        # przycisk zapisu
        btn_save = ttk.Button(btn_frame, text="Zapisz", command=save_prompt_changes, bootstyle="success")
        btn_save.pack(side=RIGHT, padx=20)

        # przycisk przywracania z dysku
        btn_restore = ttk.Button(btn_frame, text="Przywróć z pliku",
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
    app_window = ttk.Window(themename="journal", className="ScanTranscript")
    app = ManuscriptEditor(app_window)
    app_window.mainloop()
