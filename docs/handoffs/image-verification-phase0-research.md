# Image Verification — Phase 0 Research (no code)

Scope: verify where an image appeared, since when, whether edited, whether AI-generated.
Hard constraint: runs from a **Hetzner datacenter IP** — many services CAPTCHA server IPs.
Date: 2026-07-10. Every concrete claim is URL-cited. Brutally honest; "signal, not proof".

---

## 1. Reverse image search — "where + when?"

### Yandex
- **No official reverse-image API.** Programmatic use = scraping the web endpoint (`/images/search?rpt=imageview&url=`) with a headless browser. [oxylabs](https://oxylabs.io/blog/how-to-scrape-yandex)
- **Datacenter reality: CAPTCHA-walls hard.** Yandex flags/blocks IPs once CAPTCHA triggers, which happens fast from datacenter ranges; raw scripts need constant maintenance. [oxylabs](https://oxylabs.io/blog/how-to-scrape-yandex)
- Still the **strongest for faces / recycled people photos** per OSINT community. [Bellingcat toolkit](https://bellingcat.gitbook.io/toolkit/categories/image-video/reverse-image-search)
- Verdict: **great results, but NOT reliably reachable from a server IP unencrypted.** Only viable via paid proxy/SERP wrappers (SerpApi/SearchApi/ScrapingBee). [searchapi](https://www.searchapi.io/docs/yandex-reverse-image-api)

### Bing Visual Search
- **DEAD as an API.** All Bing Search APIs (Web/Image/Video/News/Entity/**Visual Search**) were **retired August 11, 2025**, fully decommissioned, no new signups. [Microsoft Learn](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement)
- Microsoft's "replacement" = *Grounding with Bing Search* inside Azure AI Agents — an LLM product, not a SERP/visual API, and 40–483% costlier. [ppc.land](https://ppc.land/microsoft-ends-bing-search-apis-on-august-11-alternative-costs-40-483-more/)
- Verdict: **do not build on Bing API.** Web endpoint scraping only, same datacenter-CAPTCHA risk as Yandex.

### TinEye
- **Real official API**, exact/near-exact copy matching (no faces). [TinEye API](https://services.tineye.com/TinEyeAPI)
- **"Sort by oldest" gives first-appearance dates** — the single most useful "since when" signal. [Bellingcat](https://bellingcat.gitbook.io/toolkit/categories/image-video/reverse-image-search)
- **Paid, no free API tier.** Bundles from **$200/mo (5k searches, ~$0.04/search)** down to ~$0.01 at enterprise. [TinEye blog](https://blog.tineye.com/new-image-search-pricing/)
- Server-friendly (it's an API, no CAPTCHA). Commercial use = the licensed product.
- Verdict: **best "where+when" for money**; API is datacenter-clean.

### Google Lens / Google Images
- **No official API.** Since **Feb 2025 "search by image" always redirects to Google Lens.** [SerpApi/DEV](https://dev.to/bartek_serpapi/how-google-replaced-search-by-image-with-google-lens-55gm)
- Largest index / highest correct-ID rate in OSINT testing. [Bellingcat](https://bellingcat.gitbook.io/toolkit/categories/image-video/reverse-image-search)
- Programmatic route = paid scrapers (SerpApi Google Lens API) — not free, not raw-server-safe. [SerpApi](https://serpapi.com/google-lens-api)

### SearXNG (we self-host)
- **Has a built-in TinEye reverse-image engine** — but **by image URL only, no file upload, and it does NOT use the official API** (it scrapes TinEye's public widget). [SearXNG docs](https://docs.searxng.org/dev/engines/online_url_search/tineye.html)
- Keyword image search yes; general reverse-by-upload no. The image must already be hosted at a public URL. [SearXNG issue #291](https://github.com/searxng/searxng/issues/291)
- Verdict: **free, self-hosted, datacenter-native "who else hosts this exact image" via the TinEye engine** — good first cheap pass, but brittle (scraped, URL-only, no dates guaranteed).

### Newer players
- **Lenso.ai** — has a public reverse-image API (base64, categories People/Duplicates/Places, sort newest/oldest), but **pricing starts ~$2,800/mo**. Not free. [GitHub lenso-ai](https://github.com/lenso-ai/reverse-image-search-api)
- **Copyseeker** — **free tier**, smaller index, API via RapidAPI **$0–$300**. Cheapest "extra coverage" option worth a pilot. [lenso blog](https://lenso.ai/en/blog/general/top-4-best-reverse-image-search-apis)

### FOSS self-hostable
- No FOSS tool gives web-scale "where has this appeared" — that needs an index we don't have. Self-hostable only covers **matching against your OWN corpus** (perceptual hash / FAISS). Treat SearXNG-TinEye as the only free "web index" route.

### RANK (free/cheap, works from a server IP, returns usable where+when)
1. **SearXNG TinEye engine** (free, self-hosted, datacenter-clean) — first pass, exact copies.
2. **TinEye API** ($200/mo) — reliable API, first-seen dates, no CAPTCHA — the paid backbone.
3. **Copyseeker** (free–$300 RapidAPI) — cheap extra index coverage.
4. **Google Lens / Yandex via SerpApi** (paid per-search) — only when a case needs their index/faces; never raw from Hetzner.
- **Raw Yandex/Google/Bing scraping from Hetzner = unreliable (CAPTCHA/retired). Do not depend on it.**

---

## 2. Tampering + AI-generated detectors (vetted)

Honest headline: **free AI-image detectors are a weak signal.** Accuracy collapses on unseen generators and on compressed social images. Independent arena rates **Organika/sdxl-detector at 60.5% overall, 17.1% false-positive rate** (flags real photos as AI). [AI Detector Arena](https://aidetectarena.com/detectors/hf-sdxl-detector) Academic consensus: methods near-perfect on their training generator, **drop sharply on unseen generators**. [UniversalFakeDetect CVPR23](https://openaccess.thecvf.com/content/CVPR2023/papers/Ojha_Towards_Universal_Fake_Image_Detectors_That_Generalize_Across_Generative_Models_CVPR_2023_paper.pdf) A 2026 paper shows detectors over-rely on global artifacts and miss inpainting. [arxiv 2602.00192](https://arxiv.org/pdf/2602.00192)

### Classic forensics (deterministic, explainable — prefer these)
- **Sherloq** (GuidoBartoli/sherloq) — full local suite: ELA, JPEG-quality, double-compression ML, copy-move, splicing (DCT), resampling. **Free OSS, runs fully offline/local**, no upload. [GitHub](https://github.com/GuidoBartoli/sherloq) — desktop/PySide app; not a clean pip library, but the algorithms are portable. License: GPL-family (check before shipping in a closed product).
- Standalone ELA scripts exist if we only want ELA (shurain/ela, prsntmaurya). [ela](https://github.com/shurain/ela)
- These give **explainable, reproducible signals** (recompression/clone traces) — better courtroom logic than a black-box "AI: 73%".

### AI-generated detectors (use as soft signal only)
- **Organika/sdxl-detector** (HF) — fine-tuned from umm-maybe; pip via `transformers`, pretrained weights on HF, runs on a single image. **~60% real-world accuracy, high false positives.** [HF](https://huggingface.co/Organika/sdxl-detector) / [arena](https://aidetectarena.com/detectors/hf-sdxl-detector)
- **UniversalFakeDetect** (WisconsinAIVision / Yuheng-Li) — CVPR'23, code+weights, best-in-class generalization for its era. Research code, not pip; good if we self-host a model. [GitHub](https://github.com/WisconsinAIVision/UniversalFakeDetect)
- **DIRE** (ICCV'23) — diffusion-image detector; research repo. [awesome list](https://github.com/yjtlab/awesome-aigc-image-detection)
- Curated tracking of active repos/benchmarks: [awesome-aigc-image-detection](https://github.com/yjtlab/awesome-aigc-image-detection), [AIGCDetectBenchmark](https://github.com/Ekko-zn/AIGCDetectBenchmark).

### Deepfake / face-manipulation
- We do NOT do face recognition. For manipulation, the same generalization caveat dominates. Sherloq's splicing/copy-move + an AI-gen score is the honest ceiling for a free stack. No free deepfake detector is trustworthy enough to state as fact.

**Reliability verdict:** ship AI-gen detection ONLY as a labeled probability ("possible AI, low confidence"), never as a verdict. Deterministic forensics (ELA/copy-move/double-JPEG) is the stronger, defensible signal.

---

## 3. Supporting

### EXIF
- **exiftool > Pillow.** Pillow reads only basic EXIF tags; exiftool reads EXIF+IPTC+XMP+maker-notes+GPS across far more formats. Use **exiftool** (shell/`pyexiftool`) for extraction; Pillow only if a pure-Python dep is required.
- **Social platforms strip EXIF on the public copy** — Instagram (all), Facebook (GPS/camera/timestamp), Twitter/X (all). [privacystrip](https://privacystrip.com/blog/social-media-metadata-policies/)
- **Messengers depend on send mode:** WhatsApp/Telegram **strip when sent as compressed "photo"** but **preserve 100% when sent as "Document/File".** [dev.to guide](https://dev.to/samma1997/which-apps-strip-photo-metadata-the-complete-2026-guide-5ghh)
- Implication: absence of EXIF proves nothing (it was likely stripped on upload); presence of GPS/timestamp is a strong lead only if provenance of the file is known.

### Perceptual hashing
- **Yes — core free building block.** Python `imagehash` (phash/dhash/whash/ahash); pHash robust to mild JPEG recompression/resize/overlays, sensitive to flips/crops/color-shift. [benhoyt](https://benhoyt.com/writings/duplicate-image-detection/) Use to dedup, cluster near-dupes, and match against our own stored corpus (pair with FAISS). Datacenter-native, free, deterministic.

---

## 4. Bottom line — the free/cheap, datacenter-runnable stack

**Reverse image (where+when):**
1. **SearXNG TinEye engine** — free, self-hosted, first pass for exact copies. [docs](https://docs.searxng.org/dev/engines/online_url_search/tineye.html)
2. **TinEye API** ($200/mo) — the paid backbone: clean API, first-seen dates, no CAPTCHA. **This is where money is unavoidable if we need reliable dated coverage.** [pricing](https://blog.tineye.com/new-image-search-pricing/)
3. **Copyseeker** (free–$300) — cheap extra index. [ref](https://lenso.ai/en/blog/general/top-4-best-reverse-image-search-apis)
4. Google Lens / Yandex **only via paid SerpApi** when a case demands their index/faces — never raw from Hetzner (CAPTCHA). Bing API is **retired, ignore it**. [MS](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement)

**EXIF:** **exiftool** (via `pyexiftool`). Treat missing metadata as inconclusive.

**Tampering signal (strong, deterministic):** port **Sherloq**'s ELA + copy-move + double-JPEG (mind GPL). [repo](https://github.com/GuidoBartoli/sherloq)

**AI-generated signal (weak, label clearly):** **Organika/sdxl-detector** for a quick score, optionally self-host **UniversalFakeDetect**. State as probability only — ~60% real-world accuracy, high false positives. [arena](https://aidetectarena.com/detectors/hf-sdxl-detector)

**Near-dupe / own-corpus match:** **imagehash pHash + FAISS** — free, datacenter-native.

**Where paid is genuinely required:** reliable dated web coverage (TinEye API), and any Google/Yandex/Bing-index result (paid SERP proxies) — because raw datacenter scraping of those is CAPTCHA-walled or retired.

**Overall honesty line for the product UI:** the free stack produces *leads and signals* (exact-copy hits, first-seen date from TinEye, forensic traces, an AI-gen probability), **not proof**. Every automated verdict must be presented as confidence-scored evidence for a human analyst.
