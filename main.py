"""
PDF -> UBL-TR E-Arsiv Fatura Donusturucu
Ana uygulama - GUI arayuzu
"""

import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

from pdf_extractor import PDFExtractor
from invoice_parser import InvoiceParser, InvoiceData
from xml_generator import UBLTriGenerator


class App(tk.Tk):

    APP_TITLE = "PDF > UBL-TR E-Arsiv Fatura Donusturucu"
    APP_VERSION = "2.0.0"
    WINDOW_SIZE = "960x700"

    def __init__(self):
        super().__init__()
        self.title(self.APP_TITLE)
        self.geometry(self.WINDOW_SIZE)
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")

        self.pdf_extractor = PDFExtractor()
        self.invoice_parser = InvoiceParser()
        self.xml_generator = UBLTriGenerator()

        self.selected_files = []
        self.output_dir = ""

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"), foreground="#cdd6f4", background="#1e1e2e")
        style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#a6adc8", background="#1e1e2e")
        style.configure("Status.TLabel", font=("Segoe UI", 9), foreground="#a6e3a1", background="#1e1e2e")
        style.configure("Warn.TLabel", font=("Segoe UI", 9), foreground="#f9e2af", background="#1e1e2e")
        style.configure("Error.TLabel", font=("Segoe UI", 9), foreground="#f38ba8", background="#1e1e2e")
        style.configure("Dir.TLabel", font=("Segoe UI", 9), foreground="#89b4fa", background="#1e1e2e")

        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8))
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 6))

        style.configure("Custom.Treeview", font=("Consolas", 9), rowheight=24, background="#313244", foreground="#cdd6f4", fieldbackground="#313244")
        style.configure("Custom.Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#45475a", foreground="#cdd6f4")
        style.map("Custom.Treeview", background=[("selected", "#585b70")], foreground=[("selected", "#f5c2e7")])

        style.configure(".Horizontal.TProgressbar", troughcolor="#313244", background="#a6e3a1", thickness=20)

    def _build_ui(self):
        main = ttk.Frame(self, padding=16)
        main.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="PDF > UBL-TR Donusturucu", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(header, text="E-arsiv fatura PDF dosyalarini UBL-TR XML formatina donusturur", style="Sub.TLabel").pack(anchor=tk.W)

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(btn_frame, text="PDF Dosyalari Sec", style="Accent.TButton", command=self._select_files).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Cikis Klasoru Sec", style="Accent.TButton", command=self._select_output_dir).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Donustur", style="Accent.TButton", command=self._start_conversion).pack(side=tk.LEFT, padx=(0, 8))

        sep = ttk.Separator(btn_frame, orient=tk.VERTICAL)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Button(btn_frame, text="Klasoru Ac", command=self._open_output_dir).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Temizle", command=self._clear_all).pack(side=tk.LEFT)

        self.file_count_label = ttk.Label(btn_frame, text="Secili dosya: 0", style="Sub.TLabel")
        self.file_count_label.pack(side=tk.RIGHT)

        self.dir_label = ttk.Label(main, text="Cikis klasoru: Secilmedi (PDF ile ayni klasor)", style="Dir.TLabel")
        self.dir_label.pack(fill=tk.X, pady=(0, 8))

        paned = ttk.PanedWindow(main, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        top_frame = ttk.Frame(paned)
        paned.add(top_frame, weight=2)

        tree_frame = ttk.Frame(top_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("dosya", "fatura_no", "tarih", "satici", "alici", "brut_toplam", "kalem", "durum")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", style="Custom.Treeview", selectmode="extended")

        col_config = [
            ("dosya", "Dosya", 140),
            ("fatura_no", "Fatura No", 150),
            ("tarih", "Tarih", 80),
            ("satici", "Satici", 140),
            ("alici", "Alici", 140),
            ("brut_toplam", "Brut Toplam", 100),
            ("kalem", "Kalem", 50),
            ("durum", "Durum", 90),
        ]
        for cid, heading, width in col_config:
            self.tree.heading(cid, text=heading)
            self.tree.column(cid, width=width, minwidth=50)

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        bottom_frame = ttk.Frame(paned)
        paned.add(bottom_frame, weight=1)

        log_header = ttk.Frame(bottom_frame)
        log_header.pack(fill=tk.X, pady=(4, 2))
        ttk.Label(log_header, text="Islem Gunlugu", style="Sub.TLabel").pack(side=tk.LEFT)

        self.log_text = tk.Text(
            bottom_frame, height=8, font=("Consolas", 9),
            bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4",
            wrap=tk.WORD, state=tk.DISABLED, relief=tk.FLAT, padx=8, pady=4,
        )
        log_scroll = ttk.Scrollbar(bottom_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text.tag_configure("info", foreground="#a6adc8")
        self.log_text.tag_configure("success", foreground="#a6e3a1")
        self.log_text.tag_configure("warning", foreground="#f9e2af")
        self.log_text.tag_configure("error", foreground="#f38ba8")
        self.log_text.tag_configure("header", foreground="#89b4fa", font=("Consolas", 9, "bold"))

        progress_frame = ttk.Frame(main)
        progress_frame.pack(fill=tk.X, pady=(8, 0))

        self.progress = ttk.Progressbar(progress_frame, mode="determinate", style="Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X, pady=(0, 4))

        self.status_label = ttk.Label(progress_frame, text="Hazir - PDF dosyalari secin", style="Status.TLabel")
        self.status_label.pack(anchor=tk.W)

    def _select_files(self):
        files = filedialog.askopenfilenames(
            title="E-arsiv fatura PDF dosyalarini secin",
            filetypes=[("PDF Dosyalari", "*.pdf"), ("Tum Dosyalar", "*.*")],
        )
        if files:
            self.selected_files = list(files)
            self.file_count_label.configure(text=f"Secili dosya: {len(files)}")
            self._log(f"{len(files)} dosya secildi", "info")
            for f in files:
                self._log(f"  >> {os.path.basename(f)}", "info")

    def _select_output_dir(self):
        d = filedialog.askdirectory(title="XML dosyalarinin kaydedilecegi klasoru secin")
        if d:
            self.output_dir = d
            self.dir_label.configure(text=f"Cikis klasoru: {d}")
            self._log(f"Cikis klasoru: {d}", "info")

    def _open_output_dir(self):
        target = self.output_dir
        if not target:
            if self.selected_files:
                target = os.path.dirname(self.selected_files[0])
            else:
                messagebox.showinfo("Bilgi", "Once bir cikis klasoru veya PDF dosyasi secin.")
                return
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])

    def _clear_all(self):
        self.selected_files = []
        self.output_dir = ""
        self.file_count_label.configure(text="Secili dosya: 0")
        self.dir_label.configure(text="Cikis klasoru: Secilmedi (PDF ile ayni klasor)")
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.progress["value"] = 0
        self.status_label.configure(text="Temizlendi", style="Status.TLabel")
        self._log("Liste temizlendi", "info")

    def _start_conversion(self):
        if not self.selected_files:
            messagebox.showwarning("Uyari", "Lutfen once PDF dosyasi secin.")
            return
        thread = threading.Thread(target=self._convert_all, daemon=True)
        thread.start()

    def _convert_all(self):
        total = len(self.selected_files)
        self.after(0, lambda: self.progress.configure(maximum=total, value=0))

        success_count = 0
        error_count = 0

        self._log("", "info")
        self._log("=" * 55, "header")
        self._log(f"DONUSURME BASLADI - {total} dosya", "header")
        self._log("=" * 55, "header")

        for idx, pdf_path in enumerate(self.selected_files, 1):
            filename = os.path.basename(pdf_path)
            self._set_status(f"Isleniyor ({idx}/{total}): {filename}")

            try:
                pdf_data = self.pdf_extractor.extract_all(pdf_path)
                text = pdf_data["text"]
                tables = pdf_data["tables"]
                invoice = self.invoice_parser.parse(text, source_file=pdf_path, tables=tables)

                if invoice.parse_warnings:
                    for w in invoice.parse_warnings:
                        self._log(f"  UYARI: {w}", "warning")

                xml_str = self.xml_generator.generate(invoice)

                output_dir = self.output_dir or os.path.dirname(pdf_path)
                os.makedirs(output_dir, exist_ok=True)
                xml_filename = self._make_xml_filename(invoice, filename)
                output_path = os.path.join(output_dir, xml_filename)

                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(xml_str)

                self.after(0, lambda v=(
                    filename,
                    invoice.invoice_id,
                    invoice.issue_date,
                    (invoice.supplier_name or "-")[:30],
                    (invoice.customer_name or "-")[:25],
                    f"{invoice.total_gross:,.2f} TL",
                    str(len(invoice.line_items)),
                    "Basarili" if not invoice.parse_warnings else "Uyarili",
                ): self.tree.insert("", tk.END, values=v))

                self._log(
                    f"  OK {filename} >> {xml_filename}",
                    "success",
                )
                self._log(
                    f"     Fatura: {invoice.invoice_id} | "
                    f"Toplam: {invoice.total_gross:,.2f} TL | "
                    f"Kalem: {len(invoice.line_items)}",
                    "success",
                )
                success_count += 1

            except Exception as e:
                err_msg = str(e)[:60]
                self.after(0, lambda v=(
                    filename, "-", "-", "-", "-", "-", "-", f"HATA: {err_msg}",
                ): self.tree.insert("", tk.END, values=v))
                self._log(f"  HATA ({filename}): {err_msg}", "error")
                error_count += 1

            self.after(0, lambda v=idx: self.progress.configure(value=v))
            self.update_idletasks()

        self._log("=" * 55, "header")
        self._log(
            f"DONUSURME TAMAMLANDI | Basarili: {success_count} | Hatali: {error_count}",
            "success" if error_count == 0 else "error",
        )
        self._log("=" * 55, "header")

        self._set_status(
            f"Tamamlandi - {success_count}/{total} basarili"
            + (f", {error_count} hatali" if error_count else ""),
            "success" if error_count == 0 else "error",
        )

        output_path_display = self.output_dir or "PDF ile ayni klasor"
        if success_count > 0:
            self.after(0, lambda: messagebox.showinfo(
                "Donusturme Tamamlandi",
                f"{success_count}/{total} dosya basariyla donusturuldu.\n\n"
                f"Cikis klasoru: {output_path_display}",
            ))

    def _make_xml_filename(self, invoice: InvoiceData, original_pdf_name: str) -> str:
        base = os.path.splitext(original_pdf_name)[0]
        if invoice.invoice_id:
            safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in invoice.invoice_id)
            return f"{safe_id}.xml"
        return f"{base}_ubl.xml"

    def _log(self, message: str, tag: str = "info"):
        def _insert():
            self.log_text.configure(state=tk.NORMAL)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.after(0, _insert)

    def _set_status(self, text: str, style: str = "Status.TLabel"):
        def _update():
            self.status_label.configure(text=text, style=style)
        self.after(0, _update)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
