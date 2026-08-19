@echo off
chcp 65001 >nul 2>&1
echo ============================================
echo   PDF to UBL-TR Paketleyici
echo ============================================
echo.

echo [1/2] Temizleniyor...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/2] EXE olusturuluyor...
python -m PyInstaller --clean --noconfirm pdf_to_ubl.spec

echo.
if exist "dist\PDF_to_UBL_TR.exe" (
    echo BASARILI! EXE dosyasi:
    echo   dist\PDF_to_UBL_TR.exe
    echo.
    echo Bu dosyayi istediginiz bilgisayara kopyalayabilirsiniz.
    echo Python yuklu olmasi gerekmez.
) else (
    echo HATA: EXE olusturulamadi!
)

echo.
pause
