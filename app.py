"""
app.py -- Local web UI for the PDF quality checker.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser.

100% local -- Flask just serves a page on your own machine; nothing
leaves your computer, no internet connection is used at any point.

Long PDFs (100+ pages) can take many minutes to process because of the
OCR step, so analysis runs in a background thread and the browser polls
for progress rather than waiting on a single request.
"""

import os
import csv
import json
import uuid
import threading
from datetime import datetime

import fitz  # PyMuPDF
from PIL import Image
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for

from quality_checks import analyze_page

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB upload limit

# Same presets as the CLI tool -- see analyze_pdf.py for the full
# reasoning/reference table on which languages to pick.
LANG_PRESETS = {
    "hindi_belt": "eng+hin",
    "west": "eng+hin+mar+guj",
    "south": "eng+tam+tel+kan+mal",
    "east": "eng+hin+ben+ori+asm",
    "north": "eng+hin+pan+urd",
    "all_india": "eng+hin+ben+guj+kan+mal+mar+nep+ori+pan+san+snd+tam+tel+urd+asm",
}

# In-memory job store. Fine for a single-user local prototype; a
# restart of the app clears any in-progress or completed jobs.
JOBS = {}
JOBS_LOCK = threading.Lock()


def pdf_to_page_images(pdf_path, dpi=300):
    doc = fitz.open(pdf_path)
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        yield i, img
    doc.close()


def run_analysis(job_id, pdf_path, ocr_lang, original_filename):
    """Runs in a background thread; updates JOBS[job_id] as it progresses."""
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        doc.close()

        with JOBS_LOCK:
            JOBS[job_id]["total"] = total_pages
            JOBS[job_id]["status"] = "running"

        results = []
        for page_num, pil_img in pdf_to_page_images(pdf_path):
            report = analyze_page(pil_img, ocr_lang=ocr_lang)
            report["page"] = page_num
            results.append(report)
            with JOBS_LOCK:
                JOBS[job_id]["current"] = page_num

        total = len(results)
        summary = {
            "total_pages": total,
            "clean_pages": sum(1 for r in results if not r["issues"]),
            "blank_pages": sum(1 for r in results if r["blank"]),
            "solid_dark_pages": sum(1 for r in results if r["solid_dark_page"]),
            "blurry_pages": sum(1 for r in results if r["is_blurry"]),
            "low_contrast_pages": sum(1 for r in results if r["is_low_contrast"]),
            "skewed_pages": sum(1 for r in results if r["is_skewed"]),
            "low_ocr_confidence_pages": sum(1 for r in results if r.get("is_low_ocr_conf", False)),
            "likely_unreadable_pages": sum(1 for r in results if r["likely_unreadable"]),
        }

        # Save JSON + CSV reports to disk, same as the CLI tool
        base = os.path.splitext(original_filename)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(REPORTS_DIR, f"{base}_{job_id}_{timestamp}.json")
        csv_path = os.path.join(REPORTS_DIR, f"{base}_{job_id}_{timestamp}.csv")

        with open(json_path, "w") as f:
            json.dump({"summary": summary, "pages": results}, f, indent=2)

        fieldnames = ["page", "blank", "ink_ratio", "solid_dark_page", "dark_ratio",
                      "blur_score", "is_blurry", "contrast_score", "is_low_contrast",
                      "skew_angle", "is_skewed", "ocr_confidence", "word_count",
                      "page_type", "likely_unreadable", "issues"]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                row = {k: r.get(k) for k in fieldnames}
                row["issues"] = ";".join(r["issues"])
                writer.writerow(row)

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["summary"] = summary
            JOBS[job_id]["pages"] = results
            JOBS[job_id]["json_path"] = json_path
            JOBS[job_id]["csv_path"] = csv_path

    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(e)


@app.route("/")
def index():
    return render_template("index.html", presets=LANG_PRESETS)


@app.route("/analyze", methods=["POST"])
def analyze():
    if "pdf_file" not in request.files:
        return "No file uploaded", 400
    file = request.files["pdf_file"]
    if file.filename == "":
        return "No file selected", 400

    lang_choice = request.form.get("lang", "hindi_belt")
    ocr_lang = LANG_PRESETS.get(lang_choice, lang_choice)  # preset name OR raw codes

    job_id = uuid.uuid4().hex[:12]
    safe_name = f"{job_id}_{file.filename}"
    pdf_path = os.path.join(UPLOAD_DIR, safe_name)
    file.save(pdf_path)

    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "starting",
            "current": 0,
            "total": 0,
            "filename": file.filename,
            "lang": ocr_lang,
        }

    thread = threading.Thread(target=run_analysis, args=(job_id, pdf_path, ocr_lang, file.filename))
    thread.daemon = True
    thread.start()

    return redirect(url_for("progress", job_id=job_id))


@app.route("/progress/<job_id>")
def progress(job_id):
    if job_id not in JOBS:
        return "Job not found", 404
    return render_template("progress.html", job_id=job_id, filename=JOBS[job_id]["filename"])


@app.route("/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        return jsonify({"status": "not_found"}), 404
    return jsonify({
        "status": job["status"],
        "current": job.get("current", 0),
        "total": job.get("total", 0),
        "error": job.get("error"),
    })


@app.route("/results/<job_id>")
def results(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        return "Job not found", 404
    if job["status"] != "done":
        return redirect(url_for("progress", job_id=job_id))
    return render_template("results.html", job_id=job_id, filename=job["filename"],
                            summary=job["summary"], pages=job["pages"], lang=job["lang"])


@app.route("/download/<job_id>/<fmt>")
def download(job_id, fmt):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None or job["status"] != "done":
        return "Report not available", 404
    path = job.get(f"{fmt}_path")
    if not path or not os.path.exists(path):
        return "File not found", 404
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    print("Starting PDF Quality Checker web UI...")
    print("Open this in your browser: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
