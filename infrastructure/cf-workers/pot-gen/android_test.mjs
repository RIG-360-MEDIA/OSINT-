/**
 * Test the ANDROID innertube client (NO PO token) directly from this machine's
 * residential IP, on the videos that bot-walled from Cloudflare.
 *
 * If V6 returns captions here, the whole solution is just "residential IP +
 * ANDROID client" — no PO token, no WEB client, no proxy.
 *
 * Usage: node android_test.mjs
 */
const INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";

const VIDEOS = [
  ["Rick (control)", "dQw4w9WgXcQ"],
  ["V6 News (CF-walled)", "a7J4tyqD2cA"],
];

async function androidPlayer(videoId) {
  const resp = await fetch(
    `https://www.youtube.com/youtubei/v1/player?key=${INNERTUBE_KEY}&prettyPrint=false`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip",
        "X-YouTube-Client-Name": "3",
        "X-YouTube-Client-Version": "20.10.38",
      },
      body: JSON.stringify({
        videoId,
        context: {
          client: {
            clientName: "ANDROID",
            clientVersion: "20.10.38",
            androidSdkVersion: 34,
            hl: "en",
            gl: "US",
          },
        },
      }),
    }
  );
  const j = await resp.json();
  const status = j?.playabilityStatus?.status;
  const reason = j?.playabilityStatus?.reason || "";
  const tracks = j?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
  return { status, reason, caps: tracks.length, tracks };
}

async function fetchCaptionText(track) {
  // Pull the actual transcript to prove end-to-end works from residential.
  // Try json3 first; fall back to parsing the default timedtext XML.
  const url = `${track.baseUrl}&fmt=json3`;
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!r.ok) return `(caption fetch HTTP ${r.status})`;
  const body = await r.text();
  let text;
  if (body.trimStart().startsWith("{")) {
    const j = JSON.parse(body);
    text = (j.events || [])
      .filter((e) => e.segs)
      .map((e) => e.segs.map((s) => s.utf8 || "").join(""))
      .join(" ");
  } else {
    // timedtext XML: <text start="..." dur="...">escaped text</text>
    text = [...body.matchAll(/<text[^>]*>([\s\S]*?)<\/text>/g)]
      .map((m) =>
        m[1]
          .replace(/&amp;#39;/g, "'")
          .replace(/&amp;quot;/g, '"')
          .replace(/&#39;/g, "'")
          .replace(/&quot;/g, '"')
          .replace(/&amp;/g, "&")
          .replace(/&lt;/g, "<")
          .replace(/&gt;/g, ">")
      )
      .join(" ");
  }
  return text.replace(/\s+/g, " ").trim().slice(0, 160);
}

async function main() {
  console.log("ANDROID client, no PO token, from THIS residential IP:\n");
  for (const [label, vid] of VIDEOS) {
    try {
      const r = await androidPlayer(vid);
      const mark = r.caps > 0 ? "OK " : "BLK";
      console.log(`  [${mark}] ${label.padEnd(22)} status=${r.status} caps=${r.caps}  ${r.reason}`);
      if (r.caps > 0) {
        const langs = r.tracks.map((t) => t.languageCode).join(",");
        console.log(`        languages: ${langs}`);
        const sample = await fetchCaptionText(r.tracks[0]);
        console.log(`        transcript sample: ${JSON.stringify(sample)}`);
      }
    } catch (e) {
      console.log(`  [ERR] ${label}  ${String(e).slice(0, 80)}`);
    }
  }
}

main().catch((e) => {
  console.error("ERR:", e?.stack || String(e));
  process.exit(1);
});
