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

    def __init__(self):
        self.patterns = REGEX_PATTERNS

    def parse(self, text: str, source_file: str = "", tables: list = None) -> InvoiceData:
        invoice = InvoiceData(raw_text=text, source_file=source_file)
        lines = text.split("\n")

        self._extract_header_fields(invoice, text)
        self._extract_parties(invoice, lines, text)

        if tables:
            self._extract_from_tables(invoice, tables)
        else:
            self._extract_line_items_from_text(invoice, lines)
            self._extract_totals_from_text(invoice, text)

        invoice.recalculate_totals()
        invoice.generate_uuid()
        invoice.ensure_id()
        self._add_warnings(invoice)
        return invoice

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
                invoice.issue_time = clean

        inv_type = self._search_first(text, "invoice_type")
        if inv_type and inv_type.upper() in ("IADE",):
            invoice.invoice_type = "IADE"

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

        PDF yapısı:
            [0] e-Arşiv Fatura              ← belge başlığı
            [1-8] satıcı bilgileri (ad, adres, VD, TCKN)
            [9] Sayın, ...                  ← müşteri başlangıcı
            [10-17] müşteri bilgileri + metadata (Fatura No, Tarih vb.)
            [18+] kalemler, toplamlar
        """
        sayin_idx = -1
        for i, line in enumerate(lines):
            if re.search(r"Say.+n\s*,", line.strip(), re.IGNORECASE):
                sayin_idx = i
                break

        # Metadata bitiş göstergeleri
        metadata_starts = re.compile(
            r"(?:.zelle.tirme\s+No|Senaryo\s*:|Fatura\s+No\s*:|Fatura\s+Tarihi|Fatura\s+Tipi|Olu.turma\s+Zaman)",
            re.IGNORECASE
        )

        # ─── SATICI BLOĞU: line 0 (header label) ile Sayın, arası ──
        supplier_lines = []
        if sayin_idx > 0:
            supplier_lines = [l.strip() for l in lines[1:sayin_idx] if l.strip()]
        elif sayin_idx == -1:
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

            # Vergi Dairesi
            vd_m = re.search(r"Vergi\s*Dairesi\s*:\s*(.+)", s)
            if vd_m:
                supplier_tax_office = vd_m.group(1).strip()
                continue

            # E-Posta
            ep_m = re.search(r"E-Posta\s*:\s*(.+)", s)
            if ep_m:
                supplier_email = ep_m.group(1).strip()
                continue

            # Posta kodu + şehir (örn: "06830 GÖLBAŞI ANKARA")
            pc_m = re.match(r"^(\d{5})\s+(.+)$", s)
            if pc_m:
                supplier_postal_code = pc_m.group(1)
                city_str = pc_m.group(2).strip()
                city_parts_list = city_str.split()
                if city_parts_list:
                    supplier_city = " ".join(city_parts_list[-2:]) if len(city_parts_list) >= 2 else city_parts_list[0]
                address_parts.append(s)
                continue

            # Tek "No:" satırını atla
            if s.strip() == "No:":
                continue

            # Adres içeren satırlar
            if re.search(r"(?:No[:\s]|Mah\.|Cad\.|Bulvar|Sokak|Sok\.|Apartman|Kat|Daire|Blo)", s, re.IGNORECASE):
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

            # Sayıcı satırlar (EArşiv vs) atla
            if re.search(r"e-Ar.siv\s+Fatura|e-Fatura", s, re.IGNORECASE):
                continue

            # Hala isim tespit edilmediyse ve yeterince uzunsa → muhtemelen satıcı adı
            if not supplier_name and len(s) > 3:
                has_company = any(kw.upper() in s.upper() for kw in SUPPLIER_KEYWORDS)
                if has_company:
                    supplier_name = s

        # Company keyword ile bulunamadıysa, ilk anlamlı satırı al
        if not supplier_name and supplier_lines:
            for s in supplier_lines:
                if len(s) > 3 and not re.match(r"^\d", s):
                    if not re.search(r"(?:E-Posta|Vergi|TCKN|No:|e-Ar.siv|Fatura)", s, re.IGNORECASE):
                        supplier_name = s
                        break

        address = ", ".join(address_parts) if address_parts else ""

        # VKN: Eğer satıcının TCKN'si varsa VKN arama (şahıs firması)
        if not supplier_vkn and not supplier_tckn:
            all_nums_10 = re.findall(r"\b(\d{10})\b", text)
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

        # ─── MÜŞTERİ BLOĞU: Sayın, ile metadata arası ─────────
        if sayin_idx < 0:
            return

        customer_lines = []
        for i in range(sayin_idx + 1, len(lines)):
            s = lines[i].strip()
            if not s:
                continue
            # Satır içinde metadata keyword'ü varsa, ondan önceki kısmı müşteri olarak al
            meta_split = re.split(r"(\s*.zelle.tirme\s+No\s*:|\s*Senaryo\s*:|\s*Fatura\s+No\s*:|\s*Fatura\s+Tarihi|\s*Fatura\s+Tipi|\s*Olu.turma\s+Zaman)", s, flags=re.IGNORECASE)
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
        cust_address_parts = []

        for c in customer_lines:
            if not c:
                continue

            # VKN
            vkn_m = re.search(r"VKN\s*:\s*(\d{10})", c)
            if vkn_m:
                customer_vkn = vkn_m.group(1)
                continue

            # TCKN
            tckn_m = re.search(r"TCKN\s*:\s*(\d{10,11})", c)
            if tckn_m:
                customer_tckn = tckn_m.group(1)
                continue

            # Vergi Dairesi
            vd_m = re.search(r"Vergi\s*Dairesi\s*:\s*(.+)", c)
            if vd_m:
                customer_tax_office = vd_m.group(1).strip()
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
            if not customer_name and len(c) > 2:
                customer_name = c

        customer_address = ", ".join(cust_address_parts) if cust_address_parts else ""

        invoice.customer_name = customer_name
        invoice.customer_tckn = customer_tckn
        invoice.customer_vkn = customer_vkn
        invoice.customer_tax_office = customer_tax_office
        invoice.customer_address = customer_address
        invoice.customer_city = customer_city

    # ─── TABLE-BASED EXTRACTION ─────────────────────────────────

    def _extract_from_tables(self, invoice: InvoiceData, tables: list):
        """pdfplumber tablolarından kalem ve toplam bilgilerini çıkarır.

        Tablo yapısı:
          T0: Müşteri + Metadata (sol-sağ)
          T1: Kalem satırları [sira_no, kod, ad, miktar, birim_fiyat, kdv%, kdv_tutari, diger, tutar]
          T2: Toplam satırları
        """
        items = []
        totals = {"gross": 0.0, "net": 0.0, "tax": 0.0}

        for table in tables:
            for row in table:
                if not row or not any(row):
                    continue

                first_cell = (row[0] or "").strip()

                # Kalem satırı: ilk hücre sayısal (sira no)
                if first_cell.isdigit():
                    item = self._parse_table_line_item(row, int(first_cell))
                    if item:
                        items.append(item)
                    continue

                # Toplam satırları: label-value çiftleri
                label = " ".join(str(c or "") for c in row).strip()
                value = self._find_amount_in_row(row)

                if value <= 0:
                    continue

                if "Vergiler Dahil" in label or "denecek Tutar" in label:
                    totals["gross"] = value
                elif "Hesaplanan KDV" in label:
                    totals["tax"] = value
                elif "Matrah" in label:
                    totals["net"] = value
                elif "Mal Hizmet Toplam" in label:
                    totals["net"] = value

        if items:
            invoice.line_items = items

        if totals["gross"] > 0:
            invoice.total_gross = totals["gross"]
        if totals["net"] > 0:
            invoice.total_net = totals["net"]
        if totals["tax"] > 0:
            invoice.total_tax = totals["tax"]

        # Table T0'dan müşteri bilgisi çek (VKN/TCKN, VD, adres eksikliklerini tamamla)
        if tables:
            self._extract_customer_from_table0(invoice, tables)

    def _extract_customer_from_table0(self, invoice: InvoiceData, tables: list):
        """Table T0'nun sol hücresinden müşteri bilgilerini çıkarır."""
        if not tables or len(tables) < 1:
            return
        t0 = tables[0]
        if len(t0) < 2:
            return

        # Sol hücre: müşteri bilgisi (Sayın,\nAdres\n...\nVKN: xxxxx)
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

        if customer_name:
            invoice.customer_name = customer_name
        if customer_vkn:
            invoice.customer_vkn = customer_vkn
        if customer_tax_office:
            invoice.customer_tax_office = customer_tax_office
        if customer_address_parts:
            invoice.customer_address = ", ".join(customer_address_parts)
        if customer_city:
            invoice.customer_city = customer_city
        if customer_postal_code:
            invoice.customer_postal_code = customer_postal_code

    def _parse_table_line_item(self, row: list, line_id: int) -> Optional[InvoiceLineItem]:
        """Tablo satırından kalem ürünü parse eder.

        PDF yapısı:
        [sira_no, kod, ad, miktar, birim_fiyat, kdv%, kdv_tutari, diger, tutar]
        'Birim Fiyat' = net birim fiyat, 'Tutar' = net satır toplamı
        """
        if len(row) < 6:
            return None

        stock_code = (row[1] or "").strip()
        name = (row[2] or "").strip()
        quantity_str = (row[3] or "").strip()
        price_str = (row[4] or "").strip()
        kdv_percent_str = (row[5] or "").strip()
        kdv_amount_str = (row[6] or "").strip() if len(row) > 6 else ""
        total_str = (row[8] or "").strip() if len(row) > 8 else (row[7] or "").strip() if len(row) > 7 else ""

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
        """Miktar string'ini sayıya çevirir. '3 Boy', '7 Adet', '1.000 Adet' formatları."""
        if not qty_str:
            return 1.0
        qty_str = qty_str.strip()
        qty_str = re.sub(r"\s*(Adet|Boy|Kg|Lt|Mt|M2|M3|Set|Paket|Kutu|Palet|Ton|gram|litre|metre).*", "", qty_str, flags=re.IGNORECASE)
        qty_str = qty_str.strip()
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
        """Tablo yoksa metin tabanlı kalem çıkarma (fallback)."""
        items = []
        in_items_section = False

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            if re.search(r"S.+\s+r.n\s*Hizmet", stripped, re.IGNORECASE):
                in_items_section = True
                continue

            if not in_items_section:
                continue

            if re.search(r"(?:Mal\s*Hizmet|Toplam|KDV|Matrah|Yaln.z|denecek|e-Ar.iv)", stripped, re.IGNORECASE):
                break

            if re.match(r"^\d+\s+[A-Z]{2,}-\d+", stripped):
                item = self._parse_text_line_item(stripped, lines, i, len(items))
                if item:
                    items.append(item)

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
        """Tablo yoksa metin tabanlı toplam çıkarma."""
        gross = self._search_first(text, "total_gross")
        if gross:
            invoice.total_gross = self._parse_turkish_number(gross)

        net = self._search_first(text, "total_net")
        if net:
            invoice.total_net = self._parse_turkish_number(net)

        kdv = self._search_first(text, "total_tax_kdv")
        if kdv:
            invoice.total_tax = self._parse_turkish_number(kdv)

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
            if len(parts[-1]) == 3 and all(p.isdigit() for p in parts):
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
