"""
UBL-TR E-Arşiv Fatura Dönüştürücü - Yapılandırma
PDF'teki gerçek alan yapısına uygun regex patternleri
"""

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
        r"Vergiler\s*Dahil\s*Toplam\s*Tutar\s+([\d.]+,\d{2})",
        r"(?:Toplam\s*Tutar|Toplam)[:\s]*([\d.]+,\d{2})\s*(?:TL|$)",
    ],
    "total_net": [
        r"Mal\s*Hizmet\s*Toplam\s*Tutar[ıi]?\s+([\d.]+,\d{2})",
        r"(?:Matrah|Net\s*(?:Mal\s*)?De[ğg]eri)[:\s]*([\d.]+,\d{2})",
    ],
    "total_tax_kdv": [
        r"Hesaplanan\s*KDV.*?([\d.]+,\d{2})",
        r"(?:KDV\s*(?:Toplam[ıi]|Tutar[ıi]|Tutar))[:\s]*([\d.]+,\d{2})",
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
