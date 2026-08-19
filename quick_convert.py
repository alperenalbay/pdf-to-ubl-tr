"""
Hızlı PDF → UBL-TR Dönüştürücü (Komut Satırı)
Kullanım: python quick_convert.py dosya1.pdf dosya2.pdf ...
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_extractor import PDFExtractor
from invoice_parser import InvoiceParser
from xml_generator import UBLTriGenerator


def convert(pdf_path, output_dir=None):
    ext = PDFExtractor()
    parser = InvoiceParser()
    gen = UBLTriGenerator()

    filename = os.path.basename(pdf_path)
    print(f"\n  Isleniyor: {filename}")

    data = ext.extract_all(pdf_path)
    invoice = parser.parse(data["text"], source_file=pdf_path, tables=data["tables"])

    if invoice.parse_warnings:
        for w in invoice.parse_warnings:
            print(f"    UYARI: {w}")

    xml_str = gen.generate(invoice)

    if not output_dir:
        output_dir = os.path.dirname(pdf_path)

    base = os.path.splitext(filename)[0]
    xml_filename = f"{base}_ubl.xml"
    output_path = os.path.join(output_dir, xml_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"    Fatura: {invoice.invoice_id}")
    print(f"    Tarih:  {invoice.issue_date}")
    print(f"    Satici: {invoice.supplier_name} ({invoice.supplier_tckn or invoice.supplier_vkn})")
    print(f"    Alici:  {invoice.customer_name} ({invoice.customer_vkn or invoice.customer_tckn})")
    print(f"    Toplam: {invoice.total_gross:,.2f} TL ({len(invoice.line_items)} kalem)")
    print(f"    >> {output_path}")

    return invoice


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanim: python quick_convert.py dosya1.pdf [dosya2.pdf ...]")
        print("Ornek:    python quick_convert.py ornek.pdf")
        sys.exit(1)

    output_dir = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_dir = sys.argv[idx + 1]
            sys.argv = sys.argv[:idx] + sys.argv[idx + 2:]

    pdf_files = [a for a in sys.argv[1:] if a.lower().endswith(".pdf")]

    if not pdf_files:
        print("PDF dosyasi bulunamadi!")
        sys.exit(1)

    print(f"{len(pdf_files)} dosya donusturuluyor...")

    for pdf_path in pdf_files:
        if not os.path.exists(pdf_path):
            print(f"  HATA: {pdf_path} bulunamadi!")
            continue
        try:
            convert(pdf_path, output_dir)
        except Exception as e:
            print(f"  HATA ({pdf_path}): {e}")

    print("\nTamamlandi!")
