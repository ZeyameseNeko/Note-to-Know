# Notes to Quiz

Paste or upload lesson notes and get a quiz or a study reviewer.
Built with Flask and the Gemini API (free tier).

## Run it locally

1. Get a free API key from https://aistudio.google.com/apikey
2. In the project folder:

   Windows (PowerShell)
       python -m venv .venv
       .venv\Scripts\Activate.ps1
       pip install -r requirements.txt
       copy .env.example .env

   Mac / Linux
       python3 -m venv .venv && source .venv/bin/activate
       pip install -r requirements.txt
       cp .env.example .env

3. Open `.env` and paste your key after `GEMINI_API_KEY=`
4. `python app.py`, then open http://127.0.0.1:5000

## File scanner (OCR) for scanned PDFs and photos

DOCX, XLSX, and text-based PPTX files work without this. Install Tesseract,
a free text-recognition program, to read scanned PDFs, photos, and images embedded in PPTX files.

Windows
1. Download the Tesseract installer for Windows from https://github.com/UB-Mannheim/tesseract/wiki
   (or run `winget install UB-Mannheim.TesseractOCR`).
2. Install it in the default folder (`C:\Program Files\Tesseract-OCR`). The app finds it there.
3. `pip install -r requirements.txt` again (adds pytesseract, pymupdf, pillow).
4. Restart `python app.py`.

Mac:    `brew install tesseract`
Ubuntu: `sudo apt install tesseract-ocr`   (this is also the command for a cloud server)

Check that it works: `python check_ocr.py` should print "Working: YES".

If Tesseract is installed somewhere else, set `TESSERACT_CMD` in `.env` to the full path.
For other languages, install that language's data and set `OCR_LANG` (for example `eng+fil`).

Limits: files up to 10 MB, first 30 scanned PDF pages or embedded PPTX images, 20,000 characters of text.
Scanning is slower than reading normal text and works best on clear, straight, well-lit pages.

## Notes
- Never commit `.env`. It is already in `.gitignore`.
- Free-tier requests may be used by Google to improve its products, so do not paste private material.
- Uploaded files are read in memory and never saved.

## Roadmap
- [x] Quiz (multiple types) and reviewer modes, answers shown after finishing
- [x] Upload .docx, .pptx, .xlsx and PDF files, with OCR for scans and photos
- [ ] User accounts, saved lessons, quiz history and scores
- [ ] Deploy on Oracle Cloud (Always Free)
