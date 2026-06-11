"""
Newspaper clipping collector (P16 — Cutting Room).

CareersWave.in mechanism (verified 2026-04-23):
    Each newspaper page lists DATE → Google Drive download links.
    Link format: https://drive.google.com/file/d/<FILE_ID>/view?usp=drive_link
    Dates appear in multiple formats across papers:
      - "23 April 2026"          (Times of India, The Hindu)
      - "23-04-2026"             (Sakshi — DD-MM-YYYY)
      - "2026-04-23"             (rare)
      - "April 23, 2026"         (some)

Flow:
    1. Scrape the paper's CareersWave page for today's Google Drive URL.
    2. Resolve that Google Drive URL to a direct PDF download (handles
       the large-file "can't scan for viruses" confirmation page).
    3. Use OpenDataLoader PDF → PyMuPDF fallback to extract articles
       with bounding boxes.
    4. Render each article region as a cropped PNG via PyMuPDF.
    5. Score relevance; caller stores relevant clippings.
"""

import asyncio
import base64
import json
import logging
import os
import re
import tempfile
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# CareersWave page scraping — find today's Google Drive link
# ────────────────────────────────────────────────────────────────────────

_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
    6: "June", 7: "July", 8: "August", 9: "September",
    10: "October", 11: "November", 12: "December",
}

_GDRIVE_FILE_ID_RE = re.compile(r"drive\.google\.com/file/d/([A-Za-z0-9_-]{20,})")


def _date_variants(d: date) -> list[str]:
    """Return every string form of a date we've seen on CareersWave."""
    mname = _MONTHS[d.month]
    return [
        # Day-first (most common on the site)
        f"{d.day:02d} {mname} {d.year}",      # 23 April 2026
        f"{d.day} {mname} {d.year}",          # 23 April 2026 (no zero-pad)
        f"{d.day:02d}-{d.month:02d}-{d.year}", # 23-04-2026 (Sakshi)
        f"{d.day}-{d.month:02d}-{d.year}",     # 23-4-2026
        f"{d.day:02d}/{d.month:02d}/{d.year}", # 23/04/2026
        # Month-first
        f"{mname} {d.day:02d}, {d.year}",     # April 23, 2026
        f"{mname} {d.day}, {d.year}",         # April 23, 2026
        f"{mname} {d.day} {d.year}",          # April 23 2026
        # ISO
        d.isoformat(),                         # 2026-04-23
    ]


def _find_gdrive_id_near_date(html: str, d: date) -> str | None:
    """
    Find the first Google Drive file ID that appears AFTER today's date
    string in the raw HTML.

    The pages are structured as:
        23 April 2026: <a href="https://drive.google.com/file/d/FILE_ID/view">
    So scanning forward from each date occurrence finds the matching link.
    """
    variants = _date_variants(d)
    # Try each date variant, return the first drive link within 2000 chars.
    for variant in variants:
        idx = 0
        while True:
            pos = html.find(variant, idx)
            if pos == -1:
                break
            window = html[pos : pos + 2500]
            m = _GDRIVE_FILE_ID_RE.search(window)
            if m:
                return m.group(1)
            idx = pos + len(variant)
    return None


async def get_pdf_url_from_careerswave(careerswave_url: str) -> str | None:
    """
    Scrape a CareersWave newspaper page and return the most recent
    downloadable PDF URL (as a Google Drive direct-download URL).

    Tries today, yesterday, day-before-yesterday to tolerate a delayed
    morning upload. Returns a URL that `download_pdf_from_url` can fetch.
    """
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        ) as client:
            r = await client.get(careerswave_url)
            if r.status_code != 200:
                logger.warning(
                    "CareersWave page %s returned HTTP %s",
                    careerswave_url,
                    r.status_code,
                )
                return None
            html = r.text

    except Exception as exc:
        logger.warning("CareersWave scrape failed for %s: %s", careerswave_url, exc)
        return None

    today = date.today()
    for offset in (0, 1, 2):
        target = today - timedelta(days=offset)
        file_id = _find_gdrive_id_near_date(html, target)
        if file_id:
            logger.info(
                "CareersWave %s → drive file %s (date offset %d)",
                careerswave_url,
                file_id,
                offset,
            )
            return _gdrive_direct_url(file_id)

    # Last resort: grab the most recent drive link on the page at all.
    m = _GDRIVE_FILE_ID_RE.search(html)
    if m:
        logger.info(
            "CareersWave %s → undated drive file %s",
            careerswave_url,
            m.group(1),
        )
        return _gdrive_direct_url(m.group(1))

    # Raw HTML has no Drive links — site may be using JS-rendered tables.
    # Fall back to Playwright to execute the page JS before scraping.
    logger.info(
        "CareersWave %s: no Drive link in raw HTML, trying Playwright",
        careerswave_url,
    )
    pw_html = await _careerswave_playwright_fetch(careerswave_url)
    if pw_html:
        for offset in (0, 1, 2):
            target = today - timedelta(days=offset)
            file_id = _find_gdrive_id_near_date(pw_html, target)
            if file_id:
                logger.info(
                    "CareersWave Playwright %s → drive file %s (date offset %d)",
                    careerswave_url, file_id, offset,
                )
                return _gdrive_direct_url(file_id)
        m = _GDRIVE_FILE_ID_RE.search(pw_html)
        if m:
            logger.info(
                "CareersWave Playwright %s → undated drive file %s",
                careerswave_url, m.group(1),
            )
            return _gdrive_direct_url(m.group(1))

    drive_link_present = "drive.google.com/file/d/" in html
    logger.warning(
        "CareersWave %s: no Drive link matched dates %s "
        "(any_drive_link_on_page=%s, html_bytes=%d)",
        careerswave_url,
        ", ".join(d.isoformat() for d in (
            today, today - timedelta(days=1), today - timedelta(days=2),
        )),
        drive_link_present,
        len(html),
    )
    return None


async def _careerswave_playwright_fetch(url: str) -> str | None:
    """Render a CareersWave page with Playwright and return the full HTML.

    The dated download table (with the Google Drive links) is JS-rendered and
    lazy-loaded as the page scrolls, so a plain httpx GET sees zero Drive links.
    We load the page, scroll to the bottom in steps to trigger the lazy-load,
    settle briefly, then return the fully rendered HTML for date matching.
    """
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # Scroll the page in steps to trigger lazy-loading of the dated
            # download table that holds the Google Drive links.
            for _ in range(10):
                await page.evaluate(
                    "window.scrollBy(0, document.body.scrollHeight/10)"
                )
                await page.wait_for_timeout(600)
            await page.wait_for_timeout(2500)
            html = await page.content()
            await browser.close()
            return html
    except Exception as exc:
        logger.warning("CareersWave Playwright fetch failed for %s: %s", url, exc)
        return None


# ────────────────────────────────────────────────────────────────────────
# Google Drive direct-download helper
# ────────────────────────────────────────────────────────────────────────


def _gdrive_direct_url(file_id: str) -> str:
    """Google Drive's unauthenticated direct-download endpoint."""
    return f"https://drive.google.com/uc?export=download&id={file_id}"


async def _stream_to_file(client: httpx.AsyncClient, url: str, dest_path: str,
                          params: dict | None = None) -> tuple[bool, int]:
    """
    Stream a URL to disk. Returns (success, bytes_written).

    'Success' here means we wrote at least 10 KB starting with the PDF
    magic bytes `%PDF`. A peer-side disconnect is OK as long as we got
    a usable prefix (odl + PyMuPDF handle truncated PDFs gracefully).
    """
    bytes_written = 0
    is_pdf = False
    try:
        async with client.stream("GET", url, params=params) as r:
            if r.status_code != 200:
                return False, 0
            with open(dest_path, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=1 << 16):
                    if not is_pdf and bytes_written == 0 and chunk[:4] == b"%PDF":
                        is_pdf = True
                    f.write(chunk)
                    bytes_written += len(chunk)
    except (httpx.RemoteProtocolError, httpx.ReadError) as exc:
        # Peer-close mid-stream: keep whatever we have if it's PDF-shaped
        logger.info(
            "stream for %s ended early (%s) — kept %d bytes",
            url, exc, bytes_written,
        )
    except Exception as exc:
        logger.warning("stream failed for %s: %s", url, exc)
        return False, bytes_written

    # Verify on-disk magic bytes (chunk[:4] check above only works for 1st chunk)
    if not is_pdf and os.path.exists(dest_path):
        with open(dest_path, "rb") as f:
            is_pdf = f.read(4) == b"%PDF"

    return (is_pdf and bytes_written > 10_000), bytes_written


async def download_pdf_from_url(url: str, dest_path: str) -> bool:
    """
    Download a PDF to dest_path, handling:
      - Plain HTTP(S) PDFs
      - Google Drive `uc?export=download` URLs including the virus-scan
        confirmation page for files > 25 MB
      - Peer-side connection drops (streams to disk; accepts partial
        bodies as long as the PDF header is intact)

    Retries the direct URL once after a short back-off before giving up.
    """
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(180.0, read=180.0),
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as client:
                # First pass: try the URL directly — may succeed (small files)
                # or return the Drive HTML confirmation page.
                r = await client.get(url)
                ctype = r.headers.get("content-type", "").lower()

                if r.status_code == 200 and (
                    "application/pdf" in ctype
                    or "application/octet-stream" in ctype
                    or r.content[:4] == b"%PDF"
                ):
                    with open(dest_path, "wb") as f:
                        f.write(r.content)
                    return True

                # Google Drive confirmation page
                if "text/html" in ctype and "drive.google.com" in url:
                    html = r.text
                    form_match = re.search(
                        r'action="(https://drive\.usercontent\.google\.com/download[^"]*)"',
                        html,
                    )
                    params: dict[str, str] = {}
                    for field in re.finditer(
                        r'name="([^"]+)"\s+value="([^"]*)"', html
                    ):
                        params[field.group(1)] = field.group(2)

                    if form_match:
                        action_url = form_match.group(1).replace("&amp;", "&")
                        ok, nbytes = await _stream_to_file(
                            client, action_url, dest_path, params=params
                        )
                        if ok:
                            return True
                        logger.info(
                            "Drive confirm form attempt %d failed (%d bytes)",
                            attempt, nbytes,
                        )

                    # Older confirm-token fallback
                    confirm = re.search(r'confirm=([0-9A-Za-z_-]+)', html)
                    if confirm:
                        file_id_match = re.search(r'[?&]id=([A-Za-z0-9_-]+)', url)
                        if file_id_match:
                            ok, nbytes = await _stream_to_file(
                                client,
                                "https://drive.google.com/uc",
                                dest_path,
                                params={
                                    "export": "download",
                                    "confirm": confirm.group(1),
                                    "id": file_id_match.group(1),
                                },
                            )
                            if ok:
                                return True

                # Last resort on first attempt: try streaming the original URL
                if attempt == 1:
                    ok, nbytes = await _stream_to_file(client, url, dest_path)
                    if ok:
                        return True

                logger.warning(
                    "Unexpected response for %s: HTTP %s ctype=%s bytes=%d (attempt %d)",
                    url, r.status_code, ctype, len(r.content), attempt,
                )

        except Exception as exc:
            logger.warning(
                "download_pdf_from_url attempt %d failed for %s: %s",
                attempt, url, exc,
            )

        if attempt == 1:
            import asyncio
            await asyncio.sleep(3)

    return False


# ────────────────────────────────────────────────────────────────────────
# PDF → articles with bounding boxes
# ────────────────────────────────────────────────────────────────────────


async def extract_articles_from_pdf(
    pdf_path: str,
    language: str = "en",
    max_pages: int = 24,
) -> list[dict]:
    """
    Extract individual articles from a newspaper PDF.

    Strategy (proven in sentinel_old):
      Tier 1  Groq Vision (Llama 4 Scout) — OCR + layout + bboxes in one call
              per page. This is what actually works on scanned newspapers.
      Tier 2  OpenDataLoader PDF — for digital-text PDFs.
      Tier 3  PyMuPDF text blocks — final fallback.

    Returns a list of dicts: headline, text, bounding_box [l,t,r,b] in PDF
    points (top-down Y so the renderer can pass straight to fitz.Rect),
    page_number.
    """
    # Tier 1
    articles = await _extract_via_groq_vision(pdf_path, max_pages=max_pages)
    if articles:
        return articles

    # Tier 2
    try:
        import opendataloader_pdf  # type: ignore[import-not-found]
    except ImportError:
        opendataloader_pdf = None  # type: ignore[assignment]

    if opendataloader_pdf is not None:
        try:
            output_dir = tempfile.mkdtemp()
            opendataloader_pdf.run(
                input_path=pdf_path,
                output_folder=output_dir,
                generate_markdown=True,
                debug=False,
            )
            articles = _articles_from_odl_output(output_dir)
        except Exception as exc:
            logger.warning(
                "OpenDataLoader extraction failed (%s) — falling back to PyMuPDF",
                exc,
            )

    # Tier 3
    if not articles:
        articles = _extract_with_pymupdf(pdf_path)

    return articles


# ────────────────────────────────────────────────────────────────────────
# Tier 1: Groq Vision — page image → articles + bounding boxes
# ────────────────────────────────────────────────────────────────────────

_GROQ_VISION_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

_BBOX_PROMPT = (
    "Extract all news articles from this newspaper page.\n"
    "Ignore: advertisements, classifieds, astrology, weather boxes, "
    "TV schedules, stock tickers, page headers/footers, edition info.\n\n"
    "For each article output:\n"
    "{\n"
    '  "section": "<Politics/Business/Crime/Education/Health/'
    'National/International/City/Sports/Entertainment/Opinion/Other>",\n'
    '  "headline": "<exact headline text>",\n'
    '  "body": "<full article body — every paragraph>",\n'
    '  "language": "<2-letter ISO: en/hi/te/ta/ml/kn/gu/bn/or/pa/ur/mr>",\n'
    '  "bbox": {"top": <0-100>, "left": <0-100>, "bottom": <0-100>, "right": <0-100>}\n'
    "}\n\n"
    "bbox values are percentages of page height/width (0=top-left, 100=bottom-right). "
    "Enclose the article's headline, all body paragraphs, and any inline photo/caption. "
    "Exclude adjacent articles and page borders.\n\n"
    'Output exactly one JSON object: {"articles": [...]}\n'
    "No other text. No markdown fences."
)


async def _extract_via_groq_vision(
    pdf_path: str, max_pages: int = 24,
) -> list[dict]:
    """
    Render each page to a JPEG and ask Groq's vision model to segment it
    into articles with bounding boxes.

    Returns articles with bounding_box in PDF points using top-down Y
    ([left, top, right, bottom]) — our renderer detects this convention
    and skips the PyMuPDF coordinate flip.
    """
    try:
        import fitz  # PyMuPDF
        from PIL import Image
    except ImportError as exc:
        logger.warning("Groq Vision path missing deps: %s", exc)
        return []

    try:
        from backend.nlp.groq_client import groq_manager
    except Exception as exc:
        logger.warning("Groq key manager unavailable: %s", exc)
        return []

    import io

    articles: list[dict] = []
    doc = fitz.open(pdf_path)
    n_pages = min(len(doc), max_pages)
    logger.info("Groq Vision: extracting %d pages from %s", n_pages, pdf_path)

    for page_idx in range(n_pages):
        page = doc[page_idx]
        page_w_pt = page.rect.width
        page_h_pt = page.rect.height

        # Render at 96 DPI (1 pt = 1/72 in → 96/72 = 1.333 zoom)
        pix = page.get_pixmap(matrix=fitz.Matrix(96 / 72, 96 / 72))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        jpg_bytes = buf.getvalue()
        b64 = base64.b64encode(jpg_bytes).decode("utf-8")

        parsed = await _call_groq_vision_page(b64, groq_manager)
        if not parsed:
            continue

        for a in parsed.get("articles", []):
            headline = (a.get("headline") or "").strip()
            body = (a.get("body") or "").strip()
            if not headline or len(body) < 20:
                continue
            bb = a.get("bbox") or {}
            try:
                top_pct = float(bb.get("top", 0))
                left_pct = float(bb.get("left", 0))
                bottom_pct = float(bb.get("bottom", 100))
                right_pct = float(bb.get("right", 100))
            except (TypeError, ValueError):
                continue
            # Convert to PDF points (top-down Y)
            bbox_pts = [
                (left_pct / 100.0) * page_w_pt,
                (top_pct / 100.0) * page_h_pt,
                (right_pct / 100.0) * page_w_pt,
                (bottom_pct / 100.0) * page_h_pt,
            ]
            articles.append({
                "headline": headline[:500],
                "text": body[:10000],
                "bounding_box": bbox_pts,
                "page_number": page_idx + 1,
                "section": (a.get("section") or "").strip(),
                "detected_language": (a.get("language") or "").strip().lower(),
            })

    doc.close()
    logger.info("Groq Vision: extracted %d articles from %s", len(articles), pdf_path)
    return articles


async def _call_groq_vision_page(b64_jpg: str, groq_manager) -> dict | None:
    """Send one page image to Groq Vision, parse the JSON reply.

    Uses the AsyncGroq SDK client obtained from groq_manager.get_key(),
    which returns (key_index, cached_AsyncGroq_client).
    """
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": _BBOX_PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_jpg}"},
            },
        ],
    }]

    # Import error types lazily
    try:
        from groq import APIStatusError, RateLimitError  # type: ignore
    except Exception:
        APIStatusError = Exception  # type: ignore
        RateLimitError = Exception  # type: ignore

    for attempt in range(3):
        try:
            key_index, client = await groq_manager.get_key()
        except Exception as exc:
            logger.warning("No Groq key available: %s", exc)
            return None

        try:
            resp = await client.chat.completions.create(
                model=_GROQ_VISION_MODEL,
                messages=messages,
                max_tokens=4096,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
        except RateLimitError:  # type: ignore
            logger.info("Groq 429 — rotating key (attempt %d)", attempt + 1)
            try:
                groq_manager.mark_exhausted(key_index)
            except Exception:
                pass
            continue
        except APIStatusError as exc:  # type: ignore
            logger.warning("Groq Vision APIStatusError: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Groq Vision request failed: %s", exc)
            return None

        content = (resp.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        try:
            return json.loads(content)
        except Exception as exc:
            logger.warning(
                "Groq Vision JSON parse failed: %s (first 200: %s)",
                exc, content[:200],
            )
            return None

    return None


def _articles_from_odl_output(output_dir: str) -> list[dict]:
    """
    Walk OpenDataLoader 0.0.16's nested JSON tree:
        root dict { file name, number of pages, kids: [ page_dict, ... ] }
        page_dict { type: 'page', kids: [ element_dict, ... ] }
        element_dict { type, page number, bounding box, content?, kids? }

    Types observed on e-paper PDFs include: page, heading, paragraph,
    text, table, image, figure. Scanned newspapers often produce
    element types without "content" — OCR text lives in the .md file
    alongside the .json, so we also consume that as a fallback.
    """
    articles: list[dict] = []

    # Walk every .json file produced
    for root, _, files in os.walk(output_dir):
        for fname in files:
            fp = os.path.join(root, fname)
            if not fp.endswith(".json"):
                continue
            try:
                with open(fp) as f:
                    data = json.load(f)
            except Exception:
                continue

            # Root is a dict with "kids" — unwrap
            if isinstance(data, dict):
                elements = _flatten_odl_elements(data.get("kids", []))
            elif isinstance(data, list):
                elements = _flatten_odl_elements(data)
            else:
                continue

            current: dict | None = None
            for element in elements:
                elem_type = (element.get("type") or "").lower()
                content = element.get("content") or element.get("text") or ""
                bbox = element.get("bounding box") or element.get("bbox") or []
                page = element.get("page number") or element.get("page", 1)

                if not isinstance(content, str):
                    continue

                is_heading = elem_type in ("heading", "title", "h1", "h2", "h3")
                is_body = elem_type in ("paragraph", "text", "body", "p")

                if is_heading and len(content.strip()) > 10:
                    if current and len(current["text"]) > 80:
                        articles.append(current)
                    current = {
                        "headline": content.strip(),
                        "text": "",
                        "bounding_box": list(bbox) if bbox else [],
                        "page_number": page,
                    }
                elif current and is_body and len(content.strip()) > 15:
                    current["text"] += " " + content.strip()
                    if bbox and current["bounding_box"] and len(bbox) >= 4 \
                       and len(current["bounding_box"]) >= 4:
                        cb = current["bounding_box"]
                        current["bounding_box"] = [
                            min(cb[0], bbox[0]),
                            min(cb[1], bbox[1]),
                            max(cb[2], bbox[2]),
                            max(cb[3], bbox[3]),
                        ]

            if current and len(current["text"]) > 80:
                articles.append(current)

    # If JSON gave us nothing but markdown is present (scanned PDFs),
    # parse markdown into pseudo-articles by splitting on headers.
    if not articles:
        for root, _, files in os.walk(output_dir):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fp = os.path.join(root, fname)
                try:
                    with open(fp, encoding="utf-8") as f:
                        md = f.read()
                except Exception:
                    continue
                if not md.strip():
                    continue
                articles.extend(_articles_from_markdown(md))

    return articles


def _flatten_odl_elements(kids: list, depth: int = 0) -> list[dict]:
    """Depth-first walk of the odl kids[] tree, yielding leaf elements."""
    out: list[dict] = []
    if depth > 10:
        return out
    for kid in kids or []:
        if not isinstance(kid, dict):
            continue
        nested = kid.get("kids") or kid.get("children")
        if nested:
            # Emit this node too (it may carry summary content), then recurse
            if kid.get("content") or kid.get("text"):
                out.append(kid)
            out.extend(_flatten_odl_elements(nested, depth + 1))
        else:
            out.append(kid)
    return out


def _articles_from_markdown(md: str) -> list[dict]:
    """
    Split a markdown document into pseudo-articles using headings
    (lines starting with #). Each article has no bounding_box (PyMuPDF
    fallback can supply one later if the md lacks coordinates).
    """
    articles: list[dict] = []
    lines = md.splitlines()
    buf: list[str] = []
    headline: str | None = None

    def flush() -> None:
        if headline and buf and sum(len(l) for l in buf) > 80:
            articles.append({
                "headline": headline[:200],
                "text": "\n".join(buf).strip(),
                "bounding_box": [],
                "page_number": 1,
            })

    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            flush()
            headline = s.lstrip("# ").strip() or None
            buf = []
        elif s:
            buf.append(s)
    flush()
    return articles


def _extract_with_pymupdf(pdf_path: str) -> list[dict]:
    """PyMuPDF fallback: treat each long text block as one article."""
    articles: list[dict] = []
    try:
        import fitz

        doc = fitz.open(pdf_path)
        for page_num, page in enumerate(doc, 1):
            blocks = page.get_text("blocks")
            for block in blocks:
                if block[6] != 0:
                    continue
                text = block[4].strip()
                if len(text) <= 100:
                    continue
                lines = text.split("\n")
                headline = lines[0]
                body = " ".join(lines[1:])
                articles.append(
                    {
                        "headline": headline[:200],
                        "text": body,
                        "bounding_box": list(block[:4]),
                        "page_number": page_num,
                    }
                )
        doc.close()
    except Exception as exc:
        logger.warning("PyMuPDF fallback failed: %s", exc)
    return articles


# ────────────────────────────────────────────────────────────────────────
# Article region → base64 PNG clipping
# ────────────────────────────────────────────────────────────────────────


def render_article_clipping(
    pdf_path: str,
    page_number: int,
    bbox: list[float],
    scale: float = 1.2,
    quality: int = 72,
    max_bytes: int = 250_000,
) -> str | None:
    """
    Render a single article region as a base64-encoded JPEG.

    JPEG @ 1.2x scale + q=72 produces ~40-80 KB clippings that render
    crisply in the browser without bloating the Postgres row (PNG was
    producing 5 MB artefacts and blowing up the INSERT).
    """
    try:
        import fitz
        from PIL import Image
        import io

        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        page_height = page.rect.height

        if len(bbox) < 4:
            doc.close()
            return None

        page_width = page.rect.width

        # Some upstream extractors leak normalized bbox values (percentages
        # or 0..1 fractions) instead of PDF points. If the whole bbox lives
        # inside the first 100 units of a page that's ~600 pts wide, it has
        # to be normalized — rescale to points before rendering, otherwise
        # we get a 12×11 px crop that's useless on screen.
        max_v = max(bbox[:4])
        if max_v <= 1.5:
            scale_x, scale_y = page_width, page_height
        elif max_v <= 100:
            scale_x, scale_y = page_width / 100.0, page_height / 100.0
        else:
            scale_x = scale_y = 1.0
        b = [
            bbox[0] * scale_x,
            bbox[1] * scale_y,
            bbox[2] * scale_x,
            bbox[3] * scale_y,
        ]

        # Detect coordinate convention. Groq Vision returns top-down Y
        # (top < bottom); PyMuPDF blocks are top-down too; OpenDataLoader
        # returns bottom-up.
        if b[1] < b[3]:
            rect = fitz.Rect(b[0], b[1], b[2], b[3])
        else:
            rect = fitz.Rect(
                b[0], page_height - b[3],
                b[2], page_height - b[1],
            )
        rect = rect + fitz.Rect(-3, -3, 3, 3)

        # Safety: if the rect is still too small to be useful, skip — the
        # frontend falls back to a masthead-initials thumbnail.
        if rect.width < 30 or rect.height < 30:
            doc.close()
            return None

        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()

        # Try decreasing quality until under max_bytes
        buf = io.BytesIO()
        for q in (quality, 60, 50, 40):
            buf.seek(0); buf.truncate()
            img.save(buf, format="JPEG", quality=q, optimize=True)
            if buf.tell() <= max_bytes:
                break
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    except Exception as exc:
        logger.warning("Clipping render failed: %s", exc)
        return None


# ────────────────────────────────────────────────────────────────────────
# Relevance gate
# ────────────────────────────────────────────────────────────────────────


async def is_relevant_to_user(
    headline: str,
    text: str,
    user_entities: list[str],
    user_geos: list[str] | str,
) -> tuple[bool, float, str]:
    """Newsprint-specific relevance scorer. Returns (is_relevant, score, reason).

    CODE-2: `user_geos` accepts a list of distinct user geographies (one
    string for back-compat with existing single-tenant callers). The
    article is relevant if it covers ANY of them. Previously this used
    the geography of an arbitrary single user via `LIMIT 1`, biasing
    every newspaper's relevance scoring to one location.
    """
    combined = ((headline or "") + " " + (text or "")).lower()

    score = 0.0
    reasons: list[str] = []

    for entity in user_entities:
        if entity and entity.lower() in combined:
            score += 0.4
            reasons.append(f"{entity} mentioned")
            break

    # Normalise to list of unique non-empty lowercase geo keys
    if isinstance(user_geos, str):
        geos_list = [user_geos] if user_geos else []
    else:
        geos_list = list(user_geos or [])
    geo_keys = {g.strip().lower() for g in geos_list if g and g.strip()}

    # Geography match across English/Telugu/Hindi/Malayalam/Tamil/Kannada/Marathi/Bengali/Gujarati/Punjabi transliterations
    geo_aliases: dict[str, tuple[str, ...]] = {
        "telangana": (
            "telangana", "తెలంగాణ", "तेलंगाना", "hyderabad", "హైదరాబాద్", "हैदराबाद",
            "ടെലങ്കാന", "ஹைதராபாத்", "ತೆಲಂಗಾಣ", "তেলেঙ্গানা", "તેલંગાણા", "ਤੇਲੰਗਾਨਾ",
        ),
        "hyderabad": (
            "hyderabad", "telangana",
            "హైదరాబాద్", "తెలంగాణ", "हैदराबाद", "तेलंगाना",
            "ടെലങ്കാന", "ஹைதராபாத்", "ತೆಲಂಗಾಣ", "তেলেঙ্গানা", "તેલંગાણા", "ਤੇਲੰਗਾਨਾ",
        ),
        "andhra pradesh": (
            "andhra", "ఆంధ్ర", "आंध्र",
            "ஆந்திர", "ಆಂಧ್ರ", "ആന്ധ്ര", "অন্ধ্র", "આંધ્ર",
        ),
    }
    geo_matched: str | None = None
    for key in geo_keys:
        aliases = geo_aliases.get(key, (key,))
        if any(a and a in combined for a in aliases):
            geo_matched = key
            break
    if geo_matched is not None:
        score += 0.3
        reasons.append(f"Covers {geo_matched}")

    political_terms = (
        # English
        "government", "minister", "cm", "chief minister", "assembly",
        "cabinet", "policy", "scheme", "budget", "court", "order",
        "telangana", "hyderabad", "revanth", "kcr", "brs",
        "congress", "bjp", "modi", "parliament", "election",
        "kishan reddy", "rama rao", "ktr", "chandrashekar",
        # Telugu
        "తెలంగాణ", "హైదరాబాద్", "కాంగ్రెస్", "బిజెపి",
        "ముఖ్యమంత్రి", "ప్రభుత్వం", "రేవంత్", "కేసీఆర్",
        "కేటీఆర్", "మోదీ", "బీఆర్‌ఎస్", "చంద్రశేఖర్",
        # Hindi
        "सरकार", "मुख्यमंत्री", "कांग्रेस", "भाजपा",
        "तेलंगाना", "हैदराबाद", "मोदी", "रेवंत", "केसीआर",
        # Other Indic
        "ടെലങ്കാന", "കോൺഗ്രസ്", "ബിജെപി",  # Malayalam
        "தெலுங்கானா", "காங்கிரஸ்", "பிஜேபி", "மோடி",  # Tamil
        "ತೆಲಂಗಾಣ", "ಕಾಂಗ್ರೆಸ್", "ಬಿಜೆಪಿ", "ಮೋದಿ",  # Kannada
        "तेलंगणा", "काँग्रेस", "भाजप",  # Marathi
        "তেলেঙ্গানা", "কংগ্রেস", "বিজেপি",  # Bengali
        "તેલંગાણા", "કોંગ્રેસ", "ભાજપ",  # Gujarati
        "ਤੇਲੰਗਾਨਾ", "ਕਾਂਗਰਸ", "ਭਾਜਪਾ",  # Punjabi
    )
    for term in political_terms:
        if term in combined:
            score += 0.1
            break

    reason_text = ". ".join(reasons) if reasons else "Matched geography coverage"
    return score >= 0.3, score, reason_text
