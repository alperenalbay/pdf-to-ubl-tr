"""
PDF Dosyasından Metin ve Tablo Çıkarma Modülü
pdfplumber kullanarak Türkçe karakter destekli metin + yapılandırılmış tablo çıkarma
"""

import os
from typing import Optional

# Maksimum PDF boyutu (50 MB)
MAX_PDF_SIZE = 50 * 1024 * 1024


class PDFExtractor:
    """PDF dosyasından ham metin ve tabloları çıkaran sınıf."""

    def __init__(self):
        self._pdfplumber = None
        self._import_libraries()

    def _import_libraries(self):
        try:
            import pdfplumber
            self._pdfplumber = pdfplumber
        except ImportError:
            raise ImportError(
                "pdfplumber kütüphanesi gerekli. Yüklemek için:\n"
                "  pip install pdfplumber"
            )

    def extract_all(self, pdf_path: str) -> dict:
        """
        PDF dosyasından metin ve tabloları birlikte çıkarır.

        Returns:
            {"text": str, "tables": list[list[list]], "page_count": int}
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF dosyası bulunamadı: {pdf_path}")
        if not pdf_path.lower().endswith(".pdf"):
            raise ValueError(f"Geçersiz dosya formatı (PDF bekleniyor): {pdf_path}")
        file_size = os.path.getsize(pdf_path)
        if file_size > MAX_PDF_SIZE:
            raise ValueError(f"PDF çok büyük ({file_size / 1024 / 1024:.1f} MB). Maksimum: {MAX_PDF_SIZE / 1024 / 1024:.0f} MB")

        full_text = []
        all_tables = []
        page_count = 0

        try:
            with self._pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        full_text.append(page_text)

                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            cleaned = []
                            for row in table:
                                cleaned.append([
                                    str(cell).strip() if cell else ""
                                    for cell in row
                                ])
                            all_tables.append(cleaned)

        except Exception as e:
            raise ValueError(f"PDF okuma hatası ({pdf_path}): {e}")

        result_text = "\n".join(full_text)
        return {
            "text": result_text,
            "tables": all_tables,
            "page_count": page_count,
        }

    def extract_text(self, pdf_path: str) -> str:
        """PDF dosyasından tüm sayfaların metnini çıkarır (backward compatibility)."""
        data = self.extract_all(pdf_path)
        text = data["text"]
        if not text.strip():
            raise ValueError(f"PDF'den metin çıkarılamadı (boş veya taranmış PDF): {pdf_path}")
        return text

    def extract_text_safe(self, pdf_path: str) -> Optional[str]:
        """Hata fırlatmadan metin çıkarmayı dener."""
        try:
            return self.extract_text(pdf_path)
        except Exception:
            return None

    def get_page_count(self, pdf_path: str) -> int:
        """PDF sayfa sayısını döndürür."""
        try:
            with self._pdfplumber.open(pdf_path) as pdf:
                return len(pdf.pages)
        except Exception:
            return 0
