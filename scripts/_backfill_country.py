"""Backfill sources.country for country='XX' rows.

Priority: domain override > ccTLD > unambiguous language. Runs on the Hetzner
host, talks to the DB via `docker exec rig-postgres psql`. Reversible: only
touches rows currently 'XX'; a pre-run snapshot of (id, country) is written.
"""
from __future__ import annotations

import subprocess

# ── generic TLDs that are NOT a reliable country signal ──────────────────────
GENERIC_TLDS = {
    "com", "net", "org", "info", "io", "me", "tv", "cc", "co", "fm", "ai",
    "gg", "to", "ws", "app", "dev", "xyz", "biz", "tech", "online", "site",
    "news", "live", "blog", "media", "one", "world", "today", "press",
    "space", "email", "link", "club", "store", "shop",
}
CCTLD_FIX = {"uk": "GB", "su": "RU"}  # ccTLD != ISO code

# ── unambiguous language → country (skip en/es/pt/ar/fr/de — ambiguous) ───────
LANG_CC = {
    "fa": "IR", "tr": "TR", "ur": "PK", "bn": "BD", "cnr": "ME", "sr": "RS",
    "uk": "UA", "bg": "BG", "ne": "NP", "ja": "JP", "ko": "KR", "th": "TH",
    "vi": "VN", "id": "ID", "tl": "PH", "el": "GR", "he": "IL", "hu": "HU",
    "cs": "CZ", "sk": "SK", "pl": "PL", "ro": "RO", "nl": "NL", "sv": "SE",
    "no": "NO", "nb": "NO", "fi": "FI", "da": "DK", "hr": "HR", "sl": "SI",
    "lt": "LT", "lv": "LV", "et": "EE", "is": "IS", "ka": "GE", "hy": "AM",
    "az": "AZ", "kk": "KZ", "uz": "UZ", "sq": "AL", "mk": "MK", "si": "LK",
    "my": "MM", "km": "KH", "lo": "LA", "am": "ET", "sw": "KE", "ru": "RU",
    "de": "DE",
    # Indian languages
    "te": "IN", "hi": "IN", "ta": "IN", "ml": "IN", "kn": "IN", "mr": "IN",
    "gu": "IN", "pa": "IN", "or": "IN", "as": "IN",
}

# ── domain substring → country (overrides everything; for generic-TLD majors) ─
DOMAIN_CC = {
    "sports.yahoo.com": "US", "uk.news.yahoo.com": "GB", "news.yahoo.com": "US",
    "infobae.com": "AR", "clarin.com": "AR", "perfil.com": "AR",
    "elintransigente.com": "AR", "lanacion.com": "AR", "pagina12": "AR",
    "okdiario.com": "ES", "elmundo.es": "ES", "elpais.com": "ES",
    "elcolombiano.com": "CO", "eltiempo.com": "CO", "semana.com": "CO",
    "cibercuba.com": "CU", "globo.com": "BR", "uol.com.br": "BR",
    "folha": "BR", "estadao": "BR", "investing.com": "US",
    "seekingalpha.com": "US", "financialpost.com": "CA", "bringatrailer.com": "US",
    "freemalaysiatoday.com": "MY", "sundayguardianlive.com": "IN",
    "arynews.tv": "PK", "hespress.com": "MA", "jordanzad.com": "JO",
    "senego.com": "SN", "inquirer.net": "PH", "okezone.com": "ID",
    "onlinekhabar.com": "NP", "naslovi.net": "RS", "unian.net": "UA",
    "actualno.com": "BG", "mehrnews.com": "IR", "asriran.com": "IR",
    "urdupoint.com": "PK", "jagonews24.com": "BD", "prothomalo.com": "BD",
    "haberler.com": "TR", "haber7.com": "TR", "sporx.com": "TR",
    "stargazete.com": "TR", "handelsblatt.com": "DE", "faz.net": "DE",
    "tt.com": "AT", "nikkansports.com": "JP",
}


def psql(sql: str) -> str:
    out = subprocess.run(
        ["docker", "exec", "rig-postgres", "psql", "-U", "rig", "-d", "rig",
         "-tA", "-F", "\t", "-c", sql],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def derive(domain: str, language: str) -> str | None:
    d = (domain or "").lower().strip()
    lang = (language or "").lower().strip()
    # 1. domain override
    for needle, cc in DOMAIN_CC.items():
        if needle in d:
            return cc
    # 2. ccTLD
    if "." in d:
        tld = d.rsplit(".", 1)[-1]
        if len(tld) == 2 and tld.isalpha() and tld not in GENERIC_TLDS:
            return CCTLD_FIX.get(tld, tld.upper())
    # 3. unambiguous language
    return LANG_CC.get(lang)


def main() -> None:
    rows = [r for r in psql(
        "SELECT id, COALESCE(domain,''), COALESCE(language,'') "
        "FROM sources WHERE country='XX'"
    ).splitlines() if r.strip()]

    updates: list[tuple[str, str]] = []
    for line in rows:
        sid, domain, language = (line.split("\t") + ["", ""])[:3]
        cc = derive(domain, language)
        if cc:
            updates.append((sid, cc))

    print(f"XX sources read: {len(rows)}")
    print(f"derivable: {len(updates)}  |  remaining XX: {len(rows) - len(updates)}")

    if not updates:
        return

    # snapshot for reversibility
    with open("/tmp/country_backfill_snapshot.tsv", "w") as f:
        for sid, _ in updates:
            f.write(sid + "\n")
    print("snapshot of changed ids: /tmp/country_backfill_snapshot.tsv")

    values = ",".join(f"('{sid}'::uuid,'{cc}')" for sid, cc in updates)
    psql(
        f"UPDATE sources s SET country = v.cc "
        f"FROM (VALUES {values}) AS v(id, cc) "
        f"WHERE s.id = v.id AND s.country='XX'"
    )
    print(f"updated: {len(updates)} sources")


if __name__ == "__main__":
    main()
