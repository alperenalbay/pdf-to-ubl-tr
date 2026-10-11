#!/usr/bin/env bash
# UBL 2.1 resmî XSD şemalarını indirir.
#
#   ./fetch_ubl_xsd.sh
#   python -m unittest test_ubl_xsd -v
#
# Şemalar ~2,8 MB tuttuğu için repoya commit edilmez; .gitignore'da
# tutulur. Bulunamazsa test_ubl_xsd.py sessizce atlanır.
#
# Doğrulamayı çalıştırmak için lxml gerekir:
#   pip install lxml

set -euo pipefail

BASE="https://git.erst.dk/openebusiness/common/-/raw/5f1b47d6179b14a53cc2073c6f9b38184192831f/resources/Schemas/UBL_v2.1"
DEST="${1:-$(cd "$(dirname "$0")" && pwd)/ubl-xsd}"
COMMON="$DEST/common"

FILES=(
  maindoc/UBL-Invoice-2.1.xsd
  common/CCTS_CCT_SchemaModule-2.1.xsd
  common/UBL-CommonAggregateComponents-2.1.xsd
  common/UBL-CommonBasicComponents-2.1.xsd
  common/UBL-CommonExtensionComponents-2.1.xsd
  common/UBL-CommonSignatureComponents-2.1.xsd
  common/UBL-CoreComponentParameters-2.1.xsd
  common/UBL-ExtensionContentDataType-2.1.xsd
  common/UBL-QualifiedDataTypes-2.1.xsd
  common/UBL-SignatureAggregateComponents-2.1.xsd
  common/UBL-SignatureBasicComponents-2.1.xsd
  common/UBL-UnqualifiedDataTypes-2.1.xsd
  common/UBL-XAdESv132-2.1.xsd
  common/UBL-XAdESv141-2.1.xsd
  common/UBL-xmldsig-core-schema-2.1.xsd
)

mkdir -p "$COMMON"

echo "UBL 2.1 şemaları indiriliyor -> $DEST"
for f in "${FILES[@]}"; do
  out="$DEST/${f#maindoc/}"
  # maindoc/UBL-Invoice-2.1.xsd, ../common/ yolundan ortak şemaları
  # çektiği için common/ altına da bir kopyası gerekiyor.
  if [[ "$f" == maindoc/* ]]; then
    out="$COMMON/$(basename "$f")"
  fi
  curl -fsSL -o "$out" "$BASE/$f"
  printf '  %-46s %s bayt\n' "$(basename "$f")" "$(wc -c < "$out")"
done

echo
echo "Tamam. Şimdi:  python -m unittest test_ubl_xsd -v"