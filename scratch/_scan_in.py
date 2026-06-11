import openpyxl
from urllib.parse import urlparse

P = r"D:\global_news_dataset_PERFECTED_20260527 (2).xlsx"
our = set()
with open(r"C:\Users\Dell\Desktop\rig-surveillance\scratch\_our_sources.csv", encoding="utf-8") as f:
    for line in f:
        p = line.strip().split(",", 1)
        if len(p) > 1 and p[1].strip():
            d = p[1].strip().lower()
            our.add(d[4:] if d.startswith("www.") else d)


def dom(u):
    n = urlparse(str(u) if "://" in str(u) else "http://" + str(u)).netloc.lower()
    return n[4:] if n.startswith("www.") else n


wb = openpyxl.load_workbook(P, read_only=True, data_only=True)
rows = list(wb["IN - India"].iter_rows(values_only=True))
h = {str(c).strip(): i for i, c in enumerate(rows[0])}
UTT = ["uttarakhand", "garhwal", "kumaon", "dehradun", "nainital", "haridwar", "rishikesh"]
KAS = ["kashmir", "srinagar", "jammu"]


def scan(kws, label):
    found = []
    for r in rows[1:]:
        blob = (str(r[h["website_name"]] or "") + " " + str(r[h["url"]] or "")).lower()
        if any(k in blob for k in kws):
            acc = str(r[h["access_status"]]).strip()
            d = dom(r[h["url"]])
            found.append((r[h["website_name"]], d, acc, d in our))
    live = [x for x in found if x[2] == "LIVE"]
    new_live = [x for x in live if not x[3]]
    print(f"\n=== {label}: {len(found)} matches | LIVE {len(live)} | LIVE & NOT-ours {len(new_live)} ===")
    for n, d, acc, mine in found:
        print(f"  {'OURS' if mine else 'NEW '} {acc:14} {d}  ({str(n)[:34]})")


scan(UTT, "UTTARAKHAND")
scan(KAS, "KASHMIR")
print("\nIN sheet total source rows:", len(rows) - 1)
