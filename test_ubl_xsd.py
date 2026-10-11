#!/usr/bin/env python3
"""
UBL 2.1 resmî XSD'sine karşı gerçek şema doğrulaması.

Bu, `test_xml_generator.py` ile tamamlayıcıdır: oradaki testler üretilen
yapıyı elle denetler, buradaki ise belgeyi **resmî şemaya** karşı
doğrular. İkisi birbirinin yerine geçmez.

UBL 2.1 InvoiceType'ta `minOccurs` belirtilmemiş, yani zorunlu olan
altı eleman: ID, IssueDate, AccountingSupplierParty,
AccountingCustomerParty, LegalMonetaryTotal, InvoiceLine.

Şemalar repoda tutulmaz (2,8 MB). İlk kez:

    ./fetch_ubl_xsd.sh

Şema bulunamazsa bu dosya sessizce **atlanır** — temel suite yine
bağımlılıksız çalışır. Doğrulamayı gerçekten çalıştırmak için `lxml`
gerekir; o da yalnızca bu testte kullanılır.

Ortam değişkeniyle dizin değiştirilebilir:

    UBL_XSD_DIR=/path/to/schemas python -m unittest test_ubl_xsd -v
"""

import os
import unittest
import xml.etree.ElementTree as ET

from invoice_parser import InvoiceData, InvoiceLineItem
from xml_generator import UBLTriGenerator

# fetch_ubl_xsd.sh şemaları ubl-xsd/common/ altına koyar: UBL-Invoice.xsd
# ortak şemaları ../common/ yolundan çekiyor, yani yükleme ortak
# dizininden yapılmalı.
_BASE = os.environ.get("UBL_XSD_DIR") or os.path.join(
    os.path.dirname(__file__), "ubl-xsd")
COMMON_DIR = os.path.join(_BASE, "common")
INVOICE_XSD = os.path.join(COMMON_DIR, "UBL-Invoice-2.1.xsd")

try:
    from lxml import etree as _lxml
except ImportError:  # pragma: no cover
    _lxml = None

_SCHEMA = None
_SCHEMA_ERROR = None

if _lxml is not None and os.path.isfile(INVOICE_XSD):
    try:
        # Şema, ortak şemaları ../common/ üzerinden çekiyor; bu yüzden
        # dizinin içinden yüklenmeli.
        _SCHEMA = _lxml.XMLSchema(_lxml.parse(INVOICE_XSD))
    except Exception as exc:  # pragma: no cover
        _SCHEMA_ERROR = str(exc)


def full_invoice(**overrides):
    """Şemayı geçmesi beklenen tam bir fatura."""
    base = dict(
        invoice_id="INV-2026-001",
        uuid="11111111-2222-3333-4444-555555555555",
        invoice_type="1",
        issue_date="2026-10-11",
        supplier_name="Satıcı A.Ş.",
        supplier_vkn="1234567890",
        supplier_tax_office="Marmara",
        supplier_city="İstanbul",
        supplier_district="Kadıköy",
        supplier_street="Moda Caddesi",
        supplier_building_no="12",
        supplier_postal_code="34710",
        supplier_email="info@satici.example",
        customer_name="Müşteri Ltd. Şti.",
        customer_vkn="9876543210",
        customer_city="Ankara",
        customer_district="Çankaya",
        customer_street="Atatürk Bulvarı",
        total_net=100.0,
        total_tax=20.0,
        total_gross=120.0,
        tax_rate=20.0,
        line_items=[
            InvoiceLineItem(
                line_id=1, name="Ürün", stock_code="S1", serial_no="SN-1",
                quantity=2.0, unit_price_net=50.0, line_total_net=100.0,
                tax_rate=20.0, tax_amount=20.0,
            ),
        ],
    )
    base.update(overrides)
    return InvoiceData(**base)


@unittest.skipIf(_lxml is None, "lxml kurulu değil; XSD doğrulaması atlandı")
@unittest.skipIf(not os.path.isfile(INVOICE_XSD),
                 f"UBL şemaları bulunamadı ({INVOICE_XSD}); "
                 "indirmek için: ./fetch_ubl_xsd.sh")
@unittest.skipIf(_SCHEMA is None, f"UBL şeması derlenemedi: {_SCHEMA_ERROR}")
class UBLSchemaValidationTest(unittest.TestCase):
    """Üretilen belgeler resmî UBL 2.1 şemasına uymalı."""

    def assert_valid(self, invoice, label):
        xml = UBLTriGenerator().generate(invoice)
        doc = _lxml.fromstring(xml.encode("utf-8"))
        self.assertTrue(
            _SCHEMA.validate(doc),
            f"{label} şemaya uymuyor:\n"
            + "\n".join(str(e) for e in _SCHEMA.error_log),
        )

    def test_single_line_invoice(self):
        self.assert_valid(full_invoice(), "tek kalemli fatura")

    def test_mixed_tax_rates(self):
        """P0-1'in düzeltmesi: oran başına ayrı TaxSubtotal şemada geçerli."""
        inv = full_invoice(
            total_net=200.0, total_tax=30.0, total_gross=230.0,
            line_items=[
                InvoiceLineItem(line_id=1, name="A", quantity=1.0,
                                unit_price_net=100.0, line_total_net=100.0,
                                tax_rate=20.0, tax_amount=20.0),
                InvoiceLineItem(line_id=2, name="B", quantity=1.0,
                                unit_price_net=100.0, line_total_net=100.0,
                                tax_rate=10.0, tax_amount=10.0),
            ],
        )
        self.assert_valid(inv, "karma KDV oranlı fatura")

    def test_tckn_supplier(self):
        """P1-3'ün düzeltmesi: TCKN'li satıcı şemada sorun çıkarmamalı."""
        inv = full_invoice(supplier_vkn=None, supplier_tckn="12345678901")
        self.assert_valid(inv, "TCKN'li satıcı")

    def test_fractional_tax_rate(self):
        """P1-4'ün düzeltmesi: ondalıklı oran şemada geçerli kalmalı."""
        inv = full_invoice(
            total_net=100.0, total_tax=7.5, total_gross=107.5, tax_rate=7.5,
            line_items=[
                InvoiceLineItem(line_id=1, name="Ürün", quantity=1.0,
                                unit_price_net=100.0, line_total_net=100.0,
                                tax_rate=7.5, tax_amount=7.5),
            ],
        )
        self.assert_valid(inv, "ondalıklı KDV oranı")

    def test_turkish_characters(self):
        """Türkçe karakterler şemayı etkilememeli."""
        inv = full_invoice(
            supplier_name="İşğÜÇÖŞĞİ A.Ş.",
            customer_name="ĞÜŞİÖÇ ÖRNEK Ltd.",
        )
        self.assert_valid(inv, "Türkçe karakterli unvanlar")

    def test_many_lines(self):
        inv = full_invoice(
            total_net=300.0, total_tax=60.0, total_gross=360.0,
            line_items=[
                InvoiceLineItem(line_id=i, name=f"Ürün {i}", quantity=1.0,
                                unit_price_net=100.0, line_total_net=100.0,
                                tax_rate=20.0, tax_amount=20.0)
                for i in range(1, 4)
            ],
        )
        self.assert_valid(inv, "çok kalemli fatura")

    def test_missing_date_is_rejected_not_written(self):
        """Eksik zorunlu alan sessizce geçersiz belge üretmemeli."""
        with self.assertRaises(ValueError):
            UBLTriGenerator().generate(full_invoice(issue_date=None))

    def test_element_order_matches_schema(self):
        """Üretilen sıra, InvoiceType dizilimiyle uyumlu olmalı.

        cac:Signature, AccountingSupplierParty'den **önce** gelir; bu
        şemada böyle. (Şüpheyle başlamıştık, XSD doğruladı: doğruymuş.)
        """
        expected = [
            f"{{{NS_EXT}}}UBLExtensions",
            f"{{{NS_CBC}}}UBLVersionID",
            f"{{{NS_CBC}}}CustomizationID",
            f"{{{NS_CBC}}}ProfileID",
            f"{{{NS_CBC}}}ID",
            f"{{{NS_CBC}}}CopyIndicator",
            f"{{{NS_CBC}}}UUID",
            f"{{{NS_CBC}}}IssueDate",
            f"{{{NS_CBC}}}InvoiceTypeCode",
            f"{{{NS_CBC}}}DocumentCurrencyCode",
            f"{{{NS_CBC}}}LineCountNumeric",
            f"{{{NS_CAC}}}AdditionalDocumentReference",
            f"{{{NS_CAC}}}Signature",
            f"{{{NS_CAC}}}AccountingSupplierParty",
            f"{{{NS_CAC}}}AccountingCustomerParty",
            f"{{{NS_CAC}}}TaxTotal",
            f"{{{NS_CAC}}}LegalMonetaryTotal",
            f"{{{NS_CAC}}}InvoiceLine",
        ]
        xml = UBLTriGenerator().generate(full_invoice())
        actual = [c.tag for c in ET.fromstring(xml)]
        self.assertEqual(actual, expected)


NS_ROOT = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS_EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"


if __name__ == "__main__":
    unittest.main(verbosity=2)