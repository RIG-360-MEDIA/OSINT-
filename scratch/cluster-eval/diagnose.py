p = r"sample.json"
with open(p, "rb") as f:
    data = f.read()
print(f"Total bytes: {len(data)}")
print("Context around char 72413:")
print(repr(data[72350:72500]))
print()
cr = data.count(b"\r"); lf = data.count(b"\n"); tab = data.count(b"\t")
print(f"CR (0x0d): {cr}")
print(f"LF (0x0a): {lf}")
print(f"Tab (0x09): {tab}")

# Try to parse and show exact position
import json
try:
    json.loads(data.decode("utf-8"))
    print("Parses OK")
except json.JSONDecodeError as e:
    print(f"Error at pos {e.pos}: {e.msg}")
    s = data.decode("utf-8", errors="replace")
    start = max(0, e.pos - 60)
    end = min(len(s), e.pos + 60)
    print("Context:")
    print(repr(s[start:end]))
