"""
UBL-TR E-Arşiv Fatura - Otomatik Pattern Tespiti
PDF metnini analiz ederek hangi format kullanıldığını ve
uygun regex pattern'lerini otomatik olarak tespit eder.
"""

import re
import json
from pathlib import Path
from typing import Optional


# Bilinen Türk şehirleri (büyük harf)
TURKISH_CITIES = [
    "ADANA", "ADIYAMAN", "AFYONKARAHİSAR", "AĞRI", "AKSARAY", "AMASYA", "ANKARA",
    "ANTALYA", "ARDAHAN", "ARTVİN", "AYDIN", "BALIKESİR", "BARTIN", "BATMAN",
    "BAYBURT", "BİLECİK", "BİNGÖL", "BİTLİS", "BOLU", "BURDUR", "BURSA",
    "ÇANAKKALE", "ÇANKIRI", "ÇORUM", "DENİZLİ", "DİYARBAKIR", "DÜZCE", "EDİRNE",
    "ELAZIĞ", "ERZİNCAN", "ERZURUM", "ESKİŞEHİR", "GAZİANTEP", "GİRESUN",
    "GÜMÜŞHANE", "HAKKARİ", "HATAY", "IĞDIR", "ISPARTA", "İÇEL", "İSTANBUL",
    "İZMİR", "KAHRAMANMARAŞ", "KARABÜK", "KARAMAN", "KARS", "KASTAMONU",
    "KAYSERİ", "KIRIKKALE", "KIRKLARELİ", "KIRŞEHİR", "KİLİS", "KOCAELİ",
    "KONYA", "KÜTAHYA", "MALATYA", "MANİSA", "MARDİN", "MERSİN", "MUĞLA",
    "MUŞ", "NEVŞEHİR", "NİĞDE", "ORDU", "OSMANİYE", "RİZE", "SAKARYA",
    "SAMSUN", "ŞANLIURFA", "SİİRT", "SİNOP", "SİVAS", "ŞIRNAK", "TEKİRDAĞ",
    "TOKAT", "TRABZON", "TUNCELİ", "UŞAK", "VAN", "YOZGAT", "ZONGULDAK",
]

# Şirket unvanı keyword'leri
COMPANY_KEYWORDS = [
    "ŞİRKETİ", "SIRKETI", "ANONİM", "ANONIM", "LİMİTED", "LIMITED",
    "SANAYİ", "SANAYI", "TİCARET", "TICARET", "TİC", "TIC", "A.Ş", "A.S",
    "LTD", "ŞTİ", "STI", "PAZARLAMA", "ELEKTRONİK", "ELEKTRONIK",
    "TEKNOLOJİ", "TEKNOLOJI", "BİLİŞİM", "BILISIM", "DANIŞMANLIK",
]

# Bilinen metadata/başlık satırı keyword'leri
METADATA_KEYWORDS = [
    "e-Arşiv", "e-Fatura", "eArsiv", "EFATURA", "Oluşturma", "Olusturma",
    "Senaryo", "Fatura Tipi", "Fatura No", "Fatura Tarihi", "Fatura ID",
    "Özelleştirme", "Zellestirme", "ETTN", "ProfileID", "Profile ID",
    "Gönderim", "Gonderim", "KAYNAK", "FATURA NO", "Invoice",
]


class HeuristicDetector:
    """PDF metnini analiz ederek otomatik pattern tespiti yapar."""

    def __init__(self):
        self.lines = []
        self.text = ""

    def analyze(self, text: str) -> dict:
        """PDF metnini analiz et, bulunan pattern'leri döndür.

        Returns:
            Template dict (save_template ile kaydedilebilir)
        """
        self.text = text
        self.lines = text.split("\n")

        template = {
            "name": "auto_detected",
            "version": "1.0",
            "created": "",
            "confidence": 0.0,
            "parties_separator": self._detect_separator_type(),
            "supplier": self._detect_supplier_patterns(),
            "customer": self._detect_customer_patterns(),
            "items": self._detect_item_patterns(),
            "totals": self._detect_total_patterns(),
        }

        template["confidence"] = self._calculate_confidence(template)
        return template

    # ─── SEPARATOR DETECTION ────────────────────────────────────

    def _detect_separator_type(self) -> str:
        """Satıcı/müşteri ayrım türünü tespit et."""
        for line in self.lines:
            stripped = line.strip()
            # Virgüllü "Sayın,"
            if re.search(r"Say[ıin]+\s*,", stripped, re.IGNORECASE):
                return "sayin_comma"
            # Virgülsüz "SAYIN" (TTNET)
            if re.search(r"^SAYIN\s+", stripped):
                return "sayin_uppercase"
        return "unknown"

    # ─── SUPPLIER DETECTION ─────────────────────────────────────

    def _detect_supplier_patterns(self) -> dict:
        """Satıcı bilgi pattern'lerini tespit et."""
        sayin_idx = self._find_sayin_line()
        supplier_lines = self.lines[1:sayin_idx] if sayin_idx > 0 else self.lines[1:]

        result = {
            "name_extraction": "auto",
            "vkn_pattern": None,
            "email_pattern": None,
            "tax_office_pattern": None,
            "address_format": "auto",
            "metadata_skip": [],
        }

        for s in supplier_lines:
            s = s.strip()
            if not s:
                continue

            # VKN pattern
            if not result["vkn_pattern"]:
                vkn_m = re.search(r"Vergi\s*(?:No|Numaras[ıi])\s*:\s*(\d{10})", s)
                if vkn_m:
                    result["vkn_pattern"] = re.escape(
                        s[:s.find(vkn_m.group(1))].rstrip()
                        .lstrip()
                    ).replace(r"\ ", "\\s*") + r"\s*(\d{10})"
                elif re.search(r"VKN\s*:\s*(\d{10})", s):
                    result["vkn_pattern"] = r"VKN\s*:\s*(\d{10})"

            # Email pattern
            if not result["email_pattern"]:
                ep_m = re.search(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", s)
                if ep_m:
                    result["email_pattern"] = r"E-Posta\s*:\s*([^\s]+@[^\s]+)"

            # Vergi Dairesi pattern
            if not result["tax_office_pattern"]:
                vd_m = re.search(r"Vergi\s*Dairesi\s*:\s*(.+)", s)
                if vd_m:
                    result["tax_office_pattern"] = r"Vergi\s*Dairesi\s*:\s*(.+?)\s*(?:Paket|Hizmet|Erişim|Alo|Web|HESAP|$)"

            # Şirket adı tespiti
            if result["name_extraction"] == "auto":
                has_company = any(kw in s.upper() for kw in COMPANY_KEYWORDS)
                hizmet_m = re.search(r"H.{0,3}ZMET\s*NO\s*:", s, re.IGNORECASE)
                if hizmet_m:
                    result["name_extraction"] = "hizmet_no_line"
                elif has_company and len(s) > 5 and not re.search(r"(?:Vergi|E-Posta|TCKN|Fatura|e-Ar)", s, re.IGNORECASE):
                    result["name_extraction"] = "company_keyword"

        return result

    # ─── CUSTOMER DETECTION ─────────────────────────────────────

    def _detect_customer_patterns(self) -> dict:
        """Müşteri bilgi pattern'lerini tespit et."""
        sayin_idx = self._find_sayin_line()
        if sayin_idx < 0:
            return {"name_extraction": "unknown", "vkn_pattern": None, "city_format": "unknown"}

        sayin_line = self.lines[sayin_idx].strip()
        customer_lines = [l.strip() for l in self.lines[sayin_idx + 1:] if l.strip()]

        result = {
            "name_extraction": "auto",
            "vkn_pattern": None,
            "city_format": "unknown",
            "tax_office_pattern": None,
        }

        # SAYIN satırından isim çıkarma pattern'i
        sayin_match = re.search(
            r"Say\w*\s+(.+?)(?:\s+SON\b|\s+Tarih\b|\s+Fatura\b|\s+ETTN\b|\s+Vergi\b|$)",
            sayin_line, re.IGNORECASE
        )
        if sayin_match:
            result["name_extraction"] = "sayin_line"

        for c in customer_lines[:15]:  # İlk 15 satıra bak
            # VKN pattern
            if not result["vkn_pattern"]:
                if re.search(r"Vergi\s*No\s*:\s*(\d{10})", c):
                    result["vkn_pattern"] = r"Vergi\s*No\s*:\s*(\d{10})"
                elif re.search(r"VKN\s*:\s*(\d{10})", c):
                    result["vkn_pattern"] = r"VKN\s*:\s*(\d{10})"
                elif re.search(r"TCKN/VKN\s*:\s*(\d{10,11})", c):
                    result["vkn_pattern"] = r"TCKN/VKN\s*:\s*(\d{10,11})"

            # Şehir formatı
            if result["city_format"] == "unknown":
                # "ÇANKAYA / ANKARA" formatı
                if re.match(r"^\S+\s*/\s*\S+$", c):
                    result["city_format"] = "district_slash_city"
                # "34349 Beşiktaş / İSTANBUL" formatı
                elif re.match(r"^\d{5}\s+\S+", c):
                    result["city_format"] = "postal_code_city"
                # Bilinen şehir ismi
                else:
                    for city in TURKISH_CITIES:
                        if city in c.upper():
                            result["city_format"] = "inline_city"
                            break

            # Vergi Dairesi
            if not result["tax_office_pattern"]:
                vd_m = re.search(r"Vergi\s*Dairesi\s*:\s*(.+)", c)
                if vd_m:
                    result["tax_office_pattern"] = r"Vergi\s*Dairesi\s*:\s*(.+?)\s*(?:HESAP|ETTN|BİR|B.R|$)"

        return result

    # ─── ITEM PATTERN DETECTION ─────────────────────────────────

    def _detect_item_patterns(self) -> dict:
        """Kalem çıkarma pattern'ini tespit et."""
        result = {
            "type": "unknown",
            "header_pattern": None,
            "item_pattern": None,
            "skip_patterns": [],
            "break_patterns": [],
        }

        # Tablo başlığı ara (Media Markt: "Sıra No Hizmet")
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if re.search(r"S.+\s+r.n\s*Hizmet", stripped, re.IGNORECASE):
                result["type"] = "table_based"
                result["header_pattern"] = r"S.+\s+r.n\s*Hizmet"
                break
            # TTNET: "Tutar İndirim Toplam"
            if re.search(r"Tutar\s+.*?[İi]ndirim\s+Toplam", stripped, re.IGNORECASE):
                result["type"] = "text_based"
                result["header_pattern"] = r"Tutar\s+.*?[İi]ndirim\s+Toplam"
                break

        # Kalem satırı pattern'ini tespit et
        in_items = False
        item_lines_found = 0

        for line in self.lines:
            stripped = line.strip()
            if not stripped:
                continue

            if result["header_pattern"] and re.search(result["header_pattern"], stripped, re.IGNORECASE):
                in_items = True
                continue

            if not in_items:
                continue

            # Toplam satırı → dur
            if re.search(r"TOPLAM|DEVLETE|KDV|Matrah|Mal\s*Hizmet|Yaln.z|denecek|e-Ar.iv", stripped, re.IGNORECASE):
                break

            # TTNET pattern: "hizmet adı 1.234,56 0,00 1.234,56"
            ttnet_m = re.match(r"^(.+?)\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})$", stripped)
            if ttnet_m:
                if not result["item_pattern"]:
                    result["item_pattern"] = r"^(.+?)\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})$"
                    result["type"] = "text_based"
                item_lines_found += 1
                # Toplam/sümen satırı kontrolü
                name = ttnet_m.group(1).strip()
                if re.search(r"Paket\s+[UÜ]creti|Toplam|Ara\s*Toplam|Genel", name, re.IGNORECASE):
                    result["skip_patterns"].append(re.escape(name))
                continue

            # Media Markt pattern: "1 AB-123 Ürün Adı ..."
            mm_m = re.match(r"^\d+\s+[A-Z]{2,}-\d+", stripped)
            if mm_m:
                if not result["item_pattern"]:
                    result["item_pattern"] = r"^\d+\s+[A-Z]{2,}-\d+"
                    result["type"] = "table_based"
                item_lines_found += 1
                continue

        if item_lines_found == 0:
            result["type"] = "unknown"

        return result

    # ─── TOTAL PATTERN DETECTION ────────────────────────────────

    def _detect_total_patterns(self) -> dict:
        """Toplam bilgisi pattern'lerini tespit et."""
        result = {
            "gross_patterns": [],
            "net_patterns": [],
            "tax_kdv_patterns": [],
            "tax_otv_patterns": [],
        }

        for line in self.lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Brüt toplam
            if re.search(r"TOPLAM\s*FATURA\s*TUTARI", stripped, re.IGNORECASE):
                result["gross_patterns"].append(r"TOPLAM\s*FATURA\s*TUTARI\s+([\d.]+,\d{2})")
            elif re.search(r"[OÖ]DENECEK\s*TOPLAM", stripped, re.IGNORECASE):
                result["gross_patterns"].append(r"[OÖ]DENECEK\s*TOPLAM\s+([\d.]+,\d{2})")
            elif re.search(r"Vergiler\s*Dahil\s*(?:Ödenecek\s+)?Toplam\s*Tutar", stripped, re.IGNORECASE):
                result["gross_patterns"].append(r"Vergiler\s*Dahil\s*(?:Ödenecek\s+)?Toplam\s*Tutar\s+([\d.]+,\d{2})")

            # Net toplam / Matrah
            if re.search(r"KDV\s*%\d+\s*\(Matrah", stripped, re.IGNORECASE):
                result["net_patterns"].append(r"KDV\s*%\d+\s*\(Matrah\s+([\d.]+[\d.]*)")
            elif re.search(r"Mal\s*Hizmet\s*Toplam\s*Tutar", stripped, re.IGNORECASE):
                result["net_patterns"].append(r"Mal\s*Hizmet\s*Toplam\s*Tutar[ıi]?\s+([\d.]+,\d{2})")

            # KDV
            if re.search(r"DEVLETE\s*[OÖ]DENEN\s*VERG[Iİ]LER", stripped, re.IGNORECASE):
                result["tax_kdv_patterns"].append(r"DEVLETE\s*[OÖ]DENEN\s*VERG[Iİ]LER\s*TOPLAMI\s+([\d.]+,\d{2})")
            elif re.search(r"KDV\s*%\d+", stripped, re.IGNORECASE):
                result["tax_kdv_patterns"].append(r"KDV\s*%\\d+.*?([\\d.]+,\\d{2})")

            # ÖTV
            if re.search(r"[OÖ]TV\s*%\d+", stripped, re.IGNORECASE):
                result["tax_otv_patterns"].append(r"[OÖ]TV\s*%\d+.*?([\d.]+,\d{2})")

        return result

    # ─── UTILITY ────────────────────────────────────────────────

    def _find_sayin_line(self) -> int:
        """Sayın/SAYIN satırının index'ini bul."""
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if re.search(r"Say[ıin]+[\s,]", stripped, re.IGNORECASE):
                return i
        return -1

    def _calculate_confidence(self, template: dict) -> float:
        """Tespit edilen pattern'lerin güvenilirliğini hesapla (0-1)."""
        score = 0.0
        total_checks = 8

        if template["parties_separator"] != "unknown":
            score += 1
        if template["supplier"].get("vkn_pattern"):
            score += 1
        if template["supplier"].get("email_pattern"):
            score += 0.5
        if template["supplier"].get("name_extraction") not in ("auto", "unknown"):
            score += 1
        if template["customer"].get("vkn_pattern"):
            score += 1
        if template["customer"].get("city_format") != "unknown":
            score += 1
        if template["items"].get("type") != "unknown":
            score += 1
        if template["totals"].get("gross_patterns"):
            score += 1.5

        return round(score / total_checks, 2)


def save_template(template: dict, name: str, templates_dir: str = "templates"):
    """Tespit edilen şablonu dosyaya kaydet."""
    templates_path = Path(templates_dir)
    templates_path.mkdir(exist_ok=True)

    template["name"] = name
    from datetime import datetime
    template["created"] = datetime.now().strftime("%Y-%m-%d")

    filepath = templates_path / f"{name.lower().replace(' ', '_')}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)

    return str(filepath)


def load_template(name: str, templates_dir: str = "templates") -> Optional[dict]:
    """Şablon dosyasından yükle."""
    templates_path = Path(templates_dir)
    filepath = templates_path / f"{name.lower().replace(' ', '_')}.json"
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def list_templates(templates_dir: str = "templates") -> list:
    """Mevcut tüm şablonların isimlerini listele."""
    templates_path = Path(templates_dir)
    if not templates_path.exists():
        return []
    return [f.stem for f in templates_path.glob("*.json")]


if __name__ == "__main__":
    import sys
    from pdf_extractor import PDFExtractor

    if len(sys.argv) < 2:
        print("Kullanım: python auto_detect.py <pdf_dosya_yolu>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    ext = PDFExtractor()
    data = ext.extract_all(pdf_path)

    detector = HeuristicDetector()
    template = detector.analyze(data["text"])

    print(f"\n=== OTOMATİK TESPİT SONUCU ===")
    print(f"Güven: {template['confidence']:.0%}")
    print(f"Ayırıcı: {template['parties_separator']}")
    print(f"Satıcı adı: {template['supplier']['name_extraction']}")
    print(f"Satıcı VKN pattern: {template['supplier']['vkn_pattern']}")
    print(f"Müşteri şehir: {template['customer']['city_format']}")
    print(f"Kalem tipi: {template['items']['type']}")
    print(f"Kalem pattern: {'VAR' if template['items']['item_pattern'] else 'YOK'}")
    print(f"Brüt pattern: {len(template['totals']['gross_patterns'])} adet")
    print(f"Net pattern: {len(template['totals']['net_patterns'])} adet")
    print(f"KDV pattern: {len(template['totals']['tax_kdv_patterns'])} adet")
    print(f"ÖTV pattern: {len(template['totals']['tax_otv_patterns'])} adet")

    # Şablonu kaydet
    answer = input("\nŞablonu kaydetmek ister misiniz? (e/h): ")
    if answer.lower() == "e":
        name = input("Şablon adı: ") or "auto_detected"
        path = save_template(template, name)
        print(f"Kaydedildi: {path}")
