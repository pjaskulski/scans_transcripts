""" przeglądarka skanów i transkrypcji """
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from docx import Document


class ManuscriptEditor:
    """ główna klasa aplikacji """
    def __init__(self, root):
        self.root = root
        self.root.title("Przeglądarka Skanów i Transkrypcji")
        self.root.geometry("1600x900")

        self.file_pairs = []
        self.current_index = 0
        self.original_image = None
        self.tk_image = None
        self.scale = 1.0
        self.img_x = 0
        self.img_y = 0
        self.last_mouse_x = 0
        self.last_mouse_y = 0

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

        # pasek statusu pod obrazem
        self.zoom_label = ttk.Label(self.left_frame, text="Zoom: 100%", font=("Segoe UI", 9))
        self.zoom_label.pack(side=RIGHT, pady=5)
        ttk.Label(self.left_frame,
                  text="LPM: Przesuwanie | Scroll: Zoom",
                  font=("Segoe UI", 8), bootstyle="secondary").pack(side=LEFT, pady=5)

        # prawy panel (na edytor transkrypcji)
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame, weight=1)

        # ramka na tekst
        self.editor_frame = ttk.Labelframe(self.right_frame,
                                           text="Transkrypcja",
                                           bootstyle="warning")
        self.editor_frame.pack(fill=BOTH, expand=True, padx=(5,0))

        # informacja o pliku
        self.file_info_var = tk.StringVar(value="Brak pliku")
        ttk.Label(self.editor_frame,
                  textvariable=self.file_info_var,
                  font=("Segoe UI", 10, "bold"),
                  bootstyle="inverse-light").pack(fill=X, padx=5, pady=5)

        # pole tekstowe z paskiem przewijania
        self.text_scroll = ttk.Scrollbar(self.editor_frame, orient=VERTICAL)
        self.text_area = tk.Text(self.editor_frame, font=("Consolas", 12), wrap=WORD, undo=True,
                                 bg="#333333", fg="white", insertbackground="white",
                                 yscrollcommand=self.text_scroll.set, bd=0, width=1)

        self.text_scroll.config(command=self.text_area.yview)
        self.text_scroll.pack(side=RIGHT, fill=Y)
        self.text_area.pack(side=LEFT, fill=BOTH, expand=True, padx=5, pady=5)

        # pasek narzędzi
        self.toolbar = ttk.Frame(self.right_frame, padding=10)
        self.toolbar.pack(fill=X)

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


        # skróty klawiszowe
        self.root.bind("<Control-s>", lambda e: self.save_current_text())
        self.root.bind("<Alt-Left>", lambda e: self.prev_file())
        self.root.bind("<Alt-Right>", lambda e: self.next_file())
        self.root.bind("<Control-q>", lambda e: self.on_close())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.select_folder()


    def select_folder(self):
        """ wybór folderu """
        folder_path = filedialog.askdirectory(title="Wybierz folder ze skanami")
        if folder_path:
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
                messagebox.showinfo("Info", "Brak obrazów w folderze.")
                return

            self.current_index = 0
            self.load_pair(0)
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można odczytać folderu: {e}")


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
        if not self.original_image:
            return
        w, h = int(self.original_image.width * self.scale), int(self.original_image.height * self.scale)
        try:
            resized = self.original_image.resize((w, h), Image.Resampling.BILINEAR)
            self.tk_image = ImageTk.PhotoImage(resized)
            self.canvas.delete("all")
            self.canvas.create_image(self.img_x, self.img_y, image=self.tk_image, anchor="nw")
            self.zoom_label.config(text=f"Zoom: {int(self.scale * 100)}%")
        except Exception as e:
            print(f"Błąd rysowania: {e}")


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
        Zapis bieżącej zawartości pola tekstowego w pliku.
        Parametr 'silent=True' wyłącza 'mruganie' etykietą (przy przełączaniu stron).
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
            messagebox.showerror("Błąd zapisu", str(e))


    def refresh_label_safely(self, expected_index):
        """ pomocnicza funkcja przywracająca czystą nazwę pliku po zniknięciu komunikatu """
        if self.current_index == expected_index and self.file_pairs:
            pair = self.file_pairs[self.current_index]
            self.file_info_var.set(f"[{self.current_index + 1}/{len(self.file_pairs)}] {pair['name']}")


    def first_file(self):
        """ przejście do pierwszego pliku """
        self.save_current_text(silent=True)
        if self.current_index != 0:
            self.current_index = 0
            self.load_pair(self.current_index)


    def next_file(self):
        """ przejście do następnego pliku """
        self.save_current_text(silent=True)
        if self.current_index < len(self.file_pairs) - 1:
            self.current_index += 1
            self.load_pair(self.current_index)


    def prev_file(self):
        """ przejście do poprzedniego pliku """
        self.save_current_text(silent=True)
        if self.current_index > 0:
            self.current_index -= 1
            self.load_pair(self.current_index)


    def last_file(self):
        """ przejście do ostatniego pliku """
        self.save_current_text(silent=True)
        if self.current_index < len(self.file_pairs) - 1:
            self.current_index = len(self.file_pairs) - 1
            self.load_pair(self.current_index)


    def export_all_data(self):
        """ eksportuje wszystkie transkrypcje do jednego pliku txt """
        self.save_current_text(silent=True)

        if not self.file_pairs:
            messagebox.showwarning("Brak danych", "Brak plików do eksportu.")
            return

        target_path = filedialog.asksaveasfilename(
            title="Wybierz miejsce zapisu scalonej transkrypcji",
            defaultextension=".txt",
            filetypes=[("Plik tekstowy", "*.txt")]
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
                                f"Pomyślnie wyeksportowano {len(merged_content)} fragmentów do pliku:\n{os.path.basename(target_path)}")

        except Exception as e:
            messagebox.showerror("Błąd eksportu", f"Wystąpił błąd podczas zapisu:\n{e}")


    def export_all_data_docx(self):
        """ Eksport do DOCX z łączeniem wyrazów """
        self.save_current_text(True)
        if not self.file_pairs:
            return

        path = filedialog.asksaveasfilename(defaultextension=".docx",
                                            filetypes=[("Word Document", "*.docx")])
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
                                f"Utworzono plik DOCX:\n{os.path.basename(path)}")

        except Exception as e:
            messagebox.showerror("Błąd eksportu", str(e))


    def on_close(self):
        """ bezpieczne zamknięcie aplikacji z zapisem """
        try:
            self.save_current_text(silent=True)
        except Exception as e:
            print(e)

        self.root.destroy()


# ----------------------------------- MAIN -------------------------------------
if __name__ == "__main__":
    # dostępne motywy: "superhero", "journal" (jasny), "darkly", "solar", "minty"
    app_window = ttk.Window(themename="journal")
    app = ManuscriptEditor(app_window)
    app_window.mainloop()
