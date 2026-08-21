# PDF to UBL-TR Dönüştürücü

> Türk e-arşiv fatura PDF dosyalarını GIB/SGK standartlarında UBL-TR XML formatına dönüştüren açık kaynak araç.

**Yapay zeka destekli** akıllı format tespiti ile farklı fatura türlerini otomatik olarak tanır ve dönüştürür.

---

## Özellikler

- **Çoklu PDF Desteği** — Toplu fatura dönüştürme
- **Otomatik Veri Çıkarma** — Fatura no, tarih, satıcı, alıcı, kalemler, toplamlar
- **Tablo Tabanlı Ayıklama** — pdfplumber ile hassas tablo çıkarma
- **Türkçe Karakter Desteği** — İ, ş, ü, ö, ç, ğ, ı karakterleri
- **UBL-TR Uyumluluğu** — UBLExtensions, cac/cbc namespace'leri
- **Otomatik Format Tespiti** — Yeni PDF formatları için heuristic analiz
- **Şablon Sistemi** — Farklı fatura türleri için özelleştirilebilir şablonlar
- **GUI Arayüzü** — Kullanıcı dostu grafik arayüz
- **EXE Paketleme** — Python gerekmeden çalıştırılabilir exe

## Kurulum

### Python ile

```bash
# Depoyu klonlayın
git clone https://github.com/alperenalbay/pdf-to-ubl-tr.git
cd pdf-to-ubl-tr

# Bağımlılıkları yükleyin
pip install -r requirements.txt

# Uygulamayı başlatın
python main.py
```

### EXE ile (Python Gerekmez)

`dist/PDF_to_UBL_TR.exe` dosyasını çalıştırın.

## Kullanım

### GUI

```bash
python main.py
```

1. **PDF Dosyaları Seç** — Dönüştürülecek PDF dosyalarını seçin
2. **Çıkış Klasörü Seç** — XML'lerin kaydedileceği klasörü seçin
3. **Dönüştür** — İşlemi başlatın

### Komut Satırı

```bash
# Tek dosya
python quick_convert.py fatura.pdf

# Çoklu dosya
python quick_convert.py fatura1.pdf fatura2.pdf

# Çıkış klasörü belirle
python quick_convert.py --output ./çıkı fatura.pdf
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
with open("çıkı.xml", "w", encoding="utf-8") as f:
    f.write(xml_str)
```

## Desteklenen Fatura Formatları

| Fatura Türü | Durum | Not |
|-------------|-------|-----|
| TTNET e-Arşiv | Tam Destek | Otomatik tespit |
| Media Markt e-Arşiv | Tam Destek | Tablo tabanlı |
| Diğer e-Arşiv | Otomatik | Heuristic analiz ile tespit |

## Proje Yapısı

```
pdf-to-ubl-tr/
├── main.py              # GUI arayüzü
├── pdf_extractor.py     # PDF okuyucu (pdfplumber)
├── invoice_parser.py    # Veri ayıklayıcı (regex + tablo)
├── xml_generator.py     # UBL-TR XML oluşturucu
├── config.py            # Regex patternleri ve sabitler
├── auto_detect.py       # Otomatik format tespiti
├── quick_convert.py     # Komut satırı aracı
├── templates/           # Fatura şablonları
├── paketle.bat          # EXE paketleme scripti
└── requirements.txt     # Python bağımlılıkları
```

## Teknolojiler

- **Python 3.8+**
- **pdfplumber** — PDF metin ve tablo çıkarma
- **tkinter** — GUI arayüzü
- **PyInstaller** — EXE paketleme

## Uyumluluk

- E-Arşiv Fatura (EARSIVFATURA)
- E-Fatura / Ticari Fatura (TICARIFATURA)
- KDV oranı: Otomatik algılama (%1, %10, %20, %50)
- Fatura tipi: SATIŞ, İADE

## Nasıl Katkı Sağlanır

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b ozellik/yeni-ozellik`)
3. Değişikliklerinizi commit edin (`git commit -m 'Yeni özellik eklendi'`)
4. Push yapın (`git push origin ozellik/yeni-ozellik`)
5. Pull Request açın

## Sorun Bildirimi

Hata bulursanız veya özelliğiniz olsun istiyorsanız [GitHub Issues](https://github.com/alperenalbay/pdf-to-ubl-tr/issues) üzerinden bildirin.

## Lisans

Bu proje [MIT Lisansı](LICENSE) altında dağıtilmaktadır.

---

*Bu proje açık kaynak kodlu ve yapay zeka destekli olarak geliştirilmiştir.*
