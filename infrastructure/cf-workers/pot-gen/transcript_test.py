"""
Prove youtube-transcript-api works from this residential IP on the videos
that were blocked/walled from Hetzner and Cloudflare.

Run: python transcript_test.py
"""
import time

VIDEOS = [
    ("Rick (control)", "dQw4w9WgXcQ"),
    ("V6 News (was blocked)", "a7J4tyqD2cA"),
]


def main() -> None:
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    for label, vid in VIDEOS:
        time.sleep(2)
        try:
            # list available transcripts
            listing = api.list(vid)
            langs = [f"{t.language_code}{'(auto)' if t.is_generated else ''}" for t in listing]
            # fetch best available
            fetched = api.fetch(vid, languages=[l.split("(")[0] for l in langs] or ["en"])
            snippets = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
            text = " ".join(s["text"] for s in snippets[:6])
            print(f"  [OK ] {label:<24} langs={langs}")
            print(f"        {len(snippets)} segments; sample: {text[:140]!r}")
        except Exception as exc:
            print(f"  [ERR] {label:<24} {type(exc).__name__}: {str(exc)[:90]}")


if __name__ == "__main__":
    print("youtube-transcript-api from THIS residential IP:\n")
    main()
