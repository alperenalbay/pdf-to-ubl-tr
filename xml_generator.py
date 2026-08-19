"""
UBL-TR E-Arşiv Fatura XML Oluşturucu
Ayırıştırılmış fatura verisinden geçerli UBL-TR XML'i üretir
"""

import xml.etree.ElementTree as ET

from config import (
    UBL_NAMESPACES,
    UBL_VERSION,
    CUSTOMIZATION_ID,
    CURRENCY,
    DEFAULT_TAX_TYPE_CODE,
    DEFAULT_UNIT_CODE,
)
from invoice_parser import InvoiceData, InvoiceLineItem


class UBLTriGenerator:
    """UBL-TR formatında e-arşiv fatura XML'i üreten sınıf."""

    def __init__(self):
        self.ns = UBL_NAMESPACES

    def generate(self, invoice: InvoiceData) -> str:
        """InvoiceData'dan UBL-TR XML string'i üretir."""
        root = self._build_root(invoice)
        self._add_ubl_extensions(root)
        self._add_header(root, invoice)
        self._add_additional_refs(root, invoice)
        self._add_signature(root, invoice)
        self._add_supplier_party(root, invoice)
        self._add_customer_party(root, invoice)
        self._add_tax_total(root, invoice)
        self._add_monetary_total(root, invoice)
        self._add_invoice_lines(root, invoice)
        return self._to_pretty_xml(root)

    def generate_file(self, invoice: InvoiceData, output_path: str):
        """XML'i dosyaya yazar."""
        xml_str = self.generate(invoice)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_str)

    def _build_root(self, invoice: InvoiceData) -> ET.Element:
        """Root Invoice elementini oluşturur."""
        root = ET.Element("Invoice")
        root.set("xmlns", self.ns["root"])
        root.set("xmlns:cac", self.ns["cac"])
        root.set("xmlns:cbc", self.ns["cbc"])
        root.set("xmlns:ext", self.ns["ext"])
        return root

    def _add_sub(self, parent: ET.Element, tag: str, text: str = "", attrib: dict = None) -> ET.Element:
        """cbc: veya cac: prefix'li alt element ekler."""
        elem = ET.SubElement(parent, tag)
        if text:
            elem.text = str(text)
        if attrib:
            for k, v in attrib.items():
                elem.set(k, str(v))
        return elem

    def _add_cac_sub(self, parent: ET.Element, tag: str) -> ET.Element:
        """cac: prefix'li alt element ekler."""
        return ET.SubElement(parent, f"cac:{tag}")

    def _add_ubl_extensions(self, root: ET.Element):
        """ext:UBLExtensions bloğunu ekler."""
        ext = ET.SubElement(root, "ext:UBLExtensions")
        ext_elem = ET.SubElement(ext, "ext:UBLExtension")
        content = ET.SubElement(ext_elem, "ext:ExtensionContent")
        ET.SubElement(content, "auto-generated-wildcard")

    def _add_header(self, root: ET.Element, inv: InvoiceData):
        """Fatura başlık bilgilerini ekler."""
        self._add_sub(root, "cbc:UBLVersionID", UBL_VERSION)
        self._add_sub(root, "cbc:CustomizationID", CUSTOMIZATION_ID)

        profile = inv.profile_id or "EARSIVFATURA"
        self._add_sub(root, "cbc:ProfileID", profile)
        self._add_sub(root, "cbc:ID", inv.invoice_id)
        self._add_sub(root, "cbc:CopyIndicator", "false")
        self._add_sub(root, "cbc:UUID", inv.uuid)

        if inv.issue_date:
            self._add_sub(root, "cbc:IssueDate", inv.issue_date)
        if inv.issue_time:
            self._add_sub(root, "cbc:IssueTime", inv.issue_time)

        self._add_sub(root, "cbc:InvoiceTypeCode", inv.invoice_type)

        if inv.note:
            for note_part in inv.note.split(". "):
                note_part = note_part.strip()
                if note_part:
                    self._add_sub(root, "cbc:Note", note_part)

        self._add_sub(root, "cbc:DocumentCurrencyCode", CURRENCY)
        self._add_sub(root, "cbc:LineCountNumeric", str(len(inv.line_items)))

    def _add_additional_refs(self, root: ET.Element, inv: InvoiceData):
        """Ek referans bilgilerini ekler."""
        ref = self._add_cac_sub(root, "AdditionalDocumentReference")
        self._add_sub(ref, "cbc:ID", "2")
        self._add_sub(ref, "cbc:IssueDate", inv.issue_date or "2026-01-01")
        self._add_sub(ref, "cbc:DocumentTypeCode", "GONDERIM_SEKLI")
        self._add_sub(ref, "cbc:DocumentType", "ELEKTRONIK")

    def _add_signature(self, root: ET.Element, inv: InvoiceData):
        """İmza bloğunu ekler."""
        sig = self._add_cac_sub(root, "Signature")
        sig_id = inv.supplier_vkn or inv.supplier_tckn or "0000000000"
        self._add_sub(sig, "cbc:ID", sig_id, {"schemeID": "VKN_TCKN"})

        party = self._add_cac_sub(sig, "SignatoryParty")
        pid = self._add_cac_sub(party, "PartyIdentification")
        self._add_sub(pid, "cbc:ID", sig_id, {"schemeID": "VKN"})

        addr = self._add_cac_sub(party, "PostalAddress")
        self._add_sub(addr, "cbc:StreetName", inv.supplier_street or "")
        self._add_sub(addr, "cbc:BuildingNumber", inv.supplier_building_no or "")
        self._add_sub(addr, "cbc:CitySubdivisionName", inv.supplier_district or "")
        self._add_sub(addr, "cbc:CityName", inv.supplier_city or "")
        country = ET.SubElement(addr, "cac:Country")
        self._add_sub(country, "cbc:Name", "Türkiye")

        ext_ref = self._add_cac_sub(
            self._add_cac_sub(sig, "DigitalSignatureAttachment"),
            "ExternalReference",
        )
        self._add_sub(ext_ref, "cbc:URI", f"#Signature_{inv.uuid}")

    def _add_supplier_party(self, root: ET.Element, inv: InvoiceData):
        """Satıcı (Supplier) tarafını ekler. PDF'in üst bloğundaki bilgiler."""
        party_wrap = self._add_cac_sub(root, "AccountingSupplierParty")
        party = self._add_cac_sub(party_wrap, "Party")

        # VKN veya TCKN
        pid = self._add_cac_sub(party, "PartyIdentification")
        vkn = inv.supplier_vkn or inv.supplier_tckn or "0000000000"
        scheme = "VKN" if len(vkn) == 10 else "TCKN"
        self._add_sub(pid, "cbc:ID", vkn, {"schemeID": scheme})

        pname = self._add_cac_sub(party, "PartyName")
        self._add_sub(pname, "cbc:Name", inv.supplier_name or "Bilinmiyor")

        addr = self._add_cac_sub(party, "PostalAddress")
        self._add_sub(addr, "cbc:StreetName", inv.supplier_street or "")
        self._add_sub(addr, "cbc:BuildingNumber", inv.supplier_building_no or "")
        self._add_sub(addr, "cbc:CitySubdivisionName", inv.supplier_district or "")
        self._add_sub(addr, "cbc:CityName", inv.supplier_city or "")
        self._add_sub(addr, "cbc:PostalZone", inv.supplier_postal_code or "")
        country = ET.SubElement(addr, "cac:Country")
        self._add_sub(country, "cbc:IdentificationCode", "TR", {"name": "Türkiye"})
        self._add_sub(country, "cbc:Name", "Türkiye")

        if inv.supplier_tax_office:
            tax_scheme = self._add_cac_sub(self._add_cac_sub(party, "PartyTaxScheme"), "TaxScheme")
            self._add_sub(tax_scheme, "cbc:Name", inv.supplier_tax_office)

        if inv.supplier_email:
            contact = ET.SubElement(party, "cac:Contact")
            self._add_sub(contact, "cbc:ElectronicMail", inv.supplier_email)

    def _add_customer_party(self, root: ET.Element, inv: InvoiceData):
        """Alıcı (Customer) tarafını ekler. PDF'in 'Sayın,' bloğundaki bilgiler."""
        party_wrap = self._add_cac_sub(root, "AccountingCustomerParty")
        party = self._add_cac_sub(party_wrap, "Party")

        # TCKN veya VKN
        pid = self._add_cac_sub(party, "PartyIdentification")
        tckn = inv.customer_tckn or inv.customer_vkn or "00000000000"
        scheme = "TCKN" if len(tckn) == 11 else "VKN"
        self._add_sub(pid, "cbc:ID", tckn, {"schemeID": scheme})

        pname = self._add_cac_sub(party, "PartyName")
        self._add_sub(pname, "cbc:Name", inv.customer_name or "Bilinmiyor")

        addr = self._add_cac_sub(party, "PostalAddress")
        self._add_sub(addr, "cbc:StreetName", inv.customer_street or "")
        self._add_sub(addr, "cbc:CitySubdivisionName", inv.customer_district or "")
        self._add_sub(addr, "cbc:CityName", inv.customer_city or "")
        country = ET.SubElement(addr, "cac:Country")
        self._add_sub(country, "cbc:IdentificationCode", "TR", {"name": "Türkiye"})
        self._add_sub(country, "cbc:Name", "Türkiye")

        if inv.customer_tax_office:
            tax_scheme = self._add_cac_sub(self._add_cac_sub(party, "PartyTaxScheme"), "TaxScheme")
            self._add_sub(tax_scheme, "cbc:Name", inv.customer_tax_office)

    def _add_tax_total(self, root: ET.Element, inv: InvoiceData):
        """Vergi toplamını ekler."""
        tax_total = self._add_cac_sub(root, "TaxTotal")
        self._add_sub(
            tax_total, "cbc:TaxAmount",
            f"{inv.total_tax:.2f}",
            {"currencyID": CURRENCY},
        )

        tax_sub = self._add_cac_sub(tax_total, "TaxSubtotal")
        self._add_sub(
            tax_sub, "cbc:TaxableAmount",
            f"{inv.total_net:.2f}",
            {"currencyID": CURRENCY},
        )
        self._add_sub(
            tax_sub, "cbc:TaxAmount",
            f"{inv.total_tax:.2f}",
            {"currencyID": CURRENCY},
        )
        self._add_sub(tax_sub, "cbc:CalculationSequenceNumeric", "1")
        self._add_sub(tax_sub, "cbc:Percent", str(int(inv.tax_rate)))

        tax_cat = self._add_cac_sub(tax_sub, "TaxCategory")
        tax_scheme = self._add_cac_sub(tax_cat, "TaxScheme")
        self._add_sub(tax_scheme, "cbc:Name", f"KDV (%{int(inv.tax_rate)})")
        self._add_sub(tax_scheme, "cbc:TaxTypeCode", DEFAULT_TAX_TYPE_CODE)

    def _add_monetary_total(self, root: ET.Element, inv: InvoiceData):
        """Para birimi toplamlarını ekler."""
        total = self._add_cac_sub(root, "LegalMonetaryTotal")

        attr = {"currencyID": CURRENCY}
        self._add_sub(total, "cbc:LineExtensionAmount", f"{inv.total_net:.2f}", attr)
        self._add_sub(total, "cbc:TaxExclusiveAmount", f"{inv.total_net:.2f}", attr)
        self._add_sub(total, "cbc:TaxInclusiveAmount", f"{inv.total_gross:.2f}", attr)
        self._add_sub(total, "cbc:AllowanceTotalAmount", "0", attr)
        self._add_sub(total, "cbc:PayableAmount", f"{inv.total_gross:.2f}", attr)

    def _add_invoice_lines(self, root: ET.Element, inv: InvoiceData):
        """Fatura kalemlerini ekler."""
        for item in inv.line_items:
            self._add_single_line(root, item)

    def _add_single_line(self, root: ET.Element, item: InvoiceLineItem):
        """Tek bir fatura kalem satırını ekler."""
        line = self._add_cac_sub(root, "InvoiceLine")
        self._add_sub(line, "cbc:ID", str(item.line_id))

        note_parts = []
        if item.stock_code:
            note_parts.append(f"Stok Kodu: {item.stock_code}")
        if item.serial_no:
            note_parts.append(f"Seri No: {item.serial_no}")
        if note_parts:
            self._add_sub(line, "cbc:Note", " ".join(note_parts))

        self._add_sub(
            line, "cbc:InvoicedQuantity",
            f"{item.quantity:.2f}",
            {"unitCode": item.unit_code},
        )
        self._add_sub(
            line, "cbc:LineExtensionAmount",
            f"{item.line_total_net:.2f}",
            {"currencyID": CURRENCY},
        )

        tax_total = self._add_cac_sub(line, "TaxTotal")
        self._add_sub(
            tax_total, "cbc:TaxAmount",
            f"{item.tax_amount:.2f}",
            {"currencyID": CURRENCY},
        )

        tax_sub = self._add_cac_sub(tax_total, "TaxSubtotal")
        self._add_sub(
            tax_sub, "cbc:TaxableAmount",
            f"{item.line_total_net:.2f}",
            {"currencyID": CURRENCY},
        )
        self._add_sub(
            tax_sub, "cbc:TaxAmount",
            f"{item.tax_amount:.2f}",
            {"currencyID": CURRENCY},
        )
        self._add_sub(tax_sub, "cbc:CalculationSequenceNumeric", str(item.line_id))
        self._add_sub(tax_sub, "cbc:Percent", str(int(item.tax_rate)))

        tax_cat = self._add_cac_sub(tax_sub, "TaxCategory")
        tax_scheme = self._add_cac_sub(tax_cat, "TaxScheme")
        self._add_sub(tax_scheme, "cbc:Name", f"KDV (%{int(item.tax_rate)})")
        self._add_sub(tax_scheme, "cbc:TaxTypeCode", DEFAULT_TAX_TYPE_CODE)

        item_elem = self._add_cac_sub(line, "Item")
        self._add_sub(item_elem, "cbc:Name", item.name or "Bilinmeyen Ürün")
        sellers_id = self._add_cac_sub(item_elem, "SellersItemIdentification")
        self._add_sub(sellers_id, "cbc:ID", item.stock_code or "")

        price = self._add_cac_sub(line, "Price")
        self._add_sub(
            price, "cbc:PriceAmount",
            f"{item.unit_price_net:.8f}",
            {"currencyID": CURRENCY},
        )

    def _to_pretty_xml(self, root: ET.Element) -> str:
        """XML elementini biçimlendirilmiş string'e dönüştürür."""
        ET.indent(root, space="  ")
        rough = ET.tostring(root, encoding="unicode", xml_declaration=False)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + rough
