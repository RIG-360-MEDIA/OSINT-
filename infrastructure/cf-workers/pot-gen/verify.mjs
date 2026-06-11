/**
 * Diagnostic: mint a PO token, then immediately run the WEB+PoToken player
 * request DIRECTLY from this machine (residential IP) against test videos.
 *
 * Purpose: determine whether a token minted here is valid at all, and whether
 * the cold PO token is IP-bound (works from the minting IP) — which decides
 * whether Option C (mint laptop, fetch from Cloudflare) can ever work.
 *
 * Usage: node verify.mjs
 */
import { BG } from "bgutils-js";
import { JSDOM } from "jsdom";

const INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";
const REQUEST_KEY = "O43z0dpjhgX20SCx4KAo";
const CLIENT_VERSION = "2.20250601.01.00";

const VIDEOS = [
  ["V6 News (was walled)", "a7J4tyqD2cA"],
  ["Rick (control)", "dQw4w9WgXcQ"],
];

async function getVisitorData() {
  const resp = await fetch(
    `https://www.youtube.com/youtubei/v1/visitor_id?key=${INNERTUBE_KEY}&prettyPrint=false`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        context: { client: { clientName: "WEB", clientVersion: CLIENT_VERSION, hl: "en", gl: "US" } },
      }),
    }
  );
  const json = await resp.json();
  let vd = json?.responseContext?.visitorData;
  if (!vd) {
    // Fallback: pull visitorData from the player request's first response.
    throw new Error("no visitorData: " + JSON.stringify(json).slice(0, 160));
  }
  return decodeURIComponent(vd);
}

async function mintToken(visitorData) {
  const dom = new JSDOM('<!DOCTYPE html><html lang="en"><body></body></html>', {
    url: "https://www.youtube.com/",
    referrer: "https://www.youtube.com/",
  });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    location: dom.window.location,
    origin: dom.window.origin,
  });
  const bgConfig = {
    fetch: (u, o) => fetch(u, o),
    globalObj: globalThis,
    identifier: visitorData,
    requestKey: REQUEST_KEY,
  };
  const challenge = await BG.Challenge.create(bgConfig);
  const js = challenge.interpreterJavascript.privateDoNotAccessOrElseSafeScriptWrappedValue;
  new Function(js)();
  const r = await BG.PoToken.generate({
    program: challenge.program,
    globalName: challenge.globalName,
    bgConfig,
  });
  return r.poToken;
}

async function playerRequest(videoId, visitorData, poToken) {
  const resp = await fetch(
    `https://www.youtube.com/youtubei/v1/player?key=${INNERTUBE_KEY}&prettyPrint=false`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "X-Goog-Visitor-Id": visitorData,
        "X-YouTube-Client-Name": "1",
        "X-YouTube-Client-Version": CLIENT_VERSION,
      },
      body: JSON.stringify({
        videoId,
        context: {
          client: {
            clientName: "WEB",
            clientVersion: CLIENT_VERSION,
            visitorData,
            hl: "en",
            gl: "US",
            userAgent:
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36,gzip(gfe)",
          },
        },
        playbackContext: {
          contentPlaybackContext: { html5Preference: "HTML5_PREF_WANTS" },
        },
        serviceIntegrityDimensions: { poToken },
        contentCheckOk: true,
        racyCheckOk: true,
      }),
    }
  );
  const j = await resp.json();
  const status = j?.playabilityStatus?.status;
  const reason = j?.playabilityStatus?.reason || "";
  const caps = (j?.captions?.playerCaptionsTracklistRenderer?.captionTracks || []).length;
  return { status, reason, caps };
}

async function main() {
  const visitorData = await getVisitorData();
  console.log("visitorData:", visitorData.slice(0, 40), "...");
  const poToken = await mintToken(visitorData);
  console.log("poToken:", poToken.slice(0, 40), "...\n");
  console.log("Running WEB+PoToken player requests DIRECTLY from this (residential) IP:\n");
  for (const [label, vid] of VIDEOS) {
    try {
      const r = await playerRequest(vid, visitorData, poToken);
      const mark = r.caps > 0 ? "OK " : "BLK";
      console.log(`  [${mark}] ${label.padEnd(24)} status=${r.status} caps=${r.caps}  ${r.reason}`);
    } catch (e) {
      console.log(`  [ERR] ${label}  ${String(e).slice(0, 80)}`);
    }
  }
}

main().catch((e) => {
  console.error("VERIFY_ERROR:", e?.stack || String(e));
  process.exit(1);
});
