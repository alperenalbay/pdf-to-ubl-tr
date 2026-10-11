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


class KnownDefectFabricatedDateTest(unittest.TestCase):
    """# KNOWN DEFECT — P0-2: tarih yoksa uydurma tarih yazılıyor.

    _add_additional_refs, issue_date boşken `or "2026-01-01"` fallback'i
    kullanıyor. Yasal bir belgeye uydurma tarih yazmak kabul edilemez.

    Düzeltme: tarih yoksa alan atlanmalı ya da üretim hata vermeli —
    sessizce 2026-01-01 yazılmamalı.
    """

    def test_missing_issue_date_yields_fabricated_date(self):
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(issue_date=None)))
        ref = root.find(cac + "AdditionalDocumentReference")
        self.assertEqual(ref.find(cbc + "IssueDate").text, "2026-01-01")

    def test_header_issue_date_is_omitted_not_fabricated(self):
        """Başlık alanı koşullu — yani tutarsızlık burada görünür:
        belgenin bir yerinde tarih yok, diğerinde uydurma var."""
        cbc = f"{{{NS_CBC}}}"
        root = ET.fromstring(UBLTriGenerator().generate(make_invoice(issue_date=None)))
        self.assertIsNone(root.find(cbc + "IssueDate"))


class KnownDefectSignatorySchemeTest(unittest.TestCase):
    """# KNOWN DEFECT — P1-3: SignatoryParty şema kimliği VKN'ye sabitlenmiş.

    _add_signature, sig_id TCKN olsa bile schemeID="VKN" yazıyor.
    _add_supplier_party ise doğru davranıyor (uzunluğa bakıyor), yani iki
    bölge aynı kuralı farklı uyguluyor.

    Düzeltme: _add_signature da "VKN" if len(id)==10 else "TCKN" kullanmalı.
    """

    def test_tckn_signatory_is_labelled_vkn(self):
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        inv = make_invoice(supplier_vkn=None, supplier_tckn="12345678901")
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        signatory = root.find(f"{cac}Signature/{cac}SignatoryParty/"
                              f"{cac}PartyIdentification/{cbc}ID")
        self.assertEqual(signatory.text, "12345678901")
        self.assertEqual(signatory.get("schemeID"), "VKN")  # TCKN olmalıydı

    def test_supplier_party_resolves_scheme_correctly(self):
        """Doğru davranışın nasıl olması gerektiğini sabitler."""
        cbc, cac = f"{{{NS_CBC}}}", f"{{{NS_CAC}}}"
        inv = make_invoice(supplier_vkn=None, supplier_tckn="12345678901")
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        pid = root.find(f"{cac}AccountingSupplierParty/{cac}Party/"
                        f"{cac}PartyIdentification/{cbc}ID")
        self.assertEqual(pid.get("schemeID"), "TCKN")


class KnownDefectTaxRateTruncationTest(unittest.TestCase):
    """# KNOWN DEFECT — P1-4: KDV yüzdesi int() ile kesiliyor.

    str(int(tax_rate)) kullanıldığı için %7.5 → "7". TaxAmount doğru
    kalırken Percent yanlış çıkıyor, yani tutar ile oran tutarsızlaşıyor.

    Türk KDV'si 1/10/20 tam sayı olduğu için pratikte tetiklenmesi zor;
    gerçek risk float yuvarlama (örn. 19.9999999 → "19"). Düzeltme:
    ondalık basamağı koruyan biçimlendirme (örn. %g / round).

    Düzeltildiğinde: güncel davranış "7" yerine "7.5" beklenmeli.
    """

    def test_fractional_rate_truncated_to_integer(self):
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        inv = make_invoice(
            total_net=100.0, total_tax=7.5, total_gross=107.5, tax_rate=7.5,
            line_items=[make_item(line_total_net=100.0, unit_price_net=100.0,
                                  tax_rate=7.5, tax_amount=7.5)],
        )
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        percent = root.find(f"{cac}TaxTotal/{cac}TaxSubtotal/{cbc}Percent")
        amount = root.find(f"{cac}TaxTotal/{cac}TaxSubtotal/{cbc}TaxAmount")
        self.assertEqual(percent.text, "7")
        self.assertEqual(amount.text, "7.50")

    def test_float_rounding_boundary_is_at_risk(self):
        """19.9999999 matematiksel olarak %20 ama int() ile 19 olur."""
        cac, cbc = f"{{{NS_CAC}}}", f"{{{NS_CBC}}}"
        rate = 100 * 30 / 30  # tam sayıya yakın ama float artığı taşıyabilir
        inv = make_invoice(
            tax_rate=rate,
            line_items=[make_item(tax_rate=rate)],
        )
        root = ET.fromstring(UBLTriGenerator().generate(inv))
        percent = root.find(f"{cac}TaxTotal/{cac}TaxSubtotal/{cbc}Percent")
        self.assertEqual(percent.text, str(int(rate)))


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