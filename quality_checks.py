




"""
quality_checks.py
Core image-quality functions used to judge whether a scanned/photographed
PDF page is blank, blurry, skewed, or likely unreadable by a human.

All processing is 100% local -- OpenCV + Tesseract, no internet required.
"""

import cv2
import numpy as np
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def pil_to_cv(pil_image):
    """Convert a PIL image (RGB) to an OpenCV image (BGR)."""
    arr = np.array(pil_image.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def to_gray(cv_image):
    return cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)


def crop_margins(gray, pct=0.04):
    """
    Crop a percentage off each edge before analysis. Scanner/phone-photo
    artifacts (binding shadows, dust, dark vignetting) concentrate near
    page edges and can fool blank/blur/contrast checks if left in.
    """
    h, w = gray.shape
    dy, dx = int(h * pct), int(w * pct)
    if h - 2 * dy <= 0 or w - 2 * dx <= 0:
        return gray  # page too small to crop, skip
    return gray[dy:h - dy, dx:w - dx]


def denoise_for_blank_check(gray):
    """
    Light median-blur denoise, used ONLY for the blank-page check so that
    small dust specks / scan noise don't cause an otherwise-blank page to
    be misclassified. NOT used for blur/contrast (that would mask real
    blur/fading, which is exactly what we're trying to measure there).
    """
    return cv2.medianBlur(gray, 5)


def solid_dark_check(gray, dark_thresh=60, dark_ratio_thresh=0.85):
    """
    Returns (is_solid_dark: bool, dark_ratio: float)
    Detects pages that are overwhelmingly black/very dark -- e.g. the
    scanner bed showing through, an unopened section, or a lens-cap-like
    capture. This is a different failure mode from "blurry" and should
    be reported separately.
    """
    dark_pixels = np.sum(gray <= dark_thresh)
    total_pixels = gray.size
    dark_ratio = dark_pixels / total_pixels
    return bool(dark_ratio >= dark_ratio_thresh), round(float(dark_ratio), 4)


def blank_page_check(gray, ink_thresh=200, ink_ratio_thresh=0.004):
    """
    Returns (is_blank: bool, ink_ratio: float)
    A page is considered blank if almost no pixels are dark enough to be
    actual ink/print -- regardless of whether the "background" is pure
    white or has a gray cast (common with uneven scan lighting or
    yellowed/aged paper). This is more robust than a strict whiteness
    threshold, which false-negatives on blank pages that aren't
    perfectly white.
    """
    ink_pixels = np.sum(gray < ink_thresh)
    total_pixels = gray.size
    ink_ratio = ink_pixels / total_pixels
    return bool(ink_ratio <= ink_ratio_thresh), round(float(ink_ratio), 4)


def blur_score(gray, target_width=1500):
    """
    Laplacian variance -- classic, fast blur metric. Higher = sharper.

    IMPORTANT: the image is resized to a fixed standard width first.
    Raw Laplacian variance is resolution-dependent -- the same physical
    sharpness produces a much lower score at high resolution than at low
    resolution, because anti-aliased edges get spread across more pixels
    (each individual pixel-to-pixel jump becomes smaller). Without this
    normalization, a fixed threshold silently breaks on any PDF rendered
    at a different DPI, or with different text density, than whatever
    was used to pick the threshold -- confirmed by testing: the exact
    same sharp content scored 3185 at 374px wide vs 17 at 2992px wide,
    with nothing about the actual sharpness changed.
    """
    h, w = gray.shape
    if w != target_width and w > 0:
        scale = target_width / w
        new_h = max(1, int(h * scale))
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        gray = cv2.resize(gray, (target_width, new_h), interpolation=interpolation)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return round(float(lap.var()), 2)


def contrast_score(gray):
    """
    Ink-vs-background contrast, using Otsu's method to separate ink
    (foreground) from paper (background), then measuring the brightness
    gap between them.

    This replaces a naive whole-page standard deviation, which gives
    misleadingly LOW scores on normal pages that are mostly white space
    with a small block of sharp text -- the text itself can be perfectly
    high-contrast even though the page as a whole has low pixel variance
    (since almost all of it is uniform white background).
    """
    thresh_val, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink_mask = gray < thresh_val
    bg_mask = ~ink_mask
    if ink_mask.sum() == 0 or bg_mask.sum() == 0:
        return 255.0  # no meaningful split found -- treat as high contrast (not a contrast problem)
    ink_mean = float(gray[ink_mask].mean())
    bg_mean = float(gray[bg_mask].mean())
    return round(bg_mean - ink_mean, 2)


def skew_angle(gray, angle_range=15, step=0.5):
    """
    Estimate rotation/skew angle in degrees using a projection-profile
    method: try rotating the page by a range of candidate angles, and
    pick the one where horizontal text rows line up most sharply
    (measured as the variance of the row-sum profile -- true horizontal
    alignment produces sharp peaks/troughs, misalignment blurs them out).

    This is far more robust than fitting a bounding box to scattered
    text blobs (the previous approach), which gives unreliable, often
    wildly wrong angles on pages with sparse text.
    """
    # Downsample for speed -- doesn't need full resolution to find skew
    scale = 600 / gray.shape[1] if gray.shape[1] > 600 else 1.0
    small = cv2.resize(gray, None, fx=scale, fy=scale) if scale != 1.0 else gray.copy()
    thresh = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    if np.sum(thresh > 0) < 50:  # not enough content to judge
        return 0.0

    best_angle, best_score = 0.0, -1.0
    h, w = thresh.shape
    center = (w // 2, h // 2)
    for angle in np.arange(-angle_range, angle_range + step, step):
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(thresh, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        row_sums = np.sum(rotated, axis=1)
        score = float(np.var(row_sums))
        if score > best_score:
            best_score = score
            best_angle = angle
    return round(-float(best_angle), 2)  # sign flip to match intuitive rotation direction


def ocr_confidence(cv_image, lang="eng+hin"):
    """
    Run Tesseract and return (avg_confidence: float, word_count: int).
    Confidence is 0-100 as reported by Tesseract per recognized word;
    -1 values (no confidence) are excluded from the average.

    `lang` controls which trained language model(s) Tesseract uses.
    Default is English+Hindi since Indian government/court documents
    routinely mix both scripts. Using only 'eng' on a Devanagari page
    makes Tesseract try to read Hindi text as English, producing
    consistently low, noisy confidence scores regardless of actual
    scan quality. Install the language pack on your system first:
        Windows: download hin.traineddata into the Tesseract tessdata folder
        Linux:   sudo apt install tesseract-ocr-hin
    Other languages: use the matching 3-letter Tesseract code (e.g.
    'eng+ben' for Bengali, 'eng+tam' for Tamil), after installing that
    language's traineddata the same way.
    """
    data = pytesseract.image_to_data(cv_image, lang=lang, output_type=pytesseract.Output.DICT)
    confidences = [int(c) for c in data["conf"] if c not in ("-1", -1)]
    words = [w for w in data["text"] if w.strip() != ""]
    if not confidences:
        return 0.0, 0
    return round(sum(confidences) / len(confidences), 2), len(words)


def classify_page_type(gray, word_count, ocr_conf):
    """
    Rough heuristic to classify page content:
    'blank', 'text', 'diagram_or_image', 'mixed'
    Based on text density vs total ink (non-white pixel) density.
    """
    ink_ratio = np.sum(gray < 200) / gray.size
    if ink_ratio < 0.01:
        return "blank"
    if word_count > 20 and ocr_conf > 40:
        # lots of confidently recognized words -> text heavy
        # check ink ratio too -- pure text pages have modest ink ratio
        if ink_ratio < 0.35:
            return "text"
        else:
            return "mixed"
    if word_count <= 20 and ink_ratio > 0.05:
        return "diagram_or_image"
    return "mixed"


def analyze_page(pil_image, blur_thresh=30.0, contrast_thresh=80.0,
                  skew_thresh=5.0, ocr_conf_thresh=40.0, ocr_lang="eng+hin"):
    """
    Run the full quality pipeline on a single page image.
    Returns a dict report for that page.
    """
    cv_img = pil_to_cv(pil_image)
    gray_full = to_gray(cv_img)

    # Crop scanner-edge noise (binding shadows, dust, vignetting) out
    # before running any of the checks below.
    gray = crop_margins(gray_full)

    # Blank check uses a lightly denoised version so small dust specks
    # left after cropping don't cause a false "not blank" result.
    is_blank, ink_ratio_blank = blank_page_check(denoise_for_blank_check(gray))

    # Solid-dark-page check -- a different failure mode than blur
    # (e.g. scanner bed showing through, unopened section).
    is_solid_dark, dark_ratio = solid_dark_check(gray)

    b_score = blur_score(gray)
    c_score = contrast_score(gray)

    # OCR/blur/contrast/skew verdicts are meaningless on blank or
    # solid-dark pages -- skew detection in particular tends to latch
    # onto scan noise and return a spurious boundary angle when there's
    # no real text to anchor on.
    skip_content_checks = is_blank or is_solid_dark
    skew = 0.0 if skip_content_checks else skew_angle(gray)
    conf, word_count = (0.0, 0) if skip_content_checks else ocr_confidence(cv_img, lang=ocr_lang)
    if is_blank:
        page_type = "blank"
    elif is_solid_dark:
        page_type = "solid_dark"
    else:
        page_type = classify_page_type(gray, word_count, conf)

    is_blurry = bool((not skip_content_checks) and (b_score < blur_thresh))
    is_low_contrast = bool((not skip_content_checks) and (c_score < contrast_thresh))
    is_skewed = bool(abs(skew) > skew_thresh)
    is_low_ocr_conf = bool((not skip_content_checks) and (page_type in ("text", "mixed")) and (conf < ocr_conf_thresh))

    issues = []
    if is_blank:
        issues.append("blank")
    if is_solid_dark:
        issues.append("solid_dark_page")
    if is_blurry:
        issues.append("blurry")
    if is_low_contrast:
        issues.append("low_contrast")
    if is_skewed:
        issues.append("skewed")
    if is_low_ocr_conf:
        issues.append("low_ocr_confidence")

    # A page is judged "likely unreadable by a human" if it's blank,
    # solid dark (nothing visible), or blurry/low-contrast combined
    # with low OCR confidence -- either alone can be a false positive
    # (e.g. a sharp photograph with no text has low OCR confidence but
    # is perfectly readable as an image).
    likely_unreadable = bool(
        is_blank or is_solid_dark
        or (is_blurry and is_low_ocr_conf)
        or (is_low_contrast and is_low_ocr_conf)
    )

    return {
        "blank": is_blank,
        "ink_ratio": ink_ratio_blank,
        "solid_dark_page": is_solid_dark,
        "dark_ratio": dark_ratio,
        "blur_score": b_score,
        "is_blurry": is_blurry,
        "contrast_score": c_score,
        "is_low_contrast": is_low_contrast,
        "skew_angle": skew,
        "is_skewed": is_skewed,
        "ocr_confidence": conf,
        "is_low_ocr_conf": is_low_ocr_conf,
        "word_count": word_count,
        "page_type": page_type,
        "issues": issues,
        "likely_unreadable": likely_unreadable,
    }

