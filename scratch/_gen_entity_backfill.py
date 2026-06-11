import uuid

# (iso2, canonical, [aliases incl canonical]) — factual names/long-forms only, no demonyms
DATA = [
    ("AG", "Antigua and Barbuda", ["Antigua and Barbuda", "Antigua"]),
    ("BS", "Bahamas", ["Bahamas", "The Bahamas"]),
    ("BB", "Barbados", ["Barbados"]),
    ("BZ", "Belize", ["Belize"]),
    ("BW", "Botswana", ["Botswana", "Republic of Botswana"]),
    ("BN", "Brunei", ["Brunei", "Brunei Darussalam"]),
    ("DM", "Dominica", ["Dominica", "Commonwealth of Dominica"]),
    ("FJ", "Fiji", ["Fiji", "Republic of Fiji"]),
    ("GA", "Gabon", ["Gabon", "Gabonese Republic"]),
    ("GM", "Gambia", ["Gambia", "The Gambia"]),
    ("GD", "Grenada", ["Grenada"]),
    ("GY", "Guyana", ["Guyana"]),
    ("KI", "Kiribati", ["Kiribati"]),
    ("LS", "Lesotho", ["Lesotho", "Kingdom of Lesotho"]),
    ("MV", "Maldives", ["Maldives", "Republic of Maldives"]),
    ("MT", "Malta", ["Malta", "Republic of Malta"]),
    ("MU", "Mauritius", ["Mauritius", "Republic of Mauritius"]),
    ("NR", "Nauru", ["Nauru", "Republic of Nauru"]),
    ("KN", "Saint Kitts and Nevis", ["Saint Kitts and Nevis", "St Kitts and Nevis", "St. Kitts and Nevis", "Saint Kitts"]),
    ("LC", "Saint Lucia", ["Saint Lucia", "St Lucia", "St. Lucia"]),
    ("VC", "Saint Vincent and the Grenadines", ["Saint Vincent and the Grenadines", "St Vincent and the Grenadines", "Saint Vincent"]),
    ("WS", "Samoa", ["Samoa"]),
    ("SC", "Seychelles", ["Seychelles", "Republic of Seychelles"]),
    ("SB", "Solomon Islands", ["Solomon Islands"]),
    ("TO", "Tonga", ["Tonga", "Kingdom of Tonga"]),
    ("TT", "Trinidad and Tobago", ["Trinidad and Tobago", "Trinidad"]),
    ("TV", "Tuvalu", ["Tuvalu"]),
]
assert len(DATA) == 27, len(DATA)


def q(s):
    return "'" + str(s).replace("'", "''") + "'"


dict_rows, alias_pairs = [], []
for iso, canon, aliases in DATA:
    arr = "ARRAY[" + ",".join(q(a) for a in aliases) + "]"
    dict_rows.append(f"({q(str(uuid.uuid4()))},{q(canon)},'location',{arr},{q(iso)},'seed:commonwealth_v1')")
    for a in aliases:
        alias_pairs.append(f"({q(canon)},{q(a)})")

canon_lower = ",".join(q(c.lower()) for _, c, _ in DATA)
sql = (
    "\\set ON_ERROR_STOP on\nBEGIN;\n"
    "INSERT INTO entity_dictionary (id,canonical_name,entity_type,aliases,country,source) VALUES\n"
    + ",\n".join(dict_rows) + "\nON CONFLICT (canonical_name) DO NOTHING;\n\n"
    "INSERT INTO entity_lookup (name_norm, entity_id)\n"
    "SELECT lower(v.alias), ed.id FROM (VALUES\n"
    + ",\n".join(alias_pairs) + "\n) v(canonical,alias) JOIN entity_dictionary ed ON ed.canonical_name=v.canonical\n"
    "ON CONFLICT (name_norm) DO NOTHING;\nCOMMIT;\n\n"
    "\\echo '### verify: dict rows added + how many of the 27 now resolve in entity_lookup'\n"
    "SELECT count(*) commonwealth_dict_rows FROM entity_dictionary WHERE source='seed:commonwealth_v1';\n"
    f"WITH n(nm) AS (VALUES ({canon_lower.replace(',', '),(')})) "
    "SELECT count(*) total, count(*) FILTER (WHERE EXISTS(SELECT 1 FROM entity_lookup el WHERE el.name_norm=n.nm)) resolves FROM n;\n"
)
with open(r"C:\Users\Dell\Desktop\rig-surveillance\scratch\_entity_backfill.sql", "w", encoding="utf-8") as f:
    f.write(sql)
print("wrote _entity_backfill.sql:", len(dict_rows), "dict rows,", len(alias_pairs), "lookup aliases")
