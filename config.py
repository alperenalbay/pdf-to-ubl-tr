"""
UBL-TR E-Arşiv Fatura Dönüştürücü - Yapılandırma
PDF'teki gerçek alan yapısına uygun regex patternleri
+ Dinamik şablon yükleme desteği
"""

import json
from pathlib import Path
from typing import Optional

UBL_NAMESPACES = {
    "root": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
}

# PDF'teki gerçek alan adlarına uygun pattern'ler
REGEX_PATTERNS = {
    "invoice_no": [
        r"Fatura\s*No\s*:\s*([A-Z0-9\-/]+)",
        r"FATURA\s*NO\s*:\s*([A-Z0-9\-/]+)",
        r"Fatura\s*ID\s+([A-Z0-9\-/]+)",
        r"(?:FATURA\s*NO|Invoice\s*No)[:\s]*([A-Z0-9\-/]+)",
        r"\b([A-Z]{2,3}\d{10,})\b",
    ],
    "ettn_uuid": [
        r"ETTN\s*:?\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b",
    ],
    "date": [
        r"Fatura\s*Tarihi\s*:\s*(\d{2})-(\d{2})-(\d{4})",
        r"(?:Tarih)[:\s]*(\d{2})[.\-/](\d{2})[.\-/](\d{4})",
        r"(\d{2})[.\-/](\d{2})[.\-/](\d{4})",
    ],
    "time": [
        r"Olu[sş]turma\s*Zaman[ıi]\s*:\s*(\d{2}:\d{2}:\d{2})",
        r"(?:Saat)[:\s]*(\d{2}:\d{2}:\d{2})",
        r"(\d{2}:\d{2}:\d{2})",
        r"(\d{2}:\d{2})(?:\s|$)",
    ],
    "vkn_explicit": [
        r"(?:^|\s)VKN\s*:\s*(\d{10})\b",
    ],
    "tckn_explicit": [
        r"TCKN\s*:\s*(\d{10,11})\b",
    ],
    "invoice_type": [
        r"Fatura\s*Tipi\s*:\s*(\w+)",
        r"\b(SATIS|IADE|TEVKIFAT)\b",
    ],
    "tax_office_explicit": [
        r"Vergi\s*Dairesi\s*:\s*(.+?)(?:\s*$|\n)",
    ],
    "profile_id": [
        r"Senaryo\s*:\s*(\w+)",
        r"(?:Profile\s*ID|Profil)[:\s]*(\w+)",
    ],
    "total_gross": [
        r"Vergiler\s*Dahil\s*(?:Ödenecek\s+)?Toplam\s*Tutar\s+([\d.]+,\d{2})",
        r"(?:Toplam\s*Tutar|Toplam)[:\s]*([\d.]+,\d{2})\s*(?:TL|$)",
        r"TOPLAM\s*FATURA\s*TUTARI\s+([\d.]+,\d{2})",
        r"ÖDENECEK\s*TOPLAM\s+([\d.]+,\d{2})",
    ],
    "total_net": [
        r"Mal\s*Hizmet\s*Toplam\s*Tutar[ıi]?\s+([\d.]+,\d{2})",
        r"(?:Matrah|Net\s*(?:Mal\s*)?De[ğg]eri)[:\s]*([\d.]+,\d{2})",
        r"KDV\s*%\d+\s*\(Matrah\s+([\d.]+[\d.]*)",
    ],
    "total_tax_kdv": [
        r"Hesaplanan\s*KDV.*?([\d.]+,\d{2})",
        r"(?:KDV\s*(?:Toplam[ıi]|Tutar[ıi]|Tutar))[:\s]*([\d.]+,\d{2})",
        r"DEVLETE\s*[OÖ]DENEN\s*VERG[Iİ]LER\s*TOPLAMI\s+([\d.]+,\d{2})",
        r"KDV\s*%\d+.*?([\d.]+,\d{2})",
    ],
    "total_tax_otv": [
        r"[OÖ]TV\s*%\d+.*?([\d.]+,\d{2})",
    ],
    "tax_rate": [
        r"%\s*(\d+)",
    ],
    "mernis_no": [
        r"Mersis\s*No\s*:\s*(\d+)",
    ],
    "trade_registry": [
        r"(?:Ticaret\s*Sicil\s*No)[:\s]*(\d+)",
    ],
    "iban": [
        r"IBAN\s*:\s*([A-Z]{2}\d{2}\s*(?:\d{4}\s*){7}\d{2})",
    ],
}

# Keyword listeleri kaldırıldı - doğrudan attribute tabanlı eşleştirme kullanılır
SUPPLIER_KEYWORDS = [
    "TICARET", "TİCARET", "LIMITED", "LİMİTED", "SIRKETI", "ŞİRKETİ",
    "ANONIM", "ANONİM", "LTD", "SAN", "TIC", "TİC", "A.S", "A.Ş",
]

CUSTOMER_KEYWORDS = [
    "ERENOGLU", "ERENOĞLU", "ALICI", "MÜŞTERİ", "MUSTERI",
]

CURRENCY = "TRY"
OUTPUT_ENCODING = "UTF-8"
XML_VERSION = "1.0"
UBL_VERSION = "2.1"
CUSTOMIZATION_ID = "TR1.2"
DEFAULT_TAX_TYPE_CODE = "0015"
DEFAULT_UNIT_CODE = "C62"

# ─── DİNAMİK ŞABLON YÜKLEME ──────────────────────────────────

TEMPLATES_DIR = Path(__file__).parent / "templates"


def list_templates() -> list:
    """Mevcut tüm şablonların isimlerini listele."""
    if not TEMPLATES_DIR.exists():
        return []
    return sorted([f.stem for f in TEMPLATES_DIR.glob("*.json")])


def load_template(name: str) -> Optional[dict]:
    """Şablon dosyasından yükle."""
    filepath = TEMPLATES_DIR / f"{name}.json"
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def get_patterns_for_template(template: dict) -> dict:
    """Şablondan REGEX_PATTERNS formatında pattern dict'i oluştur.

    Template formatı ile REGEX_PATTERNS formatı arasında köprü kurar.
    Eksik pattern'ler varsayılan REGEX_PATTERNS'ten alınır.
    """
    patterns = dict(REGEX_PATTERNS)  # Varsayılanları kopyala

    if not template:
        return patterns

    # ── invoice_no ──
    # (şablonda özel bir alan yoksa varsayılan kalır)

    # ── total_gross ──
    if template.get("totals", {}).get("gross_patterns"):
        patterns["total_gross"] = template["totals"]["gross_patterns"]

    # ── total_net ──
    if template.get("totals", {}).get("net_patterns"):
        patterns["total_net"] = template["totals"]["net_patterns"]

    # ── total_tax_kdv ──
    if template.get("totals", {}).get("tax_kdv_patterns"):
        patterns["total_tax_kdv"] = template["totals"]["tax_kdv_patterns"]

    # ── total_tax_otv ──
    if template.get("totals", {}).get("tax_otv_patterns"):
        patterns["total_tax_otv"] = template["totals"]["tax_otv_patterns"]

    # ── vkn_explicit (satıcı) ──
    supplier = template.get("supplier", {})
    if supplier.get("vkn_pattern"):
        patterns["vkn_explicit"] = [supplier["vkn_pattern"]]

    # ── vkn (müşteri) ──
    customer = template.get("customer", {})
    if customer.get("vkn_pattern"):
        patterns["tckn_explicit"] = [customer["vkn_pattern"]]

    return patterns


def get_template_metadata(template: dict) -> dict:
    """Şablondan parser meta-bilgilerini çıkar (separator, item type vb.)."""
    if not template:
        return {}

    return {
        "parties_separator": template.get("parties_separator", "unknown"),
        "supplier_name_extraction": template.get("supplier", {}).get("name_extraction", "auto"),
        "customer_city_format": template.get("customer", {}).get("city_format", "unknown"),
        "item_type": template.get("items", {}).get("type", "unknown"),
        "item_pattern": template.get("items", {}).get("item_pattern"),
        "item_header_pattern": template.get("items", {}).get("header_pattern"),
        "item_skip_patterns": template.get("items", {}).get("skip_patterns", []),
        "item_break_patterns": template.get("items", {}).get("break_patterns", []),
    }
