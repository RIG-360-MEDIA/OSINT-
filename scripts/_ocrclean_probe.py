"""Probe v3: Vision-corroborated ₹ repair + merged-word split. Must be SAFE."""
import re
import wordsegment
wordsegment.load()
_UNI = wordsegment.UNIGRAMS

_WORD = re.compile(r"[A-Za-z0-9ऀ-ൿ]+")
_STOP = {"is", "of", "in", "to", "a", "an", "the", "and", "on", "at", "for", "as", "by", "its"}
# ₹ look-alike glyphs directly before a lakh/crore/cr amount.
_RUPEE_LOOKALIKE = re.compile(r"[\$%₨](?=\s*[\d.,]+\s*(?:lakh|crore|cr)\b)", re.I)
# A number before lakh/crore/cr whose leading digit may be a merged ₹ glyph.
_MERGED_RUPEE = re.compile(r"(?<![\d.])(\d)([\d,]*\d)(?=\s*(?:lakh|crore|cr)\b)", re.I)


def _toks(t):
    return {w.lower() for w in _WORD.findall(t) if len(w) >= 3}


def _rupee_amounts(text):
    out = set()
    for m in re.finditer(r"(?:₹|Rs\.?)\s*([\d,]+(?:\.\d+)?)", text):
        out.add(m.group(1).replace(",", ""))
    return out


def _fix_rupee(text, amounts):
    text = _RUPEE_LOOKALIKE.sub("₹", text)
    if amounts:
        def repl(m):
            lead, rest = m.group(1), m.group(2)
            if (lead + rest).replace(",", "") in amounts:
                return m.group(0)                      # whole number is genuine
            if rest.replace(",", "") in amounts:       # strip merged ₹ glyph
                return "₹" + rest
            return m.group(0)
        text = _MERGED_RUPEE.sub(repl, text)
    return text


def _recase(raw, parts):
    if raw.isupper():
        return " ".join(p.upper() for p in parts)
    if raw[:1].isupper():
        return " ".join(p.capitalize() for p in parts)
    return " ".join(parts)


def _split_merged(token, vocab):
    low = token.lower()
    if not low.isalpha() or len(low) < 7 or low in _UNI:
        return token
    parts = wordsegment.segment(low)
    if len(parts) < 2:
        return token
    ok = all(p in _STOP or p in vocab or (len(p) >= 3 and p in _UNI) for p in parts)
    anchor = any(len(p) >= 4 and p in vocab for p in parts)
    # Pure-dictionary fallback for lowercase merges Vision didn't mention.
    dict_ok = (
        low == token and len(low) >= 9
        and all(len(p) >= 3 and p in _UNI for p in parts)
    )
    if (ok and anchor) or dict_ok:
        return _recase(token, parts)
    return token


def clean(text, vision=""):
    vocab = _toks(vision)
    amounts = _rupee_amounts(vision)
    text = _fix_rupee(text, amounts)
    return " ".join(_split_merged(w, vocab) for w in text.split())


print("== ₹ merge (Adani: vision has ₹3,050) ==")
print(" ", clean("for 23,050 crore, a move", "Adani to buy IntelliSmart for ₹3,050 cr"))
print("== ₹ merge with NO corroboration (must stay 23,050) ==")
print(" ", clean("revenue of 23,050 crore", "Company posts strong quarter"))
print("== $ lakh/crore ==")
print(" ", clean("bill to $3.4 lakh crore and $1.23 lakh crore", "subsidy"))
print("== genuine USD (must stay $) ==")
print(" ", clean("services of $64.6 billion", "x"))

print("== uppercase merge (vision: 'Kia India is preparing two-pronged') ==")
print(" ", clean("KIAINDIAIS preparing a two-pronged SUV",
                 "Kia India is preparing a two-pronged SUV offensive"))
print("== DANGER uppercase proper nouns (must NOT split) ==")
for tok, vis in [("DELHI", "New Delhi report"), ("MUMBAI", "from Mumbai"),
                 ("CHANDRASEKARAN", "N Chandrasekaran said"),
                 ("INTELLISMART", "acquire IntelliSmart Infrastructure"),
                 ("ARTIFICIAL", "Artificial Intelligence could"),
                 ("CONSULTANCY", "Tata Consultancy Services")]:
    print(f"  {tok:16} -> {clean(tok, vis)!r}")
print("== lowercase dict merges (no vision) ==")
for tok in ["digitalassistant", "quickcommerce", "smartmetering"]:
    print(f"  {tok:16} -> {clean(tok)!r}")
