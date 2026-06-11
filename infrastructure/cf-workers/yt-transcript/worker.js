/**
 * RIG YouTube Transcript Proxy
 * Runs on Cloudflare edge IPs (not flagged by YouTube).
 * Hetzner calls this; we fetch the watch page, extract captions, return JSON.
 *
 * GET /?video_id=<id>&lang=en&key=<API_KEY>
 *
 * Responses:
 *   200 { video_id, language, is_auto, segments: [{start, dur, text}] }
 *   400 { error: "invalid_video_id" }
 *   401 { error: "unauthorized" }
 *   404 { error: "no_captions", available_languages: [...] }
 *   502 { error: "youtube_wall" | "parse_failed" | "caption_fetch_failed" }
 */

// Bypass YouTube's GDPR consent wall — sets region acceptance cookie
const CONSENT_COOKIE = "CONSENT=YES+cb.20210328-17-p0.en+FX+667; SOCS=CAISEwgDEgk";

const WATCH_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  "Accept-Language": "en-US,en;q=0.9",
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  Cookie: CONSENT_COOKIE,
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === "/health") {
      return Response.json({ status: "ok" });
    }

    // RSS discovery — fetch channel feed from CF edge (keeps Hetzner IP clean)
    if (url.pathname === "/discover") {
      const key = url.searchParams.get("key");
      if ((env.API_KEY || "").trim() && key !== (env.API_KEY || "").trim()) {
        return Response.json({ error: "unauthorized" }, { status: 401 });
      }
      const channelId = url.searchParams.get("channel_id");
      if (!channelId || !/^UC[a-zA-Z0-9_-]{22}$/.test(channelId)) {
        return Response.json({ error: "invalid_channel_id" }, { status: 400 });
      }
      let feedResp = await fetch(
        `https://www.youtube.com/feeds/videos.xml?channel_id=${channelId}`,
        { headers: { "User-Agent": "Mozilla/5.0 (compatible; RIG/1.0)" } }
      );
      // Fallback to the public feedburner-style host if the primary 404s
      if (feedResp.status === 404) {
        feedResp = await fetch(
          `https://www.youtube.com/feeds/videos.xml?channel_id=${channelId}`,
          { headers: { "User-Agent": WATCH_HEADERS["User-Agent"], "Accept": "application/atom+xml,text/xml,*/*" } }
        );
      }
      if (!feedResp.ok) {
        return Response.json({ error: "rss_failed", http_status: feedResp.status }, { status: 502 });
      }
      const xml = await feedResp.text();
      const channelName = (xml.match(/<title>([^<]+)<\/title>/) || [])[1] || null;
      const videos = [];
      const entryRe = /<entry>([\s\S]*?)<\/entry>/g;
      let m;
      while ((m = entryRe.exec(xml)) !== null) {
        const block = m[1];
        const vid = (block.match(/<yt:videoId>([^<]+)<\/yt:videoId>/) || [])[1];
        const title = (block.match(/<title>([^<]+)<\/title>/) || [])[1];
        const published = (block.match(/<published>([^<]+)<\/published>/) || [])[1];
        if (vid) videos.push({ video_id: vid, title, published });
      }
      return Response.json({ channel_id: channelId, channel_name: channelName, count: videos.length, videos });
    }

    // Auth — compare against API_KEY secret set via `wrangler secret put API_KEY`
    const key = url.searchParams.get("key") || request.headers.get("x-api-key");
    const expectedKey = (env.API_KEY || "").trim();
    if (expectedKey && key !== expectedKey) {
      return Response.json({ error: "unauthorized" }, { status: 401 });
    }

    const videoId = url.searchParams.get("video_id");
    if (!videoId || !/^[a-zA-Z0-9_-]{11}$/.test(videoId)) {
      return Response.json({ error: "invalid_video_id" }, { status: 400 });
    }

    // Debug: probe many client variants in one request, report each result.
    if (url.searchParams.get("strategy") === "debug") {
      const out = await debugAllClients(videoId);
      return Response.json(out);
    }

    const preferredLang = url.searchParams.get("lang") || "en";
    const strategy = url.searchParams.get("strategy") || "auto";

    try {
      // ── Step 1+2: obtain playerResponse via innertube (primary) or HTML ───
      const potOpts = {
        poToken: url.searchParams.get("pot") || "",
        visitorData: url.searchParams.get("visitor") || "",
      };
      const { playerResponse, source, error: peError, raw } =
        await getPlayerResponse(videoId, strategy, potOpts);

      if (!playerResponse) {
        return Response.json(
          { error: peError || "parse_failed", detail: "could not obtain player response", raw: raw || undefined },
          { status: 502 }
        );
      }

      // Playability gate — surfaces login/bot walls explicitly
      const status = playerResponse?.playabilityStatus?.status;
      if (status && status !== "OK") {
        const reason =
          playerResponse?.playabilityStatus?.reason ||
          playerResponse?.playabilityStatus?.errorScreen?.playerErrorMessageRenderer
            ?.reason?.simpleText ||
          "";
        if (
          /sign in|bot|not a bot|confirm/i.test(reason) ||
          status === "LOGIN_REQUIRED"
        ) {
          return Response.json(
            { error: "youtube_wall", status, reason, source },
            { status: 502 }
          );
        }
        return Response.json(
          { error: "not_playable", status, reason, source },
          { status: 502 }
        );
      }

      // ── Step 3: get caption tracks ────────────────────────────────────────
      const tracks =
        playerResponse?.captions?.playerCaptionsTracklistRenderer?.captionTracks ?? [];

      if (!tracks.length) {
        // Return video metadata so caller knows what we did get
        const videoDetails = playerResponse?.videoDetails ?? {};
        return Response.json(
          {
            error: "no_captions",
            video_id: videoId,
            title: videoDetails.title ?? null,
            channel: videoDetails.author ?? null,
          },
          { status: 404 }
        );
      }

      // Pick best language: exact match → any English variant → first track
      const track =
        tracks.find((t) => t.languageCode === preferredLang) ??
        tracks.find((t) => (t.languageCode ?? "").startsWith("en")) ??
        tracks[0];

      const availableLanguages = tracks.map((t) => ({
        code: t.languageCode,
        name: t.name?.simpleText ?? "",
        auto: !!t.kind,
      }));

      // ── Step 4: fetch caption data (json3 format) ─────────────────────────
      const captionUrl = `${track.baseUrl}&fmt=json3&xorb=2&xobt=3&xovt=3`;
      const captionResp = await fetch(captionUrl, {
        headers: { "User-Agent": WATCH_HEADERS["User-Agent"] },
      });

      if (!captionResp.ok) {
        return Response.json(
          { error: "caption_fetch_failed", http_status: captionResp.status },
          { status: 502 }
        );
      }

      const captionData = await captionResp.json();

      // ── Step 5: convert to clean segment array ────────────────────────────
      const segments = (captionData.events ?? [])
        .filter((e) => e.segs && e.tStartMs != null)
        .map((e) => ({
          start: e.tStartMs / 1000,
          dur: (e.dDurationMs ?? 0) / 1000,
          text: e.segs
            .map((s) => s.utf8 ?? "")
            .join("")
            .replace(/\n/g, " ")
            .trim(),
        }))
        .filter((s) => s.text.length > 0);

      const videoDetails = playerResponse?.videoDetails ?? {};

      return Response.json({
        video_id: videoId,
        source,
        title: videoDetails.title ?? null,
        channel: videoDetails.author ?? null,
        duration_s: parseInt(videoDetails.lengthSeconds ?? "0", 10),
        language: track.languageCode,
        language_name: track.name?.simpleText ?? "",
        is_auto: !!track.kind,
        available_languages: availableLanguages,
        segment_count: segments.length,
        segments,
      });
    } catch (err) {
      return Response.json(
        { error: "internal", detail: String(err) },
        { status: 500 }
      );
    }
  },
};

// ── Player-response acquisition ────────────────────────────────────────────

const SLEEP = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Innertube client contexts. ANDROID is most robust: it does NOT hit the
 * consent wall, often does not require a PO token for captions, and uses
 * a lightweight JSON endpoint instead of the heavy watch-page HTML.
 */
const CLIENTS = {
  ANDROID: {
    clientName: "ANDROID",
    clientVersion: "19.09.37",
    androidSdkVersion: 30,
    userAgent: "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
    clientNameId: "3",
  },
  IOS: {
    clientName: "IOS",
    clientVersion: "19.09.3",
    userAgent: "com.google.ios.youtube/19.09.3 (iPhone14,3; U; CPU iOS 15_6 like Mac OS X)",
    clientNameId: "5",
  },
  WEB: {
    clientName: "WEB",
    clientVersion: "2.20240101",
    userAgent: WATCH_HEADERS["User-Agent"],
    clientNameId: "1",
  },
  // TV embedded — historically the most block-resistant, no PO token needed
  TVHTML5: {
    clientName: "TVHTML5_SIMPLY_EMBEDDED_PLAYER",
    clientVersion: "2.0",
    userAgent:
      "Mozilla/5.0 (PlayStation; PlayStation 4/12.00) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    clientNameId: "85",
  },
};

const INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";

/**
 * Try to obtain a YouTube player response.
 * strategy: "auto" (android→ios→html), "android", "ios", "web", "html".
 * Retries once on 429 with backoff.
 */
async function getPlayerResponse(videoId, strategy, potOpts) {
  // PO-token path takes precedence when a token is supplied.
  if (potOpts && potOpts.poToken && potOpts.visitorData) {
    const res = await fetchViaWebPot(videoId, potOpts.poToken, potOpts.visitorData);
    if (res.playerResponse) return { playerResponse: res.playerResponse, source: "web_pot" };
    // fall through to clientless attempts if the token failed
    if (strategy === "web_pot") {
      return { playerResponse: null, error: res.error || "webpot_failed", raw: res.raw };
    }
  }

  const order =
    strategy === "android" ? ["ANDROID"]
    : strategy === "ios" ? ["IOS"]
    : strategy === "web" ? ["WEB"]
    : strategy === "tv" ? ["TVHTML5"]
    : strategy === "html" ? ["HTML"]
    : ["TVHTML5", "ANDROID", "IOS", "HTML"];

  let lastError = "all_failed";
  let lastRaw = "";

  for (const client of order) {
    for (let attempt = 0; attempt < 2; attempt++) {
      const res =
        client === "HTML"
          ? await fetchViaHtml(videoId)
          : await fetchViaInnertube(videoId, CLIENTS[client]);

      if (res.playerResponse) {
        return { playerResponse: res.playerResponse, source: client.toLowerCase() };
      }
      lastError = res.error || lastError;
      if (res.raw) lastRaw = res.raw;
      if (res.http === 429) {
        await SLEEP(1500 * (attempt + 1)); // backoff then retry same client
        continue;
      }
      break; // non-429 → move to next client
    }
  }
  return { playerResponse: null, error: lastError, raw: lastRaw };
}

// Current (2026) client variants to probe. Each entry = full innertube body.
const DEBUG_VARIANTS = [
  {
    label: "ANDROID_20",
    headers: { "X-YouTube-Client-Name": "3", "X-YouTube-Client-Version": "20.10.38",
      "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip" },
    body: { videoId: "%VID%", context: { client: { clientName: "ANDROID", clientVersion: "20.10.38", androidSdkVersion: 34, hl: "en", gl: "US" } }, params: "CgIQBg" },
  },
  {
    label: "ANDROID_VR",
    headers: { "X-YouTube-Client-Name": "28", "X-YouTube-Client-Version": "1.60.19",
      "User-Agent": "com.google.android.apps.youtube.vr.oculus/1.60.19 (Linux; U; Android 12L; eureka-user) gzip" },
    body: { videoId: "%VID%", context: { client: { clientName: "ANDROID_VR", clientVersion: "1.60.19", androidSdkVersion: 32, hl: "en", gl: "US" } } },
  },
  {
    label: "IOS_20",
    headers: { "X-YouTube-Client-Name": "5", "X-YouTube-Client-Version": "20.10.4",
      "User-Agent": "com.google.ios.youtube/20.10.4 (iPhone16,2; U; CPU iOS 18_3 like Mac OS X)" },
    body: { videoId: "%VID%", context: { client: { clientName: "IOS", clientVersion: "20.10.4", deviceModel: "iPhone16,2", hl: "en", gl: "US" } } },
  },
  {
    label: "MWEB",
    headers: { "X-YouTube-Client-Name": "2", "X-YouTube-Client-Version": "2.20250101.00.00",
      "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1" },
    body: { videoId: "%VID%", context: { client: { clientName: "MWEB", clientVersion: "2.20250101.00.00", hl: "en", gl: "US" } } },
  },
  {
    label: "TVHTML5_new",
    headers: { "X-YouTube-Client-Name": "7", "X-YouTube-Client-Version": "7.20250101.00.00",
      "User-Agent": "Mozilla/5.0 (ChromiumStylePlatform) Cobalt/Version" },
    body: { videoId: "%VID%", context: { client: { clientName: "TVHTML5", clientVersion: "7.20250101.00.00", hl: "en", gl: "US" } } },
  },
];

async function debugAllClients(videoId) {
  const results = [];
  for (const v of DEBUG_VARIANTS) {
    try {
      const resp = await fetch(
        `https://www.youtube.com/youtubei/v1/player?key=${INNERTUBE_KEY}&prettyPrint=false`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Cookie: CONSENT_COOKIE, ...v.headers },
          body: JSON.stringify(v.body).replace(/%VID%/g, videoId),
        }
      );
      const http = resp.status;
      let status = null, reason = null, caps = 0, errMsg = null;
      if (resp.ok) {
        const j = await resp.json();
        status = j?.playabilityStatus?.status ?? null;
        reason = j?.playabilityStatus?.reason ?? null;
        caps = (j?.captions?.playerCaptionsTracklistRenderer?.captionTracks ?? []).length;
      } else {
        errMsg = (await resp.text()).slice(0, 120);
      }
      results.push({ client: v.label, http, status, reason, caption_tracks: caps, err: errMsg });
    } catch (e) {
      results.push({ client: v.label, error: String(e).slice(0, 80) });
    }
    await SLEEP(800);
  }
  return { video_id: videoId, results };
}

/**
 * WEB innertube player call with a PO token + visitorData. This is the
 * documented path to clear LOGIN_REQUIRED ("confirm you're not a bot").
 */
async function fetchViaWebPot(videoId, poToken, visitorData) {
  try {
    const resp = await fetch(
      `https://www.youtube.com/youtubei/v1/player?key=${INNERTUBE_KEY}&prettyPrint=false`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "User-Agent": WATCH_HEADERS["User-Agent"],
          "X-YouTube-Client-Name": "1",
          "X-YouTube-Client-Version": "2.20240101.00.00",
          "X-Goog-Visitor-Id": visitorData,
          Cookie: CONSENT_COOKIE,
        },
        body: JSON.stringify({
          videoId,
          context: {
            client: {
              clientName: "WEB",
              clientVersion: "2.20240101.00.00",
              visitorData,
              hl: "en",
              gl: "US",
            },
          },
          serviceIntegrityDimensions: { poToken },
        }),
      }
    );
    if (!resp.ok) {
      const raw = (await resp.text()).slice(0, 200);
      return { playerResponse: null, http: resp.status, error: `webpot_${resp.status}`, raw };
    }
    return { playerResponse: await resp.json() };
  } catch (e) {
    return { playerResponse: null, error: `webpot_exc:${String(e).slice(0, 60)}` };
  }
}

async function fetchViaInnertube(videoId, client) {
  try {
    const resp = await fetch(
      `https://www.youtube.com/youtubei/v1/player?key=${INNERTUBE_KEY}&prettyPrint=false`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "User-Agent": client.userAgent,
          "X-YouTube-Client-Name": client.clientNameId,
          "X-YouTube-Client-Version": client.clientVersion,
          Cookie: CONSENT_COOKIE,
        },
        body: JSON.stringify({
          videoId,
          context: {
            client: {
              clientName: client.clientName,
              clientVersion: client.clientVersion,
              androidSdkVersion: client.androidSdkVersion,
              hl: "en",
              gl: "US",
            },
          },
        }),
      }
    );
    if (!resp.ok) {
      const errBody = (await resp.text()).slice(0, 300);
      return { playerResponse: null, http: resp.status, error: `innertube_${resp.status}`, raw: errBody };
    }
    const json = await resp.json();
    return { playerResponse: json };
  } catch (e) {
    return { playerResponse: null, error: `innertube_exc:${String(e).slice(0, 60)}` };
  }
}

async function fetchViaHtml(videoId) {
  try {
    const resp = await fetch(
      `https://www.youtube.com/watch?v=${videoId}&hl=en&gl=US`,
      { headers: WATCH_HEADERS }
    );
    if (!resp.ok) return { playerResponse: null, http: resp.status, error: `html_${resp.status}` };
    const html = await resp.text();
    if (
      html.includes("consent.youtube.com") ||
      html.toLowerCase().includes("sign in to confirm")
    ) {
      return { playerResponse: null, error: "html_wall" };
    }
    const pr = extractPlayerResponse(html);
    return pr ? { playerResponse: pr } : { playerResponse: null, error: "html_parse_failed" };
  } catch (e) {
    return { playerResponse: null, error: `html_exc:${String(e).slice(0, 60)}` };
  }
}

/**
 * Extract and parse ytInitialPlayerResponse from a YouTube watch page.
 * Uses bracket counting to handle the large nested JSON without regex limits.
 */
function extractPlayerResponse(html) {
  const marker = "ytInitialPlayerResponse = ";
  const start = html.indexOf(marker);
  if (start === -1) return null;

  const jsonStart = start + marker.length;
  if (html[jsonStart] !== "{") return null;

  let depth = 0;
  let i = jsonStart;
  for (; i < html.length; i++) {
    if (html[i] === "{") depth++;
    else if (html[i] === "}") {
      depth--;
      if (depth === 0) break;
    }
  }

  try {
    return JSON.parse(html.slice(jsonStart, i + 1));
  } catch {
    return null;
  }
}
