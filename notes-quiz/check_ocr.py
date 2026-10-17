"""Run `python check_ocr.py` to confirm the app can find Tesseract."""
from dotenv import load_dotenv

load_dotenv()
import app  # noqa: E402

cmd = app.find_tesseract()
print("Tesseract path:", cmd or "not found")
print("Working:", "YES" if app.ocr_available() else "NO")
if app.ocr_available():
    import pytesseract
    print("Version:", pytesseract.get_tesseract_version())
    print("Languages:", ", ".join(pytesseract.get_languages()))
