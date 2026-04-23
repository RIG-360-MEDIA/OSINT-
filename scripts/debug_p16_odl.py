"""Dig into OpenDataLoader's actual JSON schema."""
import asyncio
import json
import os
import tempfile

from backend.collectors.newspaper_collector import download_pdf_from_url


def walk_element(el: dict, depth: int = 0, counts: dict | None = None) -> dict:
    counts = counts if counts is not None else {}
    if isinstance(el, dict):
        t = el.get("type", "?")
        counts[t] = counts.get(t, 0) + 1
        # Find any text-bearing fields
        for key in ("content", "text", "raw_text", "cleaned_text"):
            if key in el and isinstance(el[key], str) and len(el[key]) > 50:
                if depth < 2:
                    print(f"{'  '*depth}[{t}] {key}[:80]: {el[key][:80]!r}")
                break
        for kid in el.get("kids") or el.get("children") or []:
            walk_element(kid, depth + 1, counts)
    return counts


async def main() -> None:
    url = "https://drive.google.com/uc?export=download&id=1YQW2JP62haRmoHaMtc4yrVClXZ2_iRaD"
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    await download_pdf_from_url(url, path)

    import opendataloader_pdf
    out = tempfile.mkdtemp()
    opendataloader_pdf.run(
        input_path=path, output_folder=out, generate_markdown=True, debug=False,
    )
    for root, _, files in os.walk(out):
        for f in files:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, out)
            size = os.path.getsize(fp)
            print(f"FILE: {rel} ({size} bytes)")
            if f.endswith(".md"):
                with open(fp) as fh:
                    md = fh.read()
                print(f"  MD preview: {md[:500]!r}")
            elif f.endswith(".json"):
                with open(fp) as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    print(f"  JSON root dict keys: {list(data.keys())}")
                    kids = data.get("kids", [])
                    print(f"  {len(kids)} kids at root")
                    if kids:
                        print(f"  First kid type: {kids[0].get('type')}, keys: {list(kids[0].keys())}")
                        # Walk the first kid to find content
                        print("  First kid nested tree:")
                        counts = walk_element(kids[0])
                        print(f"  Type counts across first kid: {counts}")
                        # Walk all kids for aggregate type counts
                        agg: dict = {}
                        for k in kids:
                            walk_element(k, depth=99, counts=agg)  # no print
                        print(f"  AGGREGATE element type counts: {agg}")


if __name__ == "__main__":
    asyncio.run(main())
