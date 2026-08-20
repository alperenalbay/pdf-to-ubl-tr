"""TTNET PDF → XML tam pipeline testi"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_extractor import PDFExtractor
from invoice_parser import InvoiceParser
from xml_generator import UBLTriGenerator

PDF_PATH = r"C:\Users\Devatek_06\Desktop\2025135663237 TTNET.pdf"
OUT_XML = r"C:\Users\Devatek_06\Desktop\test_output.xml"

# 1. PDF çıkar
ext = PDFExtractor()
data = ext.extract_all(PDF_PATH)
text = data["text"]
tables = data["tables"]
print(f"PDF extracted: {len(text)} chars, {len(tables)} tables")

# 2. Parse et
parser = InvoiceParser()
invoice = parser.parse(text, source_file=PDF_PATH, tables=tables)

print("\n=== PARSE SONUCU ===")
print(f"Supplier: {invoice.supplier_name}")
print(f"  VKN: {invoice.supplier_vkn}")
print(f"  Şehir: {invoice.supplier_city}")
print(f"  İlçe: {invoice.supplier_district}")
print(f"  Cadde: {invoice.supplier_street}")
print(f"  Posta Kodu: {invoice.supplier_postal_code}")
print(f"  Email: {invoice.supplier_email}")
print(f"  Vergi Dairesi: {invoice.supplier_tax_office}")
print(f"Customer: {invoice.customer_name}")
print(f"  VKN: {invoice.customer_vkn}")
print(f"  TCKN: {invoice.customer_tckn}")
print(f"  Şehir: {invoice.customer_city}")
print(f"  İlçe: {invoice.customer_district}")
print(f"  Cadde: {invoice.customer_street}")
print(f"InvoiceNo: {invoice.invoice_id}")
print(f"Date: {invoice.issue_date}")
print(f"Time: {invoice.issue_time}")
print(f"Type: {invoice.invoice_type}")
print(f"ETTN/UUID: {invoice.uuid}")
print(f"Total Gross: {invoice.total_gross}")
print(f"Total Net: {invoice.total_net}")
print(f"Total Tax: {invoice.total_tax}")
print(f"Tax Rate: {invoice.tax_rate}%")
print(f"Items: {len(invoice.line_items)}")
for item in invoice.line_items:
    print(f"  {item.line_id}. {item.name}: net={item.line_total_net}, tax={item.tax_amount}, gross={item.line_total_net + item.tax_amount}, rate={item.tax_rate}%")
print(f"Warnings: {invoice.parse_warnings}")

# 3. XML oluştur
gen = UBLTriGenerator()
xml_str = gen.generate(invoice)

with open(OUT_XML, "w", encoding="utf-8") as f:
    f.write(xml_str)
print(f"\nXML written to: {OUT_XML}")

# 4. XML'i oku ve başlangıç/bitiş tag'lerini kontrol et
import xml.etree.ElementTree as ET
root = ET.parse(OUT_XML).getroot()
print(f"\nXML Root tag: {root.tag}")
print(f"XML Root attribs: {list(root.attrib.keys())}")

# Temel kontroller
checks = []
# Namespace
ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
checks.append(("Namespace", "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" in root.tag))
# ID
id_elem = root.find(f"{ns}ID") or root.find("cbc:ID", {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"})
checks.append(("Invoice ID exists", id_elem is not None))
# UBLExtensions
ext_elem = root.find(f"{ns}UBLExtensions") or root.find("ext:UBLExtensions", {"ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"})
checks.append(("UBLExtensions exists", ext_elem is not None))
# TaxTotal
tax_elem = root.find(f"{ns}TaxTotal") or root.find("cac:TaxTotal", {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"})
checks.append(("TaxTotal exists", tax_elem is not None))
# LegalMonetaryTotal
legal_elem = root.find(f"{ns}LegalMonetaryTotal") or root.find("cac:LegalMonetaryTotal", {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"})
checks.append(("LegalMonetaryTotal exists", legal_elem is not None))
# InvoiceLine
lines_elem = root.findall(f"{ns}InvoiceLine") or root.findall("cac:InvoiceLine", {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"})
checks.append(("InvoiceLine count", f"{len(lines_elem)} items"))
# Supplier
supplier_elem = root.find(f"{ns}AccountingSupplierParty") or root.find("cac:AccountingSupplierParty", {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"})
checks.append(("SupplierParty exists", supplier_elem is not None))
# Customer
customer_elem = root.find(f"{ns}AccountingCustomerParty") or root.find("cac:AccountingCustomerParty", {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"})
checks.append(("CustomerParty exists", customer_elem is not None))

print("\n=== XML KONTROL ===")
for name, result in checks:
    status = "OK" if result else "FAIL"
    print(f"  [{status}] {name}: {result}")

print("\nXML preview (ilk 100 satır):")
for i, line in enumerate(xml_str.split("\n")[:100]):
    print(f"  {i+1:3d}: {line}")
