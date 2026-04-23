"""Inspect ODL output on cached PDF (no re-download)."""
import json
import os
import tempfile


def walk_types(node, counts=None, depth=0, max_sample=None):
    counts = counts if counts is not None else {}
    max_sample = max_sample if max_sample is not None else {}
    if isinstance(node, dict):
        t = node.get("type", "?")
        counts[t] = counts.get(t, 0) + 1
        # Keep one sample of each type
        if t not in max_sample:
            max_sample[t] = node
        for kids_key in ("kids", "children"):
            if kids_key in node and isinstance(node[kids_key], list):
                for kid in node[kids_key]:
                    walk_types(kid, counts, depth + 1, max_sample)
    return counts, max_sample


def main():
    pdf_path = "/app/scripts/_toi.pdf"
    print(f"PDF size: {os.path.getsize(pdf_path)}")

    import opendataloader_pdf
    out = tempfile.mkdtemp()
    opendataloader_pdf.run(
        input_path=pdf_path, output_folder=out, generate_markdown=True, debug=False,
    )
    for root, _, files in os.walk(out):
        for f in files:
            fp = os.path.join(root, f)
            size = os.path.getsize(fp)
            print(f"FILE: {f} ({size} bytes)")
            if f.endswith(".json"):
                with open(fp) as fh:
                    data = json.load(fh)
                counts, samples = walk_types(data)
                print(f"  type counts across entire tree: {counts}")
                for t in ("heading", "title", "paragraph", "text", "body", "p", "page"):
                    if t in samples:
                        sample = samples[t]
                        content = sample.get("content") or sample.get("text") or ""
                        print(f"  sample '{t}': keys={list(sample.keys())[:10]}")
                        if content:
                            print(f"    content[:160]: {content[:160]!r}")
                        else:
                            print(f"    (no content field — keys omitted)")
            elif f.endswith(".md"):
                with open(fp, encoding="utf-8") as fh:
                    md = fh.read()
                print(f"  MD len={len(md)}")
                # Find headings
                lines = md.splitlines()
                hdrs = [l for l in lines if l.startswith("#")]
                print(f"  # headings: {len(hdrs)}")
                for h in hdrs[:10]:
                    print(f"    {h[:100]}")
                print(f"  first 400 chars: {md[:400]!r}")


if __name__ == "__main__":
    main()
