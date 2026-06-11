"""Compare Tesseract hin FAST (apt default) vs BEST (tessdata_best) on Devanagari."""
import os
import fitz
import numpy as np
import pytesseract
from PIL import Image

PDF = "/tmp/Dainik_Bhaskar.pdf"
BEST_DIR = "/tmp/tessdata_best"

doc = fitz.open(PDF)
page = doc[0]
# Native-res render (same as pipeline).
imgs = page.get_images(full=True)
native_w = max((doc.extract_image(i[0])["width"] for i in imgs), default=0)
zoom = max(220 / 72, (native_w / page.rect.width) if page.rect.width else 3.0)
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
pil = Image.fromarray(img)
print(f"render {pix.width}x{pix.height} (zoom {zoom:.2f})")
print("tesseract:", pytesseract.get_tesseract_version())

# Crop the top headline band so we compare on the same text.
band = pil.crop((0, 0, pix.width, int(pix.height * 0.18)))

print("\n=== FAST (apt tesseract-ocr-hin) ===")
print(pytesseract.image_to_string(band, lang="hin", config="--psm 6 --oem 3")[:600])

best_ok = os.path.exists(f"{BEST_DIR}/hin.traineddata")
print(f"\n=== BEST present={best_ok} ===")
if best_ok:
    cfg = f'--psm 6 --oem 1 --tessdata-dir {BEST_DIR}'
    print(pytesseract.image_to_string(band, lang="hin", config=cfg)[:600])
