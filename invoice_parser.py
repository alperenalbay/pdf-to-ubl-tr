"""
Fatura Metni Ayırıştırıcı Modülü
PDF yapısına göre satıcı/alıcı tespiti, tablo tabanlı kalem çıkarma
"""

import re
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from config import (
    REGEX_PATTERNS,
    SUPPLIER_KEYWORDS,
    DEFAULT_TAX_TYPE_CODE,
    DEFAULT_UNIT_CODE,
)


@dataclass
class InvoiceLineItem:
    line_id: int = 0
    name: str = ""
    stock_code: str = ""
    serial_no: str = ""
    quantity: float = 1.0
    unit_code: str = DEFAULT_UNIT_CODE
    unit_price_net: float = 0.0
    line_total_net: float = 0.0
    tax_amount: float = 0.0
    tax_rate: float = 20.0
    gross_price: float = 0.0

    def calculate_from_gross(self):
        if self.gross_price > 0 and self.tax_rate > 0:
            self.unit_price_net = round(self.gross_price / (1 + self.tax_rate / 100), 2)
            self.line_total_net = round(self.unit_price_net * self.quantity, 2)
            self.tax_amount = round(self.line_total_net * self.tax_rate / 100, 2)

    def calculate_from_net(self):
        """Birim fiyat net ise hesaplama yapar."""
        if self.unit_price_net > 0 and self.quantity > 0:
            self.line_total_net = round(self.unit_price_net * self.quantity, 2)
        if self.line_total_net > 0 and self.tax_rate > 0:
            self.tax_amount = round(self.line_total_net * self.tax_rate / 100, 2)
        self.gross_price = round(self.unit_price_net * (1 + self.tax_rate / 100), 2) if self.unit_price_net > 0 else 0.0


@dataclass
class InvoiceData:
    invoice_id: str = ""
    uuid: str = ""
    issue_date: str = ""
    issue_time: str = ""
    invoice_type: str = "SATIS"
    profile_id: str = ""
    note: str = ""
    supplier_name: str = ""
    supplier_vkn: str = ""
    supplier_tckn: str = ""
    supplier_tax_office: str = ""
    supplier_address: str = ""
    supplier_city: str = ""
    supplier_district: str = ""
    supplier_street: str = ""
    supplier_building_no: str = ""
    supplier_postal_code: str = ""
    supplier_email: str = ""
    customer_name: str = ""
    customer_tckn: str = ""
    customer_vkn: str = ""
    customer_tax_office: str = ""
    customer_address: str = ""
    customer_city: str = ""
    customer_district: str = ""
    customer_street: str = ""
    customer_postal_code: str = ""
    total_gross: float = 0.0
    total_net: float = 0.0
    total_tax: float = 0.0
    tax_rate: float = 20.0
    line_items: list = field(default_factory=list)
    raw_text: str = ""
    source_file: str = ""
    parse_warnings: list = field(default_factory=list)

    def generate_uuid(self):
        if not self.uuid:
            self.uuid = str(uuid.uuid4())
        return self.uuid

    def ensure_id(self):
        if not self.invoice_id:
            self.invoice_id = f"EAF{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def recalculate_totals(self):
        total_net = 0.0
        total_tax = 0.0
        for item in self.line_items:
            item.calculate_from_net()
            total_net += item.line_total_net
            total_tax += item.tax_amount
        self.total_net = round(total_net, 2)
        self.total_tax = round(total_tax, 2)
        self.total_gross = round(total_net + total_tax, 2)


class InvoiceParser:

    def __init__(self, template: dict = None):
        """Parser'ı başlat. Opsiyonel template ile farklı formatları destekle."""
        if template:
            from config import get_patterns_for_template, get_template_metadata
            self.patterns = get_patterns_for_template(template)
            self.template_meta = get_template_metadata(template)
        else:
            self.patterns = REGEX_PATTERNS
            self.template_meta = {}
        self.template = template

    def parse(self, text: str, source_file: str = "", tables: list = None) -> InvoiceData:
        invoice = InvoiceData(raw_text=text, source_file=source_file)
        lines = text.split("\n")

        self._extract_header_fields(invoice, text)
        self._extract_parties(invoice, lines, text)

        # Her iki yöntemi de dene - hangisi daha iyi sonuç verirse onu kullan
        text_items = []
        text_totals = {"gross": 0.0, "net": 0.0, "tax": 0.0}

        # Metin tabanlı çıkarma (her zaman dene)
        self._extract_line_items_from_text(invoice, lines)
        if invoice.line_items:
            text_items = list(invoice.line_items)
        self._extract_totals_from_text(invoice, text)
        text_totals = {"gross": invoice.total_gross, "net": invoice.total_net, "tax": invoice.total_tax}

        # Tablo tabanlı çıkarma (varsa dene)
        if tables:
            table_items, table_totals = self._extract_from_tables_raw(tables)

            # Tabloda kalem varsa onu kullan
            if table_items:
                invoice.line_items = table_items

            # Tabloda toplam varsa ve metin toplamından farklıysa tercih et
            if table_totals["gross"] > 0:
                invoice.total_gross = table_totals["gross"]
            elif text_totals["gross"] > 0:
                invoice.total_gross = text_totals["gross"]

            if table_totals["net"] > 0:
                invoice.total_net = table_totals["net"]
            elif text_totals["net"] > 0:
                invoice.total_net = text_totals["net"]

            if table_totals["tax"] > 0:
                invoice.total_tax = table_totals["tax"]
            elif text_totals["tax"] > 0:
                invoice.total_tax = text_totals["tax"]

            # Tablo T0'dan müşteri bilgisi tamamla (sadece eksikleri)
            self._extract_customer_from_table0(invoice, tables)

        # Her kalem için vergi hesapla (calculate_from_net)
        for item in invoice.line_items:
            item.calculate_from_net()

        # Toplamları recalculate et: eğer metin/tablodan zaten toplam geldiyse koru, yoksa kalem toplamlarından hesapla
        if invoice.total_gross <= 0 and invoice.total_net <= 0:
            invoice.recalculate_totals()
        invoice.generate_uuid()
        invoice.ensure_id()
        self._add_warnings(invoice)

        # ── OTOMATİK TESPİT: Başarısız parse → heuristic analiz ──
        # Sadece şablon yokken/yetersizken dene; açık şablon ile eşleşen
        # (örn. 0-TL Vodafone) sonucu bozma.
        no_template = (
            self.template is None
            or str(self.template.get("name", "")).startswith("auto")
            or self.template.get("_auto")
        )
        if (not invoice.line_items or invoice.total_gross <= 0) and no_template:
            invoice = self._try_auto_detect(text, source_file, tables, invoice)

        return invoice

    def _try_auto_detect(self, text, source_file, tables, invoice):
        """Parse başarısızsa, otomatik tespit ile yeni template dene."""
        try:
            from auto_detect import HeuristicDetector, save_template
            from config import get_patterns_for_template, get_template_metadata

            detector = HeuristicDetector()
            template = detector.analyze(text)

            if template["confidence"] < 0.4:
                # Yeterince güvenilir tespit yapılamadı
                invoice.parse_warnings.append(
                    f"Format tanınamadı (güven: {template['confidence']:.0%}). "
                    "Manuel şablon ekleyebilirsiniz."
                )
                return invoice

            # Yeni template ile tekrar parse et
            new_parser = InvoiceParser(template=template)
            new_invoice = new_parser.parse(text, source_file, tables)

            # Yeni sonuç daha mı iyi?
            if self._is_better_result(new_invoice, invoice):
                new_invoice.parse_warnings.insert(0,
                    f"Otomatik tespit: {template['name']} (güven: {template['confidence']:.0%})"
                )
                # Template'i kaydet (path traversal engeli)
                raw_name = source_file.split("/")[-1].split("\\")[-1].replace(".pdf", "") if source_file else "auto"
                safe_template_name = re.sub(r"[^a-zA-Z0-9_\-. ]", "_", raw_name).strip(". ")[:100].strip() or "auto"
                save_template(template, f"auto_{safe_template_name}")
                return new_invoice
            else:
                invoice.parse_warnings.append(
                    f"Otomatik tespit başarısız (güven: {template['confidence']:.0%}). "
                    "Varsayılan şablon kullanıldı."
                )
                return invoice

        except Exception as e:
            invoice.parse_warnings.append(f"Otomatik tespit hatası: {str(e)}")
            return invoice

    def _is_better_result(self, new_inv, old_inv) -> bool:
        """Yeni parse sonucu eskisinden daha mı iyi?"""
        new_score = 0
        old_score = 0

        # Kalem varlığı
        if new_inv.line_items:
            new_score += 3
        if old_inv.line_items:
            old_score += 3

        # Toplam tutar varlığı
        if new_inv.total_gross > 0:
            new_score += 2
        if old_inv.total_gross > 0:
            old_score += 2

        # Satıcı adı
        if new_inv.supplier_name and "bilinmiyor" not in new_inv.supplier_name.lower():
            new_score += 1
        if old_inv.supplier_name and "bilinmiyor" not in old_inv.supplier_name.lower():
            old_score += 1

        # Müşteri adı
        if new_inv.customer_name:
            new_score += 1
        if old_inv.customer_name:
            old_score += 1

        return new_score > old_score

    # ─── HEADER FIELDS ──────────────────────────────────────────

    def _extract_header_fields(self, invoice: InvoiceData, text: str):
        invoice.invoice_id = self._search_first(text, "invoice_no")
        invoice.uuid = self._search_first(text, "ettn_uuid")

        date_parts = self._search_groups(text, "date")
        if date_parts and len(date_parts) >= 3:
            try:
                day, month, year = date_parts[0], date_parts[1], date_parts[2]
                invoice.issue_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except (ValueError, IndexError):
                pass

        time_str = self._search_first(text, "time")
        if time_str:
            clean = re.sub(r"[^\d:]", "", time_str)
            if ":" in clean:
                # HH:MM formatını HH:MM:SS'e çevir
                parts = clean.split(":")
                if len(parts) == 2:
                    clean = f"{parts[0]}:{parts[1]}:00"
                invoice.issue_time = clean

        inv_type = self._search_first(text, "invoice_type")
        if inv_type and inv_type.upper() in ("SATIS", "IADE", "TEVKIFAT"):
            invoice.invoice_type = inv_type.upper()

        profile = self._search_first(text, "profile_id")
        if profile:
            invoice.profile_id = profile.upper()

        mernis = self._search_first(text, "mernis_no")
        if mernis:
            invoice.note += f"Mersis No: {mernis}"

        iban = self._search_first(text, "iban")
        if iban:
            invoice.note += f" IBAN: {iban}"

    # ─── PARTY DETECTION ────────────────────────────────────────

    def _extract_parties(self, invoice: InvoiceData, lines: list, text: str):
        """PDF'in üst bloğu satıcı, 'Sayın,' bloğu alıcı olacak şekilde tespit eder.

        PDF yapısı (Media Markt):
            [0] e-Arşiv Fatura              ← belge başlığı
            [1-8] satıcı bilgileri (ad, adres, VD, TCKN)
            [9] Sayın, ...                  ← müşteri başlangıcı
            [10-17] müşteri bilgileri + metadata (Fatura No, Tarih vb.)
            [18+] kalemler, toplamlar

        PDF yapısı (TTNET):
            [0-6] metadata + satıcı header
            [7-17] satıcı bilgileri
            [18] SAYIN MÜŞTERİ ADI ...      ← müşteri başlangıcı (virgülsüz)
            [19-25] müşteri bilgileri + ETTN
            [26+] kalemler, toplamlar
        """
        sayin_idx = -1
        for i, line in enumerate(lines):
            # "Sayın," (virgüllü), "SAYIN" (virgülsüz) veya yalnız "SAYIN" satırı
            if re.search(r"Say\w{0,3}n\b", line.strip(), re.IGNORECASE):
                sayin_idx = i
                break

        # Müşteri bloğunun başladığı satır indeksi.
        # SAYIN varsa ondan sonrasıdır; yoksa şablondaki customer_start regex'i kullanılır.
        customer_after = sayin_idx + 1 if sayin_idx >= 0 else None
        if customer_after is None:
            cs = (self.template_meta or {}).get("customer_start")
            if cs:
                try:
                    cs_re = re.compile(cs, re.IGNORECASE)
                except re.error:
                    cs_re = None
                if cs_re:
                    for i, line in enumerate(lines):
                        if cs_re.search(line):
                            customer_after = i + 1
                            break

        # Metadata bitiş göstergeleri
        metadata_starts = re.compile(
            r"(?:.zelle.tirme\s+No|Senaryo\s*:|Fatura\s+(?:No|ID)\s*:|FATURA\s*ID|Fatura\s+Tarihi|"
            r"Fatura\s+Tipi|Olu.turma\s+Zaman|İrsaliye\s*No|İrsaliye\s+Tarihi)",
            re.IGNORECASE
        )

        # ─── SATICI BLOĞU: line 0 (header label) ile Sayın, arası ──
        supplier_lines = []
        if customer_after is not None and customer_after > 0:
            start = 0
            # 0. satır "e-Arşiv Fatura" gibi bir belge etiketi ise atla
            if lines and re.search(r"e-Ar.siv\s+Fatura|e-Fatura|INVOICE|\bFATURA\b", lines[0], re.IGNORECASE):
                start = 1
            supplier_lines = [l.strip() for l in lines[start:customer_after] if l.strip()]
        else:
            supplier_lines = [l.strip() for l in lines[1:] if l.strip()]

        mernis_no = ""
        m_match = re.search(r"Mersis\s*No\s*:\s*(\d+)", text, re.IGNORECASE)
        if m_match:
            mernis_no = m_match.group(1)

        supplier_name = ""
        supplier_tckn = ""
        supplier_vkn = ""
        supplier_tax_office = ""
        supplier_email = ""
        supplier_postal_code = ""
        supplier_city = ""
        supplier_district = ""
        supplier_street = ""
        supplier_building_no = ""
        address_parts = []

        for s in supplier_lines:
            if not s:
                continue

            # TCKN
            tckn_m = re.search(r"TCKN\s*:\s*(\d{10,11})", s)
            if tckn_m:
                supplier_tckn = tckn_m.group(1)
                continue

            # VKN (bağımsız satırda)
            vkn_m = re.match(r"^VKN\s*:\s*(\d{10})$", s)
            if vkn_m:
                supplier_vkn = vkn_m.group(1)
                continue

            # VKN - Vergi Numarası (TTNET formatı: "Vergi Numarası: 8590491872")
            vkn_num_m = re.search(r"Vergi\s*Numaras[ıi]\s*:\s*(\d{10})", s)
            if vkn_num_m:
                supplier_vkn = vkn_num_m.group(1)
                continue

            # HİZMET NO içeren satırı atla (TTNET: "TTNET ANONIM SIRKETI HİZMET NO : 8846748153")
            # Ama önce satıcı adını bu satırdan çıkar
            hizmet_m = re.search(r"H.{0,3}ZMET\s*NO\s*:", s, re.IGNORECASE)
            if hizmet_m:
                name_part = re.split(r"\s+H.{0,3}ZMET\s*NO", s, flags=re.IGNORECASE)[0].strip()
                if name_part and not supplier_name and len(name_part) > 2:
                    supplier_name = name_part
                continue

            # Vergi Dairesi - hem "Vergi Dairesi:" hem "Müşteri Vergi Dairesi:" (TTNET)
            vd_m = re.search(r"(?:Müşteri\s+)?Vergi\s*Dairesi\s*:\s*(.+)", s)
            if vd_m:
                vd_text = vd_m.group(1).strip()
                vd_text = re.split(r"\s*(?:Paket|Hizmet|Erişim|Aylık|Alo|Web|Sicil|Mersis)\s", vd_text, flags=re.IGNORECASE)[0].strip()
                if vd_text:
                    supplier_tax_office = vd_text
                continue

            # E-Posta (sadece e-posta adresini al, sonrasını kes)
            ep_m = re.search(r"E-Posta\s*:\s*([^\s]+@[^\s]+)", s)
            if ep_m:
                supplier_email = ep_m.group(1).strip()
                continue

            # Posta kodu + şehir (TTNET: "34349 Beşiktaş / İSTANBUL FATURA NO : ...")
            pc_m = re.match(r"^(\d{5})\s+(.+?)\s+(?:FATURA|Fatura|Tel:|Vergi|E-Posta|ALO|Web|Sicil)", s)
            if not pc_m:
                pc_m = re.match(r"^(\d{5})\s+(\S+(?:\s+\S+)?)\s*$", s)
            if pc_m and not supplier_city:
                supplier_postal_code = pc_m.group(1)
                city_str = pc_m.group(2).strip()
                if "/" in city_str:
                    # "Beşiktaş / İSTANBUL" → ilçe / şehir
                    parts = [p.strip() for p in city_str.split("/")]
                    if len(parts) == 2:
                        supplier_city = parts[1]
                        supplier_district = parts[0]
                    else:
                        supplier_city = city_str
                else:
                    city_parts_list = city_str.split()
                    if len(city_parts_list) >= 2:
                        supplier_city = " ".join(city_parts_list[-2:])
                address_parts.append(s)
                continue

            # Şehir/İlçe formatı (TTNET: "ÇANKAYA / ANKARA")
            city_slash_m = re.match(r"^(\S+)\s*/\s*(\S+)\s*$", s)
            if city_slash_m and not supplier_city:
                supplier_city = f"{city_slash_m.group(1)} {city_slash_m.group(2)}"
                address_parts.append(s)
                continue

            # Tek "No:" satırını atla
            if s.strip() == "No:":
                continue

            # Mersis No atla (adres kontrolünden önce)
            if re.search(r"Mersis\s*No", s, re.IGNORECASE):
                continue

            # Sicil No atla (adres kontrolünden önce - "No:" içeriyor)
            if re.search(r"Sicil\s*No", s, re.IGNORECASE):
                continue

            # Alo Tarifesi atla (adres kontrolünden önce - "No:" içerebilir)
            if re.search(r"Alo\s*Telifesi", s, re.IGNORECASE):
                continue

            # Metadata satırlarını atla (adres kontrolünden önce - bozuk karakterlere dayanıklı)
            if re.search(r"(?:zelle.tirme|Senaryo|Fatura\s+(?:No|Tarihi|Tarih|Tipi)|Olusturma|ETTN|BU\s+FATURA|SONRAKI|SON\s+.DEME)", s, re.IGNORECASE):
                continue

            # Adres içeren satırlar
            if re.search(r"(?:No[:\s]|Mah\.|Mahallesi|Cad\.|Bulvar|Sokak|Sok\.|Apartman|Kat|Daire|Blo)", s, re.IGNORECASE):
                # TTNET: "Gayrettepe Mahallesi Vefa Bayırı Sokak ALO TEL NO : 31223810"
                # Ekstra metinleri temizle
                clean_addr = re.split(r"\s+ALO\s+TEL\s+NO", s, flags=re.IGNORECASE)[0].strip()
                clean_addr = re.split(r"\s+HIZMET\s+TUR", clean_addr, flags=re.IGNORECASE)[0].strip()
                # "No: 2 Kat: 3" patterninden binanı çıkar
                bno_m = re.search(r"No\s*:\s*(\d+)", clean_addr)
                if bno_m:
                    supplier_building_no = bno_m.group(1)
                # Cadde/sokak: "Mah." içeren kısım
                mah_m = re.match(r"^(.+?\s+Mah(?:allesi)?)\s+(.+?)(?:\s+No\s*:|\s*$)", clean_addr)
                if mah_m:
                    if not supplier_district:
                        supplier_district = mah_m.group(1).replace("Mahallesi", "").replace("Mah.", "").strip()
                    if not supplier_street:
                        supplier_street = clean_addr
                else:
                    if not supplier_street:
                        supplier_street = clean_addr
                address_parts.append(s)
                continue

            # Boş "No:" vs atla
            if re.match(r"^No\s*:?\s*$", s, re.IGNORECASE):
                continue

            # Sayısal-only satırları atla
            if re.match(r"^\d+$", s):
                continue

            # "Sayın" satırını atla
            if re.search(r"Say.+n", s, re.IGNORECASE):
                continue

            # Sayıcı satırlar: yalnızca "e-Fatura" / "e-Arşiv Fatura" etiketinin tamamıysa atla
            # (satır SONUNDA etiket içeren şirket adları atlanmamalı: "SANAYİ VE TİCARET e-Fatura")
            if re.match(r"^(?:e-Fatura|e-Ar.siv\s+Fatura)\s*$", s, re.IGNORECASE):
                continue

            # Tarih/saat satırlarını atla (ör: "19.01.2026 13:35 EFATURA")
            if re.match(r"^\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}", s):
                continue

            # Web/Sicil/Telefon/Faks satırlarını atla
            if re.search(r"(?:Web\s*Sitesi|Sicil\s*No|Tel:|Faks:|ALO\s*TEL|HİZMET\s*TÜR|Erişim\s*(?:Hızı|Şekli)|Alo\s*Telifesi)", s, re.IGNORECASE):
                continue

            # Hala isim tespit edilmediyse ve yeterince uzunsa → muhtemelen satıcı adı
            if not supplier_name and len(s) > 3:
                # Satır sonundaki belge etiketini isimden ayıkla (SAGENİT: "SANAYİ VE TİCARET e-Fatura")
                cand = re.sub(r"\s*(?:e-Fatura|e-Ar.siv\s+Fatura)\s*$", "", s, flags=re.IGNORECASE).strip()
                if len(cand) <= 3:
                    cand = s
                has_company = any(kw.upper() in cand.upper() for kw in SUPPLIER_KEYWORDS)
                if has_company:
                    supplier_name = cand

        # Template ile açık satıcı adı kalıbı (çok satıra yayılan isimler için): keyword sezgisinden öncelikli
        sp = (self.template_meta or {}).get("supplier_name_pattern")
        if sp:
            sm = None
            try:
                sm = re.search(sp, "\n".join(supplier_lines), re.IGNORECASE)
            except re.error:
                sm = None
            if sm:
                try:
                    name_frag = sm.group(1) or sm.group(0)
                except IndexError:
                    name_frag = sm.group(0)
                supplier_name = re.sub(r"\s*(?:e-Fatura|e-Ar.siv\s+Fatura)\s*", " ", name_frag).strip()
                supplier_name = re.sub(r"\s+", " ", supplier_name).strip()

        # Company keyword ile bulunamadıysa, ilk anlamlı satırı al
        if not supplier_name and supplier_lines:
            for s in supplier_lines:
                if len(s) > 3 and not re.match(r"^\d", s):
                    if not re.search(
                        r"(?:E-Posta|Vergi|TCKN|VKN|No:|e-Ar.siv|Fatura|Tel:|Faks:|Mah\.|Cad\.|Sok\.|Bulvar|"
                        r"Sokak|Apartman|^\d{5}\s|[0-9]/\d|MERSIS|SICIL)", s, re.IGNORECASE
                    ):
                        supplier_name = s
                        break

        address = ", ".join(address_parts) if address_parts else ""

        # VKN: Eğer satıcının TCKN'si yoksa, satıcı bloğu içinde VKN ara (şahıs firması)
        if not supplier_vkn and not supplier_tckn:
            supplier_txt = "\n".join(supplier_lines)
            all_nums_10 = re.findall(r"\b(\d{10})\b", supplier_txt)
            for n in all_nums_10:
                if n != mernis_no[:10]:
                    supplier_vkn = n
                    break

        invoice.supplier_name = supplier_name
        invoice.supplier_vkn = supplier_vkn
        invoice.supplier_tckn = supplier_tckn
        invoice.supplier_tax_office = supplier_tax_office
        invoice.supplier_address = address
        invoice.supplier_email = supplier_email
        invoice.supplier_postal_code = supplier_postal_code
        invoice.supplier_city = supplier_city
        invoice.supplier_district = supplier_district
        invoice.supplier_street = supplier_street
        invoice.supplier_building_no = supplier_building_no

        # ─── MÜŞTERİ BLOĞU: Sayın, ile metadata arası ─────────
        if customer_after is None:
            return

        # SAYIN satırından müşteri adını çıkar (TTNET: "SAYIN MÜŞTERİ ADI SON ÖDEME...")
        customer_name_from_sayin = ""
        if sayin_idx >= 0:
            sayin_line = lines[sayin_idx].strip()
            # "Say" + word chars (SAYIN) + space + lazy capture until SON/Tarih/Fatura/ETTN/Vergi/end
            sayin_name_match = re.search(
                r"Say\w*\s+(.+?)(?:\s+SON\b|\s+Tarih\b|\s+Fatura\b|\s+ETTN\b|\s+Vergi\b|$)",
                sayin_line, re.IGNORECASE
            )
            if sayin_name_match:
                customer_name_from_sayin = sayin_name_match.group(1).strip()

        customer_lines = []
        for i in range(customer_after, len(lines)):
            s = lines[i].strip()
            if not s:
                continue
            # Satır içinde metadata keyword'ü varsa, ondan önceki kısmı müşteri olarak al
            meta_split = re.split(r"(\s*.zelle.tirme\s+No\s*:|\s*Senaryo\s*:|\s*Fatura\s+No\s*:|\s*Fatura\s+Tarihi|\s*Fatura\s+Tipi|\s*Olu.turma\s+Zaman|\s*ETTN\s*:|\s*B.R\s+SONRAK.|\s*SON\s+.DEME)", s, flags=re.IGNORECASE)
            if len(meta_split) > 1:
                pre = meta_split[0].strip()
                if pre:
                    customer_lines.append(pre)
                break
            if metadata_starts.search(s):
                break
            customer_lines.append(s)

        customer_name = ""
        customer_vkn = ""
        customer_tckn = ""
        customer_tax_office = ""
        customer_postal_code = ""
        customer_city = ""
        customer_district = ""
        cust_address_parts = []

        for c in customer_lines:
            if not c:
                continue

            # VKN
            vkn_m = re.search(r"VKN\s*:\s*(\d{10})", c)
            if vkn_m:
                customer_vkn = vkn_m.group(1)
                continue

            # VKN - Vergi No (TTNET formatı: "Vergi No: 0851205664")
            vkn_no_m = re.search(r"Vergi\s*No\s*:\s*(\d{10})", c)
            if vkn_no_m:
                customer_vkn = vkn_no_m.group(1)
                continue

            # TCKN
            tckn_m = re.search(r"TCKN\s*:\s*(\d{10,11})", c)
            if tckn_m:
                customer_tckn = tckn_m.group(1)
                continue

            # TCKN/VKN (TTNET: "TCKN/VKN: 7415158717" gibi)
            tckn_vkn_m = re.search(r"TCKN/VKN\s*:\s*(\d{10,11})", c)
            if tckn_vkn_m:
                val = tckn_vkn_m.group(1)
                if len(val) == 10:
                    customer_vkn = val
                else:
                    customer_tckn = val
                continue

            # Vergi Dairesi - hem "Vergi Dairesi:" hem "Müşteri Vergi Dairesi:" (TTNET)
            vd_m = re.search(r"(?:Müşteri\s+)?Vergi\s*Dairesi\s*:\s*(.+)", c)
            if vd_m:
                vd_text = vd_m.group(1).strip()
                # TTNET: extra text temizle ("HESAP NUMARASI : 7038329592" gibi)
                vd_text = re.split(r"\s*HESAP\s*NUMARASI", vd_text, flags=re.IGNORECASE)[0].strip()
                if vd_text:
                    customer_tax_office = vd_text
                continue

            # Posta kodu + şehir
            pc_m = re.match(r"^(\d{5})\s+(.+)$", c)
            if pc_m:
                customer_postal_code = pc_m.group(1)
                city_str = pc_m.group(2).strip()
                city_parts_list = city_str.split()
                if len(city_parts_list) >= 2:
                    customer_city = " ".join(city_parts_list[-2:])
                cust_address_parts.append(c)
                continue

            # Şehir/İlçe formatı (TTNET: "ÇANKAYA / ANKARA")
            city_slash_m = re.match(r"^(\S+)\s*/\s*(\S+)$", c)
            if city_slash_m:
                # İlçe / Şehir formatı: ÇANKAYA ilçe, ANKARA şehir
                customer_district = city_slash_m.group(1)
                customer_city = city_slash_m.group(2)
                cust_address_parts.append(c)
                continue

            # İlçe/İl satırı (örn: "ÇANKAYA ANKARA Türkiye")
            if re.search(r"(?:ANKARA|İSTANBUL|İZMİR|ANTALYA|BURSA|KONYA|GAZİANTEP|KAYSERİ)", c, re.IGNORECASE):
                if "Türkiye" in c or "rkiye" in c:
                    cust_address_parts.append(c)
                    city_m = re.match(r"^(\S+)\s+(\S+)\s+T", c)
                    if city_m:
                        customer_city = f"{city_m.group(1)} {city_m.group(2)}"
                    continue

            # "Türkiye" içeren satırları adres olarak ekle
            if "Türkiye" in c or "rkiye" in c:
                cust_address_parts.append(c)
                continue

            # Boş veya çok kısa
            if len(c) < 3:
                continue

            # Adres içeren satırlar
            if re.search(r"(?:Cad\.|Bulvar|Sokak|Sok\.|Mah\.|No[:\s]|Apartman|Kat|Daire|Blo)", c, re.IGNORECASE):
                cust_address_parts.append(c)
                continue

            # Hala isim tespit edilmediyse → müşteri adı
            # Ama metadata veya toplam satırlarını isim olarak alma
            if not customer_name and len(c) > 2:
                if not re.search(r"(?:TUTAR|Toplam|ÖDEME|ETTN|SONRAKİ|Senaryo|Fatura)", c, re.IGNORECASE):
                    # Satır başındaki e-posta önekini at (SAGENİT: "info@sagenit.com REGNUM...")
                    name_cand = re.sub(r"^\s*\S+@\S+\s+", "", c).strip()
                    if not name_cand:
                        name_cand = c
                    customer_name = name_cand

        customer_address = ", ".join(cust_address_parts) if cust_address_parts else ""

        # SAYIN sonrası satırlarda müşteri VKN / vergi dairesi ara (metadata satırlarından sonra)
        if customer_after is not None:
            tail_text = "\n".join(lines[customer_after:])
            if not customer_vkn and not customer_tckn:
                vp = (self.template_meta or {}).get("customer_vkn_pattern")
                m = None
                if vp:
                    try:
                        m = re.search(vp, tail_text, re.IGNORECASE)
                    except re.error:
                        m = None
                if not m:
                    # Aynı satır içinde etiket+numara (satır atlaması yanlış tarafa kaçabilir)
                    m = re.search(r"\bVKN[ \t]*:?[ \t]*(\d{10})\b", tail_text)
                if not m:
                    m = re.search(r"Vergi\s*No[ \t:]{0,4}(\d{10})\b", tail_text)
                if m and m.group(1) != getattr(invoice, "supplier_vkn", ""):
                    customer_vkn = m.group(1)
            if not customer_tax_office:
                m = re.search(r"Vergi\s*Dairesi\s*:?\s*([^\n,]+)", tail_text)
                if m:
                    vd_txt = m.group(1).strip()
                    vd_txt = re.split(
                        r"\s+(?:Fatura\s*(?:No|Tipi|Tarihi|Saati)|İrsaliye|Müşteri\s*No|Düzenleme)",
                        vd_txt, flags=re.IGNORECASE,
                    )[0].strip()
                    if 1 < len(vd_txt) <= 40:
                        customer_tax_office = vd_txt

        # Metadata satırları müşteri bloğuyla iç içe olduğunda (p28 ADALI gibi)
        # müşteri adı hala boşsa, SAYIN sonrasında ilk anlamlı satırı al
        if not customer_name and not customer_name_from_sayin and customer_after is not None:
            for i in range(customer_after, len(lines)):
                s = lines[i].strip()
                if not s:
                    continue
                if metadata_starts.search(s):
                    continue
                if re.search(
                    r"(?:Senaryo|Fatura\s+(?:No|Tipi|Tarihi|Saati)|İrsaliye|ETTN|Versiyon|"
                    r"Toplam|Matrah|Bakiye|Vadeler|Vade|Sıra\b)",
                    s, re.IGNORECASE,
                ):
                    continue
                if re.match(r"^\d{1,6}\b", s) and re.search(r"TL|TRY", s):
                    continue
                if re.search(r"(?:E-Posta|Web\s*Sitesi|Tel\s*:|Faks)", s, re.IGNORECASE):
                    continue
                if len(s) > 2:
                    customer_name = s
                    break

        # Müşteri adı: her zaman SAYIN satırından gelen ismi tercih et
        if customer_name_from_sayin:
            invoice.customer_name = customer_name_from_sayin
        elif customer_name:
            invoice.customer_name = customer_name
        else:
            invoice.customer_name = ""
        invoice.customer_tckn = customer_tckn
        invoice.customer_vkn = customer_vkn
        invoice.customer_tax_office = customer_tax_office
        invoice.customer_address = customer_address
        invoice.customer_city = customer_city
        invoice.customer_district = customer_district

    # ─── TABLE-BASED EXTRACTION ─────────────────────────────────

    _DEFAULT_COLUMN_MAP = ["no", "code", "name", "qty", "price", "vat_rate", "vat_amount", "other", "total"]

    def _get_column_map(self):
        """Şablondan sütun şemasını alır; yoksa varsayılan TOLASOFT düzenini kullanır."""
        colmap = self.template_meta.get("item_column_map") or []
        if not colmap:
            return list(self._DEFAULT_COLUMN_MAP)
        # Eksik sütun isimleri varsa boş string ile doldur
        return colmap

    def _extract_from_tables_raw(self, tables: list):
        """Tablolardan kalem ve toplamları çıkarır, doğrudan list/dict döner."""
        items = []
        totals = {"gross": 0.0, "net": 0.0, "tax": 0.0}

        colmap = self._get_column_map()

        for table in tables:
            header = self._detect_header_row(table)
            for row in table:
                if not row or not any(row):
                    continue

                first_cell = (row[0] or "").strip()

                if first_cell.isdigit():
                    item = self._parse_table_line_item(row, int(first_cell), colmap)
                    if item:
                        items.append(item)
                    continue

                if row is header:
                    continue

                label = " ".join(str(c or "") for c in row).strip()
                value = self._find_amount_in_row(row)

                if value <= 0:
                    continue

                # "Vergiler Dahil" her zaman tercih edilir (TEVKIFAT'ta Ödenecek düşük olur)
                gross_m = re.search(r"Vergiler\s*Dahil|denecek\s*Tutar|FATURA\s*TUTARI", label, re.IGNORECASE)
                if gross_m:
                    if "Vergiler Dahil" in label or totals["gross"] <= 0:
                        totals["gross"] = value
                elif re.search(r"Hesaplanan\s+(?:Katma\s+De[ğg]er\s+Vergis[ıi]|Kdv|KDV)|KDV\s*GER[ÇC]EK", label, re.IGNORECASE):
                    totals["tax"] = value
                elif re.search(r"Mal\s*(?:/|ve)?\s*Hizmet|Malzeme[ıi]?\s*/\s*Hizmet", label, re.IGNORECASE):
                    totals["net"] = value
                elif re.search(r"\bMatrah|Vergi\s*Hariç\s*Tutar", label):
                    totals["net"] = value

        return items, totals

    def _detect_header_row(self, table: list):
        """Tablonun başlık satırını döndürür (Sıra No / No ile başlayan)."""
        for row in table:
            if not row or not any(row):
                continue
            first_cell = (row[0] or "").strip().lower()
            if re.match(r"s[iı]ra\s*no?.*", first_cell) or first_cell.startswith("sıra") or first_cell == "no":
                return row
        return None

    def _get_cell(self, row, colmap, field):
        """Sütun şemasına göre belirtilen alanın hücre değerini döndürür."""
        for idx, name in enumerate(colmap):
            if name == field:
                return (row[idx] or "").strip() if idx < len(row) else ""
        return ""

    def _extract_from_tables(self, invoice: InvoiceData, tables: list):
        """pdfplumber tablolarından kalem ve toplam bilgilerini çıkarır."""
        items, totals = self._extract_from_tables_raw(tables)

        if items:
            invoice.line_items = items
        if totals["gross"] > 0:
            invoice.total_gross = totals["gross"]
        if totals["net"] > 0:
            invoice.total_net = totals["net"]
        if totals["tax"] > 0:
            invoice.total_tax = totals["tax"]

    def _build_item_from_groups(self, groups: dict, name: str, count: int) -> Optional[InvoiceLineItem]:
        """Şablon item_pattern named-group'larından kalem üretir.

        Desteklenen named group'lar: qty, price, vat_rate, vat_amount, total
        """
        qty = self._parse_quantity(groups.get("qty", ""))
        price = self._parse_turkish_number(groups.get("price", "")) if groups.get("price") else 0.0
        vat_rate = float(groups["vat_rate"]) if groups.get("vat_rate") else 20.0
        vat_amount = self._parse_turkish_number(groups.get("vat_amount", "")) if groups.get("vat_amount") else 0.0
        total = self._parse_turkish_number(groups.get("total", "")) if groups.get("total") else 0.0

        item = InvoiceLineItem(
            line_id=count + 1,
            name=name,
            quantity=qty,
            unit_price_net=price,
            tax_rate=vat_rate,
        )

        if total > 0:
            item.line_total_net = total
        elif price > 0 and qty > 0:
            item.line_total_net = round(price * qty, 2)

        if vat_amount > 0:
            item.tax_amount = vat_amount
        else:
            item.tax_amount = round(item.line_total_net * vat_rate / 100, 2)

        item.gross_price = round(price * (1 + vat_rate / 100), 2) if price > 0 else 0.0

        return item

    def _extract_customer_from_table0(self, invoice: InvoiceData, tables: list):
        """Table T0'nun sol hücresinden eksik müşteri bilgilerini tamamlar.
        
        Mevcut müşteri adını veya VKN'sini override ETMEZ - sadece boş olanları doldurur.
        """
        if not tables or len(tables) < 1:
            return
        t0 = tables[0]
        if len(t0) < 2:
            return

        left_cell = t0[1][0] if len(t0[1]) > 0 else ""
        if not left_cell:
            return

        cell_lines = left_cell.split("\n")
        customer_name = ""
        customer_vkn = ""
        customer_tax_office = ""
        customer_address_parts = []
        customer_city = ""
        customer_postal_code = ""

        for cl in cell_lines:
            cl = cl.strip()
            if not cl:
                continue

            if re.search(r"Say.+n\s*,", cl, re.IGNORECASE):
                continue

            vkn_m = re.search(r"VKN\s*:\s*(\d{10})", cl)
            if vkn_m:
                customer_vkn = vkn_m.group(1)
                continue

            vd_m = re.search(r"Vergi\s*Dairesi\s*:\s*(.+)", cl)
            if vd_m:
                customer_tax_office = vd_m.group(1).strip()
                continue

            pc_m = re.match(r"^(\d{5})\s+(.+)$", cl)
            if pc_m:
                customer_postal_code = pc_m.group(1)
                customer_address_parts.append(cl)
                city_parts = pc_m.group(2).strip().split()
                if len(city_parts) >= 2:
                    customer_city = " ".join(city_parts[-2:])
                continue

            if re.search(r"(?:ANKARA|İSTANBUL|İZMİR|ANTALYA|BURSA|KONYA|GAZİANTEP)", cl, re.IGNORECASE):
                if "rkiye" in cl or "Türkiye" in cl:
                    customer_address_parts.append(cl)
                    city_m = re.match(r"^(\S+)\s+(\S+)\s+T", cl)
                    if city_m:
                        customer_city = f"{city_m.group(1)} {city_m.group(2)}"
                    continue

            if "rkiye" in cl or "Türkiye" in cl:
                customer_address_parts.append(cl)
                continue

            if len(cl) < 3:
                continue

            if not customer_name:
                customer_name = cl

        # Sadece BOŞ olan alanları doldur - mevcut bilgileri KORU
        if customer_name and not invoice.customer_name:
            invoice.customer_name = customer_name
        if customer_vkn and not invoice.customer_vkn:
            invoice.customer_vkn = customer_vkn
        if customer_tax_office and not invoice.customer_tax_office:
            invoice.customer_tax_office = customer_tax_office
        if customer_address_parts and not invoice.customer_address:
            invoice.customer_address = ", ".join(customer_address_parts)
        if customer_city and not invoice.customer_city:
            invoice.customer_city = customer_city
        if customer_postal_code and not invoice.customer_postal_code:
            invoice.customer_postal_code = customer_postal_code

    def _parse_table_line_item(self, row: list, line_id: int, colmap: list = None) -> Optional[InvoiceLineItem]:
        """Tablo satırından kalem ürünü parse eder.

        Varsayılan PDF yapısı (TOLASOFT):
        [sira_no, kod, ad, miktar, birim_fiyat, kdv%, kdv_tutari, diger, tutar]
        Farklı sütun düzenleri 'colmap' (sütun şeması) ile desteklenir.
        'Birim Fiyat' = net birim fiyat, 'Tutar' = net satır toplamı
        """
        if colmap is None:
            colmap = self._DEFAULT_COLUMN_MAP
        if len(row) < 4:
            return None

        def get(field: str) -> str:
            for idx, name in enumerate(colmap):
                if name == field:
                    return (row[idx] or "").strip() if idx < len(row) else ""
            return ""

        stock_code = get("code")
        name = get("name")
        quantity_str = get("qty")
        price_str = get("price")
        kdv_percent_str = get("vat_rate")
        kdv_amount_str = get("vat_amount")
        total_str = get("total")

        quantity = self._parse_quantity(quantity_str)
        unit_price_net = self._parse_turkish_number(price_str) if price_str else 0.0
        kdv_percent = self._parse_kdv_percent(kdv_percent_str)
        kdv_amount = self._parse_turkish_number(kdv_amount_str.replace("TL", "").strip()) if kdv_amount_str else 0.0
        line_total_net = self._parse_turkish_number(total_str.replace("TL", "").strip()) if total_str else 0.0

        item = InvoiceLineItem(
            line_id=line_id,
            name=name,
            stock_code=stock_code,
            quantity=quantity,
            unit_price_net=unit_price_net,
            tax_rate=kdv_percent,
        )

        # Doğrudan PDF'ten gelen net değerleri kullan
        if line_total_net > 0:
            item.line_total_net = line_total_net
        elif unit_price_net > 0 and quantity > 0:
            item.line_total_net = round(unit_price_net * quantity, 2)

        if kdv_amount > 0:
            item.tax_amount = kdv_amount
        else:
            item.tax_amount = round(item.line_total_net * kdv_percent / 100, 2)

        item.gross_price = round(unit_price_net * (1 + kdv_percent / 100), 2) if unit_price_net > 0 else 0.0

        return item

    def _parse_quantity(self, qty_str: str) -> float:
        """Miktar string'ini sayıya çevirir. '3 Boy', '7 Adet', '1.000 Adet', '3.506,66|Ton' formatları."""
        if not qty_str:
            return 1.0
        qty_str = qty_str.strip()
        # sayısal olmayan ilk karakterden itibaren her şeyi at (birim, |Ton, vs.)
        first_bad = re.search(r"[^\d.,\-]", qty_str)
        if first_bad:
            qty_str = qty_str[:first_bad.start()]
        return self._parse_turkish_number(qty_str) if qty_str else 1.0

    def _parse_kdv_percent(self, kdv_str: str) -> float:
        """'%20' formatından KDV oranını çıkarır."""
        m = re.search(r"%?\s*(\d+)", kdv_str)
        if m:
            return float(m.group(1))
        return 20.0

    def _find_amount_in_row(self, row: list) -> float:
        """Tablo satırındaki TL içeren tutarı bulur."""
        for cell in row:
            if cell:
                cell_str = str(cell).strip()
                if "TL" in cell_str:
                    num_str = cell_str.replace("TL", "").strip()
                    val = self._parse_turkish_number(num_str)
                    if val > 0:
                        return val
        return 0.0

    # ─── TEXT-BASED LINE ITEM EXTRACTION (fallback) ────────────

    def _extract_line_items_from_text(self, invoice: InvoiceData, lines: list):
        """Tablo yoksa metin tabanlı kalem çıkarma (fallback).

        Desteklenen formatlar:
        1. Media Markt: "1 AB-123 Ürün Adı 3 Adet 100,00 TL"
        2. TTNET: "İnternet 1.009,99 0,00 1.009,99" (hizmet adı + 3 tutar)
        """
        items = []
        in_items_section = False

        # ── Şablon tabanlı metin pattern'i (tablosuz formatlar için) ──
        item_pattern = self.template_meta.get("item_pattern")
        if item_pattern:
            compiled = re.compile(item_pattern)
            skip_compiled = [re.compile(p, re.IGNORECASE) for p in self.template_meta.get("item_skip_patterns", [])]
            parsed = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped:
                    continue
                m = compiled.match(stripped)
                if not m:
                    continue
                groups = m.groupdict()
                name = groups.get("name", "").strip()
                if not name:
                    continue
                # Bir sonraki satır isim devamı olabilir
                if i + 1 < len(lines) and lines[i + 1].strip():
                    nxt = lines[i + 1].strip()
                    if compiled.match(nxt) is None and not re.search(r"(?:TL|TRY)\s*$|^\d", nxt):
                        name = f"{name} {nxt}"
                if any(sc.search(name) for sc in skip_compiled):
                    continue
                item = self._build_item_from_groups(groups, name, len(parsed))
                if item:
                    parsed.append(item)
            if parsed:
                invoice.line_items = parsed
                return

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # Media Markt formatı: "Sıra No Hizmet" başlığı
            if re.search(r"S.+\s+r.n\s*Hizmet", stripped, re.IGNORECASE):
                in_items_section = True
                continue

            # TTNET formatı: "Tutar İndirim Toplam" başlığı
            if re.search(r"Tutar\s+İndirim\s+Toplam", stripped, re.IGNORECASE):
                in_items_section = True
                continue

            if not in_items_section:
                continue

            # Toplam satırlarında dur
            if re.search(r"(?:Mal\s*Hizmet|Toplam|KDV|Matrah|Yaln.z|denecek|e-Ar.iv|TOPLAM|DEVLETE|Yuvarlama|Önceki|Gelecek)", stripped, re.IGNORECASE):
                break

            # Media Markt formatı: "1 AB-123 Ürün Adı ..."
            if re.match(r"^\d+\s+[A-Z]{2,}-\d+", stripped):
                item = self._parse_text_line_item(stripped, lines, i, len(items))
                if item:
                    items.append(item)
                continue

            # TTNET formatı: "İnternet 1.009,99 0,00 1.009,99" (hizmet adı + 3 tutar)
            ttnet_match = re.match(
                r"^(.+?)\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})$",
                stripped
            )
            if ttnet_match:
                name = ttnet_match.group(1).strip()
                # Toplam satırı ise atla (Paket Ücreti = İnternet + Telefon toplamı)
                if re.search(r"(?:Toplam|Ara\s*Toplam|Genel|Fatura\s*Toplam|Paket\s+[UÜ]creti)", name, re.IGNORECASE):
                    continue
                # Tutar, İndirim, Toplam
                amount = self._parse_turkish_number(ttnet_match.group(2))
                discount = self._parse_turkish_number(ttnet_match.group(3))
                total = self._parse_turkish_number(ttnet_match.group(4))

                item = InvoiceLineItem(
                    line_id=len(items) + 1,
                    name=name,
                    quantity=1.0,
                    unit_price_net=total,
                    line_total_net=total,
                    tax_rate=20.0,
                )
                items.append(item)
                continue

            # TTNET: "Katma Değerli Servis Ücretler Toplamı 175,00" (tek tutar)
            kds_match = re.match(r"^(Katma Değerli.+?)\s+([\d.]+,\d{2})$", stripped)
            if kds_match:
                name = kds_match.group(1).strip()
                total = self._parse_turkish_number(kds_match.group(2))
                item = InvoiceLineItem(
                    line_id=len(items) + 1,
                    name=name,
                    quantity=1.0,
                    unit_price_net=total,
                    line_total_net=total,
                    tax_rate=20.0,
                )
                items.append(item)
                continue

        invoice.line_items = items

    def _parse_text_line_item(self, line: str, all_lines: list, idx: int, item_count: int) -> Optional[InvoiceLineItem]:
        """Metin satırından kalem ürünü parse eder."""
        parts = line.split()
        if len(parts) < 5:
            return None

        line_id = item_count + 1
        stock_code = parts[1] if len(parts) > 1 else ""

        # Koddan sonra gelene kadar消费 名を構築
        name_parts = []
        i = 2
        while i < len(parts):
            p = parts[i]
            if re.match(r"^\d+(\.\d+)?\s*(Adet|Boy|Kg|Lt|M2|M3|Set|Paket)$", p, re.IGNORECASE):
                break
            if re.match(r"^\d+\s+(Adet|Boy|Kg|Lt)", p, re.IGNORECASE):
                break
            name_parts.append(p)
            i += 1

        name = " ".join(name_parts).strip()

        # Bir sonraki satır ürün adı devamı olabilir
        if idx + 1 < len(all_lines):
            next_line = all_lines[idx + 1].strip()
            if next_line and not re.match(r"^\d+\s+[A-Z]{2,}-\d+", next_line):
                if not re.search(r"(?:Toplam|KDV|Matrah|e-Ar.iv)", next_line, re.IGNORECASE):
                    name = f"{name} {next_line}"

        # KDV ve fiyat bilgilerini ayıkla
        tl_amounts = re.findall(r"([\d.]+,\d{2})\s*TL", line)

        item = InvoiceLineItem(
            line_id=line_id,
            name=name,
            stock_code=stock_code,
        )

        if len(tl_amounts) >= 3:
            item.unit_price_net = self._parse_turkish_number(tl_amounts[0])
            item.tax_amount = self._parse_turkish_number(tl_amounts[1])
            item.line_total_net = self._parse_turkish_number(tl_amounts[2])
        elif len(tl_amounts) >= 2:
            item.unit_price_net = self._parse_turkish_number(tl_amounts[0])
            item.line_total_net = self._parse_turkish_number(tl_amounts[1])

        item.tax_rate = 20.0

        return item

    # ─── TEXT-BASED TOTALS EXTRACTION (fallback) ───────────────

    def _extract_totals_from_text(self, invoice: InvoiceData, text: str):
        """Tablo yoksa metin tabanlı toplam çıkarma.

        Desteklenen formatlar:
        - Media Markt: "Vergiler Dahil Toplam Tutar 50.466,00"
        - TTNET: "TOPLAM FATURA TUTARI 1.315,00"
        """
        gross = self._search_first(text, "total_gross")
        if gross:
            invoice.total_gross = self._parse_turkish_number(gross)

        net = self._search_first(text, "total_net")
        if net:
            invoice.total_net = self._parse_turkish_number(net)

        kdv = self._search_first(text, "total_tax_kdv")
        if kdv:
            invoice.total_tax = self._parse_turkish_number(kdv)

        # ÖTV varsa KDV'ye ekle (TTNET: KDV + ÖTV = toplam vergi)
        otv = self._search_first(text, "total_tax_otv")
        if otv:
            invoice.total_tax += self._parse_turkish_number(otv)

        # Matrah (net) placeholder pattern - TTNET: "KDV %20 (Matrah 1.011.54 )"
        if invoice.total_net == 0:
            matrah_m = re.search(r"Matrah\s+([\d.]+[\d.]*)", text, re.IGNORECASE)
            if matrah_m:
                invoice.total_net = self._parse_turkish_number(matrah_m.group(1))

    # ─── UTILITY ────────────────────────────────────────────────

    def _search_first(self, text: str, pattern_key: str) -> Optional[str]:
        patterns = self.patterns.get(pattern_key, [])
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if match:
                if match.lastindex and match.lastindex >= 1:
                    return match.group(1).strip()
                return match.group(0).strip()
        return None

    def _search_groups(self, text: str, pattern_key: str):
        patterns = self.patterns.get(pattern_key, [])
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.groups()
        return None

    @staticmethod
    def _parse_turkish_number(num_str: str) -> float:
        cleaned = num_str.replace(" ", "").replace("TL", "").strip()
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        elif "." in cleaned:
            parts = cleaned.split(".")
            if len(parts) >= 3:
                # Birden fazla nokta → binlik ayraçları kaldır, sondaki ondalık olarak koru
                cleaned = "".join(parts[:-1]) + "." + parts[-1]
            elif len(parts[-1]) == 3 and all(p.isdigit() for p in parts):
                cleaned = cleaned.replace(".", "")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def _add_warnings(self, invoice: InvoiceData):
        if not invoice.invoice_id:
            invoice.parse_warnings.append("Fatura numarasi tespit edilemedi")
        if not invoice.issue_date:
            invoice.parse_warnings.append("Fatura tarihi tespit edilemedi")
        if not invoice.supplier_name:
            invoice.parse_warnings.append("Satici bilgisi tespit edilemedi")
        if not invoice.supplier_vkn and not invoice.supplier_tckn:
            invoice.parse_warnings.append("Satici VKN/TCKN tespit edilemedi")
        if not invoice.customer_name:
            invoice.parse_warnings.append("Alici bilgisi tespit edilemedi")
        if not invoice.customer_tckn and not invoice.customer_vkn:
            invoice.parse_warnings.append("Alici TCKN/VKN tespit edilemedi")
        if not invoice.line_items:
            invoice.parse_warnings.append("Fatura kalemleri cikarilamadi")
        if invoice.total_gross == 0:
            invoice.parse_warnings.append("Toplam tutar tespit edilemedi")
