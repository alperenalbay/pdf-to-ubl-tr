from pdf_extractor import PDFExtractor
from invoice_parser import InvoiceParser
from xml_generator import UBLTriGenerator
import re
import os
import sys

ext = PDFExtractor()
parser = InvoiceParser()
gen = UBLTriGenerator()

# Komut satırından PDF yolu al, yoksaornek/ klasöründe ara
if len(sys.argv) > 1:
    pdf_path = sys.argv[1]
else:
    pdf_path = os.path.join(os.path.dirname(__file__), "ornek", "ornek_ttnet.pdf")

if not os.path.exists(pdf_path):
    print(f"PDF bulunamadi: {pdf_path}")
    print("Kullanim: python test_ttnet.py <pdf_dosya_yolu>")
    sys.exit(1)

data = ext.extract_all(pdf_path)
lines = data['text'].split('\n')

# Debug SAYIN detection
print('=== SAYIN DETECTION ===')
for i, line in enumerate(lines):
    s = line.strip()
    if 'SAYIN' in s.upper():
        m = re.search(r'Say.+n[\s,]', s, re.IGNORECASE)
        print(f'  Line {i}: [{s[:60]}] -> regex match: {m}')

# Debug metadata detection
print('\n=== METADATA DETECTION ===')
metadata_starts = re.compile(r'(?i)zelle.tirme\s+No|Senaryo\s*:|Fatura\s+No\s*:|Fatura\s+Tarihi|Fatura\s+Tipi|Olu.turma\s+Zaman')
for i, line in enumerate(lines):
    s = line.strip()
    if metadata_starts.search(s):
        print(f'  Line {i}: [{s[:60]}]')

# Debug supplier extraction
print('\n=== SUPPLIER LINES ===')
sayin_idx = -1
for i, line in enumerate(lines):
    if re.search(r'Say.+n[\s,]', line.strip(), re.IGNORECASE):
        sayin_idx = i
        break
print(f'  sayin_idx = {sayin_idx}')

if sayin_idx >= 0:
    print(f'  Supplier lines (0-{sayin_idx-1}):')
    for i in range(sayin_idx):
        print(f'    [{lines[i].strip()[:60]}]')
    print(f'  Customer lines ({sayin_idx+1}-...):')
    for i in range(sayin_idx+1, min(sayin_idx+10, len(lines))):
        print(f'    [{lines[i].strip()[:60]}]')

# Debug totals patterns
print('\n=== TOTALS PATTERNS ===')
text = data['text']
for label, pat in [
    ('gross_TOPLAM', r'TOPLAM FATURA TUTARI\s+([\d.]+,\d{2})'),
    ('gross_odecek', r'ÖDENECEK TOPLAM\s+([\d.]+,\d{2})'),
    ('gross_vergiler', r'Vergiler Dahil.*?Toplam\s*Tutar\s+([\d.]+,\d{2})'),
    ('devlet', r'DEVLETE ÖDENEN VERGİLER TOPLAMI\s+([\d.]+,\d{2})'),
    ('kdv1', r'KDV %20 \(Matrah\s+([\d.]+)'),
    ('kdv2', r'KDV\s*%\d+.*?([\d.]+,\d{2})'),
    ('otv', r'ÖTV\s*%\d+.*?([\d.]+,\d{2})'),
    ('matrah', r'Matrah\s+([\d.]+[\d.]*)'),
]:
    m = re.search(pat, text, re.IGNORECASE)
    print(f'  {label}: {m.group(1) if m else "YOK"}')

# Debug line items
print('\n=== LINE ITEM PATTERNS ===')
for i, line in enumerate(lines):
    s = line.strip()
    # TTNET: "name amount discount total"
    if re.match(r'^.+\s+[\d.]+,\d{2}\s+[\d.]+,\d{2}\s+[\d.]+,\d{2}$', s):
        print(f'  TTNET item at line {i}: [{s[:60]}]')

# Full parse
print('\n=== FULL PARSE ===')
invoice = parser.parse(data['text'], source_file='test.pdf', tables=data['tables'])
print(f'  Supplier: {invoice.supplier_name} / VKN:{invoice.supplier_vkn} / City:{invoice.supplier_city} / Email:{invoice.supplier_email}')
print(f'  Customer: {invoice.customer_name} / VKN:{invoice.customer_vkn} / TCKN:{invoice.customer_tckn} / City:{invoice.customer_city}')
print(f'  InvoiceNo: {invoice.invoice_id}')
print(f'  Date: {invoice.issue_date} Time: {invoice.issue_time}')
print(f'  Gross: {invoice.total_gross} Net: {invoice.total_net} Tax: {invoice.total_tax}')
print(f'  Items: {len(invoice.line_items)}')
for item in invoice.line_items:
    print(f'    {item.line_id}. {item.name}: {item.line_total_net} TL (KDV %{item.tax_rate})')
print(f'  Warnings: {invoice.parse_warnings}')
