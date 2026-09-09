# PDF Quality Checker (100% Local)

Analyzes scanned/photographed PDFs and flags pages that are blank, blurry,
low contrast, skewed, or likely unreadable to a human. No internet
connection is used at any point after setup.

## Setup on Windows

### 1. Install Python
If you don't already have it: download from python.org (3.10+), and
during install check "Add Python to PATH".

### 2. Install Tesseract OCR (system binary, not just the Python package)
Download the Windows installer from the official Tesseract project:
https://github.com/UB-Mannheim/tesseract/wiki

Install it (default path is usually `C:\Program Files\Tesseract-OCR\`).

**Important for Indian government/court documents:** during installation,
in the component selection screen, check **"Hindi"** under additional
language data (or any other language your documents use — Bengali,
Tamil, etc. are also listed there). By default only English is
installed, which makes Tesseract try to read Devanagari script as
English -- producing consistently low, unreliable confidence scores
even on perfectly legible Hindi text. If you already installed
Tesseract without it, re-run the installer and add the language pack,
or download `hin.traineddata` directly into your `tessdata` folder
(usually `C:\Program Files\Tesseract-OCR\tessdata\`) from:
https://github.com/tesseract-ocr/tessdata

After installing, tell pytesseract where to find it. Open
`quality_checks.py` and add near the top (adjust path if yours differs):

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

### 3. Set up the Python project
Open PowerShell in this folder and run:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Install the language packs your documents need
By default this tool OCRs with English+Hindi. For documents from other
states, you need to install the matching Tesseract language pack(s)
first, same way as Hindi in step 2:
- Windows: download the `.traineddata` file(s) from
  https://github.com/tesseract-ocr/tessdata and drop them into
  `C:\Program Files\Tesseract-OCR\tessdata\`
- Or re-run the Tesseract installer and check the languages you need
  in the components screen

**Reference: India's court/government languages and their Tesseract codes**

| Language | Code | Typically used in |
|---|---|---|
| Hindi | `hin` | UP, Bihar, MP, Rajasthan, Delhi, Haryana, Uttarakhand, Jharkhand, Chhattisgarh |
| Marathi | `mar` | Maharashtra |
| Gujarati | `guj` | Gujarat |
| Tamil | `tam` | Tamil Nadu |
| Telugu | `tel` | Andhra Pradesh, Telangana |
| Kannada | `kan` | Karnataka |
| Malayalam | `mal` | Kerala |
| Bengali | `ben` | West Bengal, Tripura |
| Odia | `ori` | Odisha |
| Assamese | `asm` | Assam |
| Punjabi | `pan` | Punjab |
| Urdu | `urd` | J&K, and used alongside Hindi in several states |
| Nepali | `nep` | Sikkim, parts of West Bengal |
| Sanskrit | `san` | Uttarakhand (rare, mostly religious/traditional documents) |
| Sindhi | `snd` | Rare, some Gujarat/Rajasthan/Maharashtra communities |
| English | `eng` | Used everywhere, especially higher courts -- always included by default |

**Not reliably supported by Tesseract:** Santali (Ol Chiki script) and
Manipuri/Meitei (Meitei Mayek script) have no usable Tesseract model --
documents in these scripts won't OCR well with this tool. Bodo, Dogri,
Konkani, and Maithili have no dedicated model either, but are commonly
written in Devanagari script in official paperwork, so Hindi (`hin`)
is the closest practical fallback for them.

### 5. Run it on a PDF

Pick a preset matching where the document is from:

```powershell
python analyze_pdf.py "C:\path\to\document.pdf" --lang hindi_belt
python analyze_pdf.py "C:\path\to\document.pdf" --lang south
python analyze_pdf.py "C:\path\to\document.pdf" --lang west
python analyze_pdf.py "C:\path\to\document.pdf" --lang east
python analyze_pdf.py "C:\path\to\document.pdf" --lang north
```

Or don't know the state, or want maximum coverage regardless of speed:

```powershell
python analyze_pdf.py "C:\path\to\document.pdf" --lang all_india
```

**Be aware: `all_india` runs roughly 5x slower per page** (tested:
~9s/page with just eng+hin vs ~45s/page with all 16 languages loaded
together) -- for a 280-page document that's the difference between
about 40 minutes and 3.5 hours. Only worth it when you genuinely don't
know the document's origin, or need to double-check a result.

Or specify exact languages yourself, no preset:

```powershell
python analyze_pdf.py "C:\path\to\document.pdf" --lang eng+hin+tam
```

Each language needs its `.traineddata` file installed first (see step 4).

You'll see live per-page progress, then a summary, then a JSON
and CSV report saved into a `reports\` folder.

## What it checks per page

- **Blank** — near-entirely white page (nothing printed)
- **Blurry** — Laplacian edge-sharpness below threshold
- **Low contrast** — faded/washed-out text (common with bad phone lighting)
- **Skewed** — page photographed at an angle
- **Low OCR confidence** — Tesseract itself struggles to recognize the text
- **likely_unreadable** — combined judgment (blank, OR blurry+low-OCR-confidence
  together, OR low-contrast+low-OCR-confidence together)

## Tuning thresholds

The default thresholds in `quality_checks.py` (`analyze_page` function
arguments) were picked as reasonable starting points, not calibrated on
your actual documents. To tune them:

1. Run the tool on a batch of your real PDFs.
2. Open the CSV report and manually look at a handful of pages you know
   are actually blurry vs actually fine.
3. Compare their `blur_score` values and pick a threshold that separates
   them well. Same idea for `contrast_score` and `ocr_confidence`.
4. Pass your tuned values into `analyze_page(...)` inside `analyze_pdf.py`,
   e.g. `analyze_page(pil_img, blur_thresh=150.0)`.

## Known limitation

The blur metric (Laplacian variance) measures edge sharpness. Faint/low-
contrast text naturally has weak edges too, even when perfectly in focus
-- so it can get flagged as "blurry" even though the real problem is
contrast, not focus. This is why `likely_unreadable` requires blur/contrast
issues to combine with low OCR confidence before calling a page truly
unreadable, rather than trusting the blur score alone.

## Web UI (prototype)

A local browser-based UI is available in the `webapp/` folder -- upload
a PDF, pick a language region, watch progress, view/download results,
all without touching the command line. It's a first prototype (see
"Known limitations of the web UI prototype" below) but fully working
and tested end-to-end.

### Setup
From inside `webapp/`, with the same virtual environment active:
```powershell
cd webapp
pip install -r ..\requirements.txt
```
(Flask is already included in the updated `requirements.txt`.)

### Run it
```powershell
python app.py
```
Then open **http://127.0.0.1:5000** in your browser. Everything runs
on your machine -- Flask is just serving a page locally, no internet
connection is used or required.

### How it works
1. Upload a PDF and pick a language/region preset (same presets as the
   CLI tool)
2. You're taken to a progress page that polls for status every second
   -- large PDFs with OCR can take a while, so this runs as a
   background job rather than making you stare at a frozen page
3. Once done, you see a summary (page counts per issue type) and a
   table of every flagged page, plus buttons to download the same
   JSON/CSV reports the CLI tool produces

### Known limitations of the web UI prototype
- **Single user, one job at a time in practice.** Job state is stored
  in memory; restarting the app clears any in-progress or completed
  jobs. Fine for local personal use, not meant for multiple people
  hitting it at once.
- **Page thumbnails accumulate on disk** in `webapp/thumbnails/` per job,
  same as uploads/reports -- nothing gets auto-cleaned yet.
- **No authentication** -- anyone with access to your machine on port
  5000 could use it. Not a concern for local-only use (it only binds
  to 127.0.0.1, not your network), but don't run this on a shared/
  public server as-is.
- **Uploaded PDFs and reports stay on disk** in `webapp/uploads/` and
  `webapp/reports/` until you delete them manually -- nothing gets
  auto-cleaned yet.

This is a prototype meant to be iterated on -- tell me what's
missing or annoying and we'll improve it (thumbnails, drag-and-drop,
batch processing multiple PDFs, dark mode, whatever's actually useful
for your workflow).

## Packaging into a standalone .exe (no browser, no separate installs)

This turns the web app into something that behaves like normal desktop
software: double-click, a window opens directly (no browser tab, no
address bar), works without anyone installing Python, Tesseract, or
any pip packages separately.

**What's been tested and confirmed working** (validated in a Linux
sandbox using GTK/WebKit as a stand-in for Windows' WebView2 -- the
same underlying Python code path, different native renderer):
- Flask running in a background thread while pywebview's native window
  loads it live -- no deadlock, no blocking between the GUI event loop
  and the web server
- A full PyInstaller build correctly bundling Flask, OpenCV, PyMuPDF,
  pytesseract, and pywebview together
- The **packaged binary itself** (not just the raw script) correctly
  finding and serving its bundled `templates/` and `static/` folders --
  this is the most common way PyInstaller + Flask breaks, and it works

**What can only be confirmed on your actual Windows machine** (I can't
test these from here):
- The real Windows build (this sandbox can only produce a Linux binary
  to validate the bundling logic)
- Bundling your actual `tesseract.exe` + its DLLs + language data
- WebView2 rendering specifically (should be a drop-in equivalent to
  what was tested, since pywebview abstracts this, but hasn't been
  directly observed)

### Steps to build it yourself

**1. Install the two new dependencies**
```powershell
pip install pywebview pyinstaller
```

**2. Bundle your Tesseract install into the project**

Copy your entire `C:\Program Files\Tesseract-OCR\` folder into
`webapp\tesseract_bundled\` (so you end up with
`webapp\tesseract_bundled\tesseract.exe`,
`webapp\tesseract_bundled\tessdata\*.traineddata`, and all the
supporting DLLs alongside them). `quality_checks.py` already knows to
look for this folder automatically -- no path editing needed.

**3. Uncomment one line in `desktop_app.spec`**

Open it and uncomment:
```python
# ('tesseract_bundled', 'tesseract_bundled'),
```
so PyInstaller actually includes the folder you just copied in.

**4. Build**
```powershell
cd webapp
pyinstaller desktop_app.spec
```

This builds in "onedir" mode (a folder containing the exe + its
dependencies as visible files) rather than a single self-extracting
exe -- onedir tends to trigger far fewer antivirus false positives,
since self-extracting exes match a pattern malware droppers also use.
The tradeoff is you're sharing a folder instead of one file; zip it up
before sending it to someone.

**5. Test it**

Your built app is at `dist\PDFQualityChecker\PDFQualityChecker.exe`.
Double-click it -- a window should open directly, no browser, no
console. Try uploading a real PDF end-to-end, including the OCR step,
to confirm the bundled Tesseract copy actually works.

### Things to expect

- **Windows SmartScreen warning** on first run, since this is an
  unsigned exe from an unrecognized publisher -- expected, not a sign
  anything's broken. Whoever you send it to just clicks "More info" →
  "Run anyway".
- **Total size** will land somewhere in the few-hundred-MB range once
  Tesseract + language packs are included -- fine for sharing via
  Drive/USB, not a tiny download.
- If antivirus flags it, that's a known PyInstaller quirk (see above on
  onedir vs onefile) rather than an indication of a real problem.

## Next steps you could add later

- A simple web UI (Flask/FastAPI) to upload a PDF and view the report
  in-browser instead of the command line
- Visual page thumbnails with flagged issues overlaid
- Batch mode for processing a whole folder of PDFs at once
- A small local LLM (via Ollama) to turn the JSON report into a plain-
  English written summary for non-technical readers