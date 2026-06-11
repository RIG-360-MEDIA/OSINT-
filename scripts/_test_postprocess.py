import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from backend.collectors.newspaper_layout.postprocess import (
    normalize_section, is_notice, mark_duplicates,
)

print("== section ==")
for s, exp in [("అంతర్జాతీయం", "International"), ("జాతీయం", "National"),
               ("Auto Zone", "Business"), ("Business", "Business"),
               ("Economy", "Economy"), ("", "Other"), ("राष्ट्रीय", "National"),
               ("खेल", "Sports")]:
    got = normalize_section(s)
    print(f"  {s!r:18} -> {got:13} {'OK' if got == exp else 'FAIL exp ' + exp}")

print("== is_notice (True expected) ==")
for h, b in [("ZEPTO LIMITED", ""), ("WIPRO LIMITED", ""),
             ("POSSESSION NOTICE APPENDIX IV", "rule 8(2)"),
             ("DEMAND NOTICE UNDER SEC.13 (2)", ""),
             ("Canara Bank", "possession notice under sarfaesi"),
             ("ANCHOR INVESTOR BIDDING DATE OPENED", "")]:
    print(f"  {is_notice(h, b)!s:5}  {h[:40]}")

print("== is_notice (False expected — real news) ==")
for h, b in [("Adani Energy to buy IntelliSmart for ₹3,050 cr", "Adani Energy Solutions on Tuesday signed"),
             ("Maruti to invest ₹925 crore in green energy projects by FY31", "Maruti Suzuki India on Friday"),
             ("AI agents may equal TCS' human workforce in 3 yrs", "Artificial intelligence could"),
             ("SBI transfers ₹8,800 cr as FY26 dividend", "State Bank of India")]:
    print(f"  {is_notice(h, b)!s:5}  {h[:48]}")

print("== dedup ==")
arts = [
    {"headline": "Adani Energy to buy IntelliSmart for ₹3,050 cr", "page_number": 1, "text": "short teaser"},
    {"headline": "Adani Energy to buy IntelliSmart for ₹3,050 crore", "page_number": 4, "text": "x" * 800},
    {"headline": "Siri jumps on AI bandwagon in more 'personal' avatar", "page_number": 1, "text": "teaser"},
    {"headline": "Siri jumps on AI bandwagon in more powerful upgrade", "page_number": 7, "text": "y" * 600},
    {"headline": "Maruti to invest ₹925 crore in green energy", "page_number": 4, "text": "z" * 300},
]
mark_duplicates(arts)
for a in arts:
    print(f"  p{a['page_number']} dup={a['is_duplicate']!s:5} of={a['duplicate_of']}  {a['headline'][:44]}")
