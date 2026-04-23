"""Debug extraction — what does OpenDataLoader 0.0.16 + PyMuPDF actually produce?"""
import asyncio
import json
import os
import tempfile

from backend.collectors.newspaper_collector import download_pdf_from_url


async def main() -> None:
    url = "https://drive.google.com/uc?export=download&id=1YQW2JP62haRmoHaMtc4yrVClXZ2_iRaD"
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    await download_pdf_from_url(url, path)
    print(f"PDF size: {os.path.getsize(path)}")

    # 1. OpenDataLoader
    import opendataloader_pdf
    out = tempfile.mkdtemp()
    opendataloader_pdf.run(
        input_path=path, output_folder=out, generate_markdown=False, debug=False,
    )
    # odl may nest output in subdirs — walk
    all_files = []
    for root, _, files in os.walk(out):
        for f in files:
            all_files.append(os.path.join(root, f))
    print(f"ODL produced {len(all_files)} files total")
    for fp in all_files[:8]:
        size = os.path.getsize(fp)
        rel = os.path.relpath(fp, out)
        print(f"  {rel}: {size} bytes")
        if fp.endswith(".json") and size < 5_000_000:
            with open(fp) as fh:
                try:
                    data = json.load(fh)
                except Exception as e:
                    print(f"    parse err: {e}")
                    continue
            if isinstance(data, dict):
                print(f"    DICT keys: {list(data.keys())[:12]}")
                # If it has a 'pages' or 'elements' nested list
                for k, v in data.items():
                    if isinstance(v, list) and v:
                        print(f"    {k}: list[{len(v)}] sample_keys={list(v[0].keys())[:8] if isinstance(v[0], dict) else type(v[0]).__name__}")
                        break
            elif isinstance(data, list):
                print(f"    LIST of {len(data)}")
                if data and isinstance(data[0], dict):
                    print(f"    sample keys: {list(data[0].keys())[:12]}")

    # 2. PyMuPDF
    import fitz
    doc = fitz.open(path)
    print(f"\nPyMuPDF: {len(doc)} pages")
    for page_num in range(min(3, len(doc))):
        page = doc[page_num]
        blocks = page.get_text("blocks")
        text_blocks = [b for b in blocks if b[6] == 0]
        long_blocks = [b for b in text_blocks if len(b[4].strip()) > 100]
        print(f"  Page {page_num+1}: {len(blocks)} blocks, {len(text_blocks)} text, {len(long_blocks)} long")
        if text_blocks:
            longest = max(text_blocks, key=lambda b: len(b[4]))
            print(f"    longest len={len(longest[4])} preview={longest[4][:120].replace(chr(10),' ')!r}")
    doc.close()


if __name__ == "__main__":
    asyncio.run(main())
