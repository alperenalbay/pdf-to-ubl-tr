#!/usr/bin/env python3
"""
UBL-TR XML üretimi için birim testleri.

Kapsam bilinçli olarak dar: PDF ayrıştırma değil, **XML üretimi**.
Faturalar elle kurulmuş InvoiceData ile üretilir, böylece:
  - testler PDF dosyasına ve pdfplumber'a bağımlı olmaz
  - .gitignore'daki `*.pdf` kuralı testleri engellemez
  - her test tek bir davranışı izole eder

Çalıştırma:
    python -m unittest test_xml_generator -v
    python test_xml_generator.py

--- KNOWN DEFECT işaretleri hakkında ---
`# KNOWN DEFECT` ile işaretli testler mevcut (kusurlu) davranışı **yeşil** olarak
pınlar. Amaçları şu:

  1. Düzeltme yapıldığında o satırı değiştirmek, düzeltmeyi kanıtlar.
  2. Kod kaza ile bozulursa test kızar, sessizce kaymaz.

Bunları "geçmesi gereken davranış" gibi okuma — bilinen hataların kaydıdır.
"""

import unittest
import xml.etree.ElementTree as ET

from invoice_parser import InvoiceData, InvoiceLineItem
from xml_generator import UBLTriGenerator

NS_ROOT = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS_EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"


def make_item(**kw):
    """Tek satırlık InvoiceLineItem. Varsayılanlar %20 KDV'li basit bir kalem."""
    base = dict(
        line_id=1,
        name="Ürün",
        stock_code="S1",
        quantity=1.0,
        unit_price_net=100.0,
        line_total_net=100.0,
        tax_amount=20.0,
        tax_rate=20.0,
    )
    base.update(kw)
    return InvoiceLineItem(**base)


def make_invoice(**kw):
    """Geçerli bir fatura için InvoiceData. Tek satır, %20 KDV."""
    base = dict(
        invoice_id="INV-001",
        uuid="11111111-2222-3333-4444-555555555555",
        invoice_type="1",
        issue_date="2026-10-11",
        supplier_name="Satıcı A.Ş.",
        supplier_vkn="1234567890",
        supplier_tax_office="Marmara",
        supplier_city="İstanbul",
        supplier_district="Kadıköy",
        customer_name="Müşteri Ltd. Şti.",
        customer_vkn="9876543210",
        customer_city="Ankara",
        total_net=100.0,
        total_tax=20.0,
        total_gross=120.0,
        tax_rate=20.0,
        line_items=[make_item()],
    )
    base.update(kw)
    return InvoiceData(**base)


class UBLNamespacesTest(unittest.TestCase):
    """Namespace ilanı ve çözümlemesi."""

    def test_root_is_invoice_namespace(self):
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))
        self.assertEqual(root.tag, f"{{{NS_ROOT}}}Invoice")

    def test_all_four_prefixes_declared(self):
        xml = UBLTriGenerator().generate(make_invoice())
        for prefix, uri in (("cac", NS_CAC), ("cbc", NS_CBC), ("ext", NS_EXT)):
            self.assertIn(f'xmlns:{prefix}="{uri}"', xml)
        self.assertIn(f'xmlns="{NS_ROOT}"', xml)

    def test_prefixed_children_resolve_on_reparse(self):
        """Yazarken prefix'ler literal metin olarak yazılıyor; geri okuma
        sırasında gerçek namespace'e çözülmeli. Aksi halde üretilen XML
        geçerli görünür ama işlenemez olurdu."""
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))
        self.assertIsNotNone(root.find(f"{{{NS_CBC}}}ID"))
        self.assertIsNotNone(root.find(f"{{{NS_CAC}}}AccountingSupplierParty"))
        self.assertIsNotNone(root.find(f"{{{NS_EXT}}}UBLExtensions"))


class RequiredElementsTest(unittest.TestCase):
    """Belge iskeletinde bulunması gereken zorunlu bloklar."""

    def setUp(self):
        self.root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))

    def test_header_fields_present(self):
        cbc = f"{{{NS_CBC}}}"
        for tag in ("UBLVersionID", "CustomizationID", "ProfileID", "ID",
                    "UUID", "IssueDate", "InvoiceTypeCode",
                    "DocumentCurrencyCode", "LineCountNumeric"):
            self.assertIsNotNone(self.root.find(cbc + tag), f"eksik: {tag}")

    def test_party_blocks_present(self):
        cac = f"{{{NS_CAC}}}"
        self.assertIsNotNone(self.root.find(cac + "AccountingSupplierParty"))
        self.assertIsNotNone(self.root.find(cac + "AccountingCustomerParty"))

    def test_monetary_totals_present(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        total = self.root.find(cac + "LegalMonetaryTotal")
        self.assertIsNotNone(total)
        for tag in ("LineExtensionAmount", "TaxExclusiveAmount",
                    "TaxInclusiveAmount", "PayableAmount"):
            self.assertIsNotNone(total.find(cbc + tag), f"eksik: {tag}")

    def test_one_invoice_line_per_item(self):
        cac = f"{{{NS_CAC}}}"
        inv = make_invoice(line_items=[make_item(line_id=1), make_item(line_id=2)])
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        self.assertEqual(len(root.findall(cac + "InvoiceLine")), 2)

    def test_line_count_numeric_matches_items(self):
        cbc = f"{{{NS_CBC}}}"
        inv = make_invoice(line_items=[make_item(line_id=1), make_item(line_id=2)])
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        self.assertEqual(root.find(cbc + "LineCountNumeric").text, "2")


class AmountsTest(unittest.TestCase):
    """Tutar hesaplarının tutarlılığı."""

    def test_payable_equals_gross(self):
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        inv = make_invoice(total_net=200.0, total_tax=30.0, total_gross=230.0,
                           line_items=[make_item(line_id=1, line_total_net=200.0,
                                                 unit_price_net=200.0,
                                                 tax_amount=30.0)])
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        total = root.find(cac + "LegalMonetaryTotal")
        self.assertEqual(total.find(cbc + "PayableAmount").text, "230.00")
        self.assertEqual(total.find(cbc + "TaxExclusiveAmount").text, "200.00")
        self.assertEqual(total.find(cbc + "TaxInclusiveAmount").text, "230.00")

    def test_amounts_rendered_with_two_decimals(self):
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))
        total = root.find(cac + "LegalMonetaryTotal")
        for tag in ("PayableAmount", "TaxExclusiveAmount"):
            text = total.find(cbc + tag).text
            self.assertRegex(text, r"^\d+\.\d{2}$", f"{tag} = {text}")

    def test_currency_is_try(self):
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))
        self.assertEqual(root.find(cbc + "DocumentCurrencyCode").text, "TRY")
        amount = root.find(cac + "LegalMonetaryTotal").find(cbc + "PayableAmount")
        self.assertEqual(amount.get("currencyID"), "TRY")


class TextHandlingTest(unittest.TestCase):
    """Türkçe karakterler ve XML kaçışları."""

    def test_turkish_characters_survive_roundtrip(self):
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        inv = make_invoice(supplier_name="İşğÜçÖŞĞİ Ltd.")
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        name = root.find(cac + "AccountingSupplierParty").find(
            f"{cac}Party/{cac}PartyName/{cbc}Name")
        self.assertEqual(name.text, "İşğÜçÖŞĞİ Ltd.")

    def test_xml_special_characters_escaped(self):
        """A & B gibi karakterler ham çıkarsa XML'i bozar."""
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        inv = make_invoice(supplier_name="A & B <Ltd>")
        xml = UBLTriGenerator().generate(inv)
        self.assertIn("&amp;", xml)
        self.assertNotIn("<Ltd>", xml)
        root = ET.fromstring(xml)
        name = root.find(cac + "AccountingSupplierParty").find(
            f"{cac}Party/{cac}PartyName/{cbc}Name")
        self.assertEqual(name.text, "A & B <Ltd>")

    def test_note_split_on_sentences(self):
        cbc = f"{{{NS_CBC}}}"
        inv = make_invoice(note="Birinci not. İkinci not.")
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        notes = [e.text for e in root.findall(cbc + "Note")]
        # Asimetrik davranış: bölme ". " ile yapıldığı için son parça noktayı
        # korur. Muhtemelen kastedilen davranış değil, ama üretim hatası olarak
        # işaretlenmedi — kasıtlı olabilir. Gerekirse buradan ele alınır.
        self.assertEqual(notes, ["Birinci not", "İkinci not."])


class DeterminismTest(unittest.TestCase):
    def test_same_input_gives_identical_output(self):
        inv = make_invoice()
        self.assertEqual(
            UBLTriGenerator().generate(inv),
            UBLTriGenerator().generate(inv),
        )


class FileOutputTest(unittest.TestCase):
    def test_generate_file_writes_parseable_xml(self):
        import os
        import tempfile

        gen = UBLTriGenerator()
        inv = make_invoice()
        expected = gen.generate(inv)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.xml")
            gen.generate_file(inv, path)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), expected)
            ET.parse(path)  # parse edilebilir olmalı


# ---------------------------------------------------------------------------
# Aşağıdakiler BİLİNEN HATALARI pınlar. Yeşil olmalılar.
# Düzeltildiğinde beklenti değişir ve o satır düzeltmenin kanıtı olur.
# ---------------------------------------------------------------------------


class TaxTotalGroupingTest(unittest.TestCase):
    """Belge seviyesi TaxTotal, kalemleri KDV oranına göre gruplar.

    Bu sınıf P0-1'in düzeltmesini sabitler. Önceden tek subtotal yazılıyordu
    ("200.00 matrah @ %20 = 30.00"), ki 200 × %20 = 40. Aritmetik tutmuyordu.
    """

    MIXED = dict(
        total_net=200.0, total_tax=30.0, total_gross=230.0, tax_rate=20.0,
        line_items=[
            make_item(line_id=1, line_total_net=100.0, unit_price_net=100.0,
                      tax_rate=20.0, tax_amount=20.0),
            make_item(line_id=2, line_total_net=100.0, unit_price_net=100.0,
                      tax_rate=10.0, tax_amount=10.0),
        ],
    )

    def test_one_subtotal_per_distinct_rate(self):
        cac = f"{{{NS_CAC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(**self.MIXED)))
        subtotals = root.find(f"{cac}TaxTotal").findall(cac + "TaxSubtotal")
        self.assertEqual(len(subtotals), 2)

    def test_each_subtotal_arithmetic_is_consistent(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(**self.MIXED)))
        for sub in root.find(f"{cac}TaxTotal").findall(cac + "TaxSubtotal"):
            taxable = float(sub.find(cbc + "TaxableAmount").text)
            percent = float(sub.find(cbc + "Percent").text)
            tax = float(sub.find(cbc + "TaxAmount").text)
            self.assertAlmostEqual(taxable * percent / 100, tax, places=2)

    def test_subtotals_carry_expected_values(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(**self.MIXED)))
        got = [
            (s.find(cbc + "Percent").text,
             s.find(cbc + "TaxableAmount").text,
             s.find(cbc + "TaxAmount").text)
            for s in root.find(f"{cac}TaxTotal").findall(cac + "TaxSubtotal")
        ]
        # oranlar yükselen sırada
        self.assertEqual(got, [("10", "100.00", "10.00"), ("20", "100.00", "20.00")])

    def test_subtotals_sum_to_document_totals(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(**self.MIXED)))
        total = root.find(cac + "TaxTotal")
        subs = total.findall(cac + "TaxSubtotal")
        self.assertAlmostEqual(
            sum(float(s.find(cbc + "TaxAmount").text) for s in subs),
            float(total.find(cbc + "TaxAmount").text),
            places=2,
        )

    def test_single_rate_invoice_still_has_one_subtotal(self):
        cac = f"{{{NS_CAC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))
        self.assertEqual(
            len(root.find(f"{cac}TaxTotal").findall(cac + "TaxSubtotal")), 1)

    def test_sequence_numbers_are_sequential_from_one(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(**self.MIXED)))
        seqs = [
            s.find(cbc + "CalculationSequenceNumeric").text
            for s in root.find(f"{cac}TaxTotal").findall(cac + "TaxSubtotal")
        ]
        self.assertEqual(seqs, ["1", "2"])

    def test_tax_scheme_name_matches_rate(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(**self.MIXED)))
        names = [
            s.find(f"{cac}TaxCategory/{cac}TaxScheme/{cbc}Name").text
            for s in root.find(f"{cac}TaxTotal").findall(cac + "TaxSubtotal")
        ]
        self.assertEqual(names, ["KDV (%10)", "KDV (%20)"])

    def test_float_noise_does_not_create_extra_group(self):
        """19.9999999 ve 20.0 aynı grupta olmalı."""
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        inv = make_invoice(
            total_net=200.0, total_tax=40.0, total_gross=240.0,
            line_items=[
                make_item(line_id=1, line_total_net=100.0, unit_price_net=100.0,
                          tax_rate=19.9999999, tax_amount=20.0),
                make_item(line_id=2, line_total_net=100.0, unit_price_net=100.0,
                          tax_rate=20.0, tax_amount=20.0),
            ],
        )
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        subs = root.find(f"{cac}TaxTotal").findall(cac + "TaxSubtotal")
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].find(cbc + "TaxableAmount").text, "200.00")

    def test_line_level_rates_unchanged(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(**self.MIXED)))
        percents = [
            e.text for e in root.findall(f"{cac}InvoiceLine/{cac}TaxTotal/"
                                         f"{cac}TaxSubtotal/{cbc}Percent")
        ]
        self.assertEqual(sorted(percents), ["10", "20"])

    def test_no_lines_produces_no_subtotal(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        inv = make_invoice(line_items=[], total_net=0.0, total_tax=0.0,
                           total_gross=0.0)
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        total = root.find(cac + "TaxTotal")
        self.assertEqual(len(total.findall(cac + "TaxSubtotal")), 0)
        self.assertEqual(total.find(cbc + "TaxAmount").text, "0.00")


class IssueDateTest(unittest.TestCase):
    """Fatura tarihi eksikken davranış.

    Düzeltme öncesi `_add_additional_refs`, tarih yoksa sabit `2026-01-01`
    yazıyordu — yasal belgeye uydurma tarih. Artık alan atlanıyor; eksik
    tarih için `parse_warnings` zaten uyarı üretiyor.
    """

    def _dates_in_document(self, xml):
        """Belgedeki tüm IssueDate değerleri."""
        root = ET.fromstring(xml)
        cbc = f"{{{NS_CBC}}}"
        return [e.text for e in root.iter(cbc + "IssueDate")]

    def test_missing_date_omits_additional_document_reference_date(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(issue_date=None)))
        ref = root.find(cac + "AdditionalDocumentReference")
        self.assertIsNone(ref.find(cbc + "IssueDate"))

    def test_missing_date_omits_header_date(self):
        cbc = f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(issue_date=None)))
        self.assertIsNone(root.find(cbc + "IssueDate"))

    def test_no_fabricated_date_anywhere(self):
        """Belgenin hiçbir yerinde 2026-01-01 olmamalı."""
        xml = UBLTriGenerator().generate(make_invoice(issue_date=None))
        self.assertNotIn("2026-01-01", xml)
        self.assertEqual(self._dates_in_document(xml), [])

    def test_present_date_is_written_in_both_places(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))
        self.assertEqual(root.find(cbc + "IssueDate").text, "2026-10-11")
        ref = root.find(cac + "AdditionalDocumentReference")
        self.assertEqual(ref.find(cbc + "IssueDate").text, "2026-10-11")

    def test_surrounding_fields_survive_missing_date(self):
        """Tarih atlanınca referans bloğu dağıtmamalı."""
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(issue_date=None)))
        ref = root.find(cac + "AdditionalDocumentReference")
        self.assertEqual(ref.find(cbc + "ID").text, "2")
        self.assertEqual(ref.find(cbc + "DocumentTypeCode").text, "GONDERIM_SEKLI")
        self.assertEqual(ref.find(cbc + "DocumentType").text, "ELEKTRONIK")

    def test_document_still_parses_without_date(self):
        """Eksik tarih XML'i geçersiz kılmamalı."""
        xml = UBLTriGenerator().generate(make_invoice(issue_date=None))
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, f"{{{NS_ROOT}}}Invoice")


class SupplierSchemeTest(unittest.TestCase):
    """Satır kimliğinin şeması (VKN/TCKN).

    Düzeltme öncesi `_add_signature`, `schemeID="VKN"`'yi sabitliyordu;
    TCKN'li bir satıcıda kimlik TCKN olmasına rağmen VKN diye etiketleniyordu.
    Aynı anda `_add_supplier_party` doğru hesaplıyordu, yani belgenin iki
    bölgesi birbiriyle çelişiyordu.

    Kural artık `_supplier_scheme` içinde tek yerde: VKN 10 hane, TCKN 11.
    """

    VKN = "1234567890"      # 10 hane
    TCKN = "12345678901"    # 11 hane

    def _signatory_scheme(self, root):
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        e = root.find(f"{cac}Signature/{cac}SignatoryParty/"
                      f"{cac}PartyIdentification/{cbc}ID")
        return e.get("schemeID")

    def _supplier_party_scheme(self, root):
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        e = root.find(f"{cac}AccountingSupplierParty/{cac}Party/"
                      f"{cac}PartyIdentification/{cbc}ID")
        return e.get("schemeID")

    def test_tckn_supplier_signatory_is_tckn(self):
        inv = make_invoice(supplier_vkn=None, supplier_tckn=self.TCKN)
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        self.assertEqual(self._signatory_scheme(root), "TCKN")

    def test_vkn_supplier_signatory_is_vkn(self):
        inv = make_invoice(supplier_vkn=self.VKN, supplier_tckn=None)
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        self.assertEqual(self._signatory_scheme(root), "VKN")

    def test_both_regions_agree_on_tckn(self):
        """Düzeltmenin asıl amacı: iki bölge aynı şemayı söylemeli."""
        inv = make_invoice(supplier_vkn=None, supplier_tckn=self.TCKN)
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        self.assertEqual(self._signatory_scheme(root),
                         self._supplier_party_scheme(root))

    def test_both_regions_agree_on_vkn(self):
        inv = make_invoice(supplier_vkn=self.VKN, supplier_tckn=None)
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        self.assertEqual(self._signatory_scheme(root),
                         self._supplier_party_scheme(root))

    def test_signature_id_keeps_combined_scheme(self):
        """En üstteki cbc:ID 'VKN_TCKN' kalmalı — o ikisini de kapsıyor."""
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        inv = make_invoice(supplier_vkn=None, supplier_tckn=self.TCKN)
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        top = root.find(f"{cac}Signature/{cbc}ID")
        self.assertEqual(top.get("schemeID"), "VKN_TCKN")
        self.assertEqual(top.text, self.TCKN)

    def test_scheme_rule_helper_directly(self):
        gen = UBLTriGenerator()
        self.assertEqual(gen._supplier_scheme(self.VKN), "VKN")
        self.assertEqual(gen._supplier_scheme(self.TCKN), "TCKN")


class TaxRateFormattingTest(unittest.TestCase):
    """KDV oranının yazımı.

    Düzeltme öncesi `str(int(rate))` kullanılıyordu; bu ondalık oranları
    kırpıyordu (7.5 -> "7") ve float artığını sessizce bozuyordu
    (19.999999999999996 -> "19"). Artık `%g` ile yazılıyor.
    """

    def _percent(self, root):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        return root.find(f"{cac}TaxTotal/{cac}TaxSubtotal/{cbc}Percent").text

    def _scheme_name(self, root):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        return root.find(f"{cac}TaxTotal/{cac}TaxSubtotal/{cac}TaxCategory/"
                         f"{cac}TaxScheme/{cbc}Name").text

    def _invoice_with_rate(self, rate, tax_amount=7.5):
        return make_invoice(
            total_net=100.0, total_tax=tax_amount,
            total_gross=100.0 + tax_amount, tax_rate=rate,
            line_items=[make_item(line_total_net=100.0, unit_price_net=100.0,
                                  tax_rate=rate, tax_amount=tax_amount)],
        )

    def test_fractional_rate_preserved(self):
        root = ET.fromstring(UBLTriGenerator().generate(
            self._invoice_with_rate(7.5)))
        self.assertEqual(self._percent(root), "7.5")

    def test_amount_and_rate_agree(self):
        """Tutar 7.50 iken oran da 7.5 — daha önce oran 7 yazıyordu."""
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(
            self._invoice_with_rate(7.5)))
        sub = root.find(f"{cac}TaxTotal/{cac}TaxSubtotal")
        self.assertEqual(sub.find(cbc + "TaxAmount").text, "7.50")
        self.assertEqual(sub.find(cbc + "Percent").text, "7.5")

    def test_integer_rate_has_no_decimal_noise(self):
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))
        self.assertEqual(self._percent(root), "20")
        self.assertNotIn(".", self._percent(root))

    def test_float_artifact_rounds_to_intended_rate(self):
        """19.999999999999996 gerçekte %20; int() onu "19" yapıyordu."""
        root = ET.fromstring(UBLTriGenerator().generate(
            self._invoice_with_rate(19.999999999999996, tax_amount=20.0)))
        self.assertEqual(self._percent(root), "20")

    def test_ordinary_division_artifact(self):
        """20/100*100 gibi gerçek bölme artığı da bozulmamalı."""
        rate = 20 / 100 * 100
        root = ET.fromstring(UBLTriGenerator().generate(
            self._invoice_with_rate(rate, tax_amount=20.0)))
        self.assertEqual(self._percent(root), "20")

    def test_scheme_name_matches_percent(self):
        root = ET.fromstring(UBLTriGenerator().generate(
            self._invoice_with_rate(7.5)))
        self.assertEqual(self._scheme_name(root), "KDV (%7.5)")

    def test_line_level_rate_preserved_too(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(
            self._invoice_with_rate(7.5)))
        percent = root.find(f"{cac}InvoiceLine/{cac}TaxTotal/"
                            f"{cac}TaxSubtotal/{cbc}Percent")
        self.assertEqual(percent.text, "7.5")

    def test_turkish_vat_rates_unchanged(self):
        """1/10/20 görünümü değişmemeli — bu yüzden işe yaramaz kalmadı."""
        gen = UBLTriGenerator()
        for rate in (1, 10, 20):
            with self.subTest(rate=rate):
                root = ET.fromstring(gen.generate(
                    self._invoice_with_rate(float(rate), tax_amount=float(rate))))
                self.assertEqual(self._percent(root), str(rate))

    def test_helper_directly(self):
        gen = UBLTriGenerator()
        for value, expected in [(20.0, "20"), (10.0, "10"), (1.0, "1"),
                                (7.5, "7.5"), (18.5, "18.5"),
                                (19.999999999999996, "20")]:
            with self.subTest(rate=value):
                self.assertEqual(gen._format_rate(value), expected)


class KnownDefectEmptyExtensionTest(unittest.TestCase):
    """# KNOWN DEFECT — P2-6: ext:UBLExtensions içeriği placeholder.

    _add_ubl_extensions, ExtensionContent içine literal <auto-generated-wildcard>
    yazıyor. Yani Türkiye-özgü tüm alanlar (muhtasar satır, e-Arşiv teslim
    parametreleri, GİB alan kodları) boş.

    Düzeltme bilinçli olarak erteleniyor: GİB'in güncel şeması olmadan
    doldurulursa uydurma alan üretir. Önce doğru alan kümesi tanımlanmalı.
    """

    def test_extension_content_is_placeholder_only(self):
        ext = f"{{{NS_EXT}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))
        content = root.find(f"{ext}UBLExtensions/{ext}UBLExtension/"
                            f"{ext}ExtensionContent")
        children = list(content)
        self.assertEqual(len(children), 1)
        # Prefix yok, dolayısıyla root'taki varsayılan (Invoice-2) namespace'ine
        # düşüyor — ext: değil. Yani placeholder yanlış namespace'de duruyor.
        self.assertEqual(children[0].tag, f"{{{NS_ROOT}}}auto-generated-wildcard")
        self.assertIsNone(children[0].text)

    def test_placeholder_appears_in_every_invoice(self):
        xml = UBLTriGenerator().generate(make_invoice())
        self.assertEqual(xml.count("auto-generated-wildcard"), 1)


class KnownDefectPricePrecisionTest(unittest.TestCase):
    """# KNOWN DEFECT — P2-7: birim fiyat 8 ondalık basamakla yazılıyor.

    TRY için 2 ondalık beklenir; .8f fazla basamak üretiyor. Miktar
    karşılaştırmalarında kayan nokta hatasına yol açabilir.

    Düzeltildiğinde: beklenen "100.00" olmalı.
    """

    def test_unit_price_rendered_with_eight_decimals(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice()))
        price = root.find(f"{cac}InvoiceLine/{cac}Price/{cbc}PriceAmount")
        self.assertEqual(price.text, "100.00000000")


if __name__ == "__main__":
    unittest.main(verbosity=2)