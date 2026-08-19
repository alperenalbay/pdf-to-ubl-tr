# PDF to UBL-TR Donusturucu

E-arsiv fatura PDF dosyalarini GIB/SGK standartlarinda UBL-TR XML formatina donusturur.

## Ozellikleri

- Coklu PDF dosyasi destegi (toplu donusturme)
- PDF'ten otomatik veri cikarma (fatura no, tarih, satici, alici, kalemler, toplamlar)
- Table-based Veri Cikarma (pdfplumber tablo cikartma ile hassas ayristirma)
- Turkce karakter destegi
- UBL-TR standartlarina uygun XML ciktisi (UBLExtensions, cac/cbc namespace'leri)
- Kullanici dostu GUI arayuzu
- Tek tiklama ile EXE paketleme

## Kurulum

### Python ile
```bash
pip install pdfplumber>=0.11.0
python main.py
```

### EXE ile (Python gerekmez)
`dist/PDF_to_UBL_TR.exe` dosyasini calistirin.

## Kullanim

### GUI
```bash
python main.py
```
1. **PDF Dosyalari Sec** - Donusturulecek PDF dosyalarini secin
2. **Cikis Klasoru Sec** - XML'lerin kaydedilecegi klasoru secin
3. **Donustur** - Islemi baslatin

### Komut Satiri
```bash
# Tek dosya
python quick_convert.py fatura.pdf

# Coklu dosya
python quick_convert.py fatura1.pdf fatura2.pdf

# Cikis klasoru belirle
python quick_convert.py --output ./cikti fatura.pdf
```

### Python Kodu
```python
from pdf_extractor import PDFExtractor
from invoice_parser import InvoiceParser
from xml_generator import UBLTriGenerator

ext = PDFExtractor()
parser = InvoiceParser()
gen = UBLTriGenerator()

data = ext.extract_all("fatura.pdf")
invoice = parser.parse(data["text"], tables=data["tables"])

xml_str = gen.generate(invoice)
with open("cikti.xml", "w", encoding="utf-8") as f:
    f.write(xml_str)
```

## EXE Paketleme

Kaynak kodda degisiklik yaptiktan sonra:

```bash
# Windows
paketle.bat

# veya dogrudan
python -m PyInstaller --clean --noconfirm pdf_to_ubl.spec
```

Uretilen `dist/PDF_to_UBL_TR.exe` dosyasini istediginiz bilgisayara kopyalayabilirsiniz.

## Proje Yapisi

```
pdf_to_ubl/
  main.py              # GUI arayuzu
  pdf_extractor.py     # PDF okuyucu (pdfplumber)
  invoice_parser.py    # Veri ayiklayici (regex + table parsing)
  xml_generator.py     # UBL-TR XML olusturucu
  config.py            # Regex patternleri ve sabit degerler
  quick_convert.py     # Komut satiri araci
  paketle.bat          # EXE paketleme scripti
  requirements.txt     # Python bagimliliklari
```

## Uyumluluk

- E-Arsiv Fatura (EARSIVFATURA)
- E-Fatura / Ticari Fatura (TICARIFATURA)
- KDV orani: otomatik algilama (%1, %10, %20, %50)
- Fatura tipi: SATIS, IADE

## Lisans

MIT
