/**
 * Mint a "cold" (logged-out) YouTube PO token bound to a fresh visitorData.
 * Runs locally on a residential IP. The token + visitorData are then handed
 * to the Cloudflare Worker's WEB innertube call to clear the LOGIN_REQUIRED
 * bot wall on videos that trip it (Option C validation).
 *
 * Output: a single JSON line { visitorData, poToken } to stdout.
 *
 * Usage:  node gen.mjs
 */
import { BG } from "bgutils-js";
import { JSDOM } from "jsdom";

const INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";
// BotGuard request key — public constant used by the web client.
const REQUEST_KEY = "O43z0dpjhgX20SCx4KAo";

async function getVisitorData() {
  const resp = await fetch(
    `https://www.youtube.com/youtubei/v1/visitor_id?key=${INNERTUBE_KEY}&prettyPrint=false`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        context: { client: { clientName: "WEB", clientVersion: "2.20240101.00.00", hl: "en", gl: "US" } },
      }),
    }
  );
  const json = await resp.json();
  const vd = json?.responseContext?.visitorData;
  if (!vd) throw new Error("could not obtain visitorData: " + JSON.stringify(json).slice(0, 200));
  // Canonicalize to the decoded form YouTube uses inside request bodies, so the
  // PO token binds to exactly the string the player request will send.
  return decodeURIComponent(vd);
}

async function main() {
  const visitorData = await getVisitorData();

  // jsdom provides the DOM/global env BotGuard's VM expects.
  const dom = new JSDOM(
    '<!DOCTYPE html><html lang="en"><body></body></html>',
    { url: "https://www.youtube.com/", referrer: "https://www.youtube.com/" }
  );
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    location: dom.window.location,
    origin: dom.window.origin,
  });

  const bgConfig = {
    fetch: (url, opts) => fetch(url, opts),
    globalObj: globalThis,
    identifier: visitorData,
    requestKey: REQUEST_KEY,
  };

  const challenge = await BG.Challenge.create(bgConfig);
  if (!challenge) throw new Error("could not create BotGuard challenge");

  const interpreterJavascript =
    challenge.interpreterJavascript.privateDoNotAccessOrElseSafeScriptWrappedValue;
  if (interpreterJavascript) {
    new Function(interpreterJavascript)();
  } else {
    throw new Error("missing BotGuard interpreter JS");
  }

  const poTokenResult = await BG.PoToken.generate({
    program: challenge.program,
    globalName: challenge.globalName,
    bgConfig,
  });

  const poToken = poTokenResult?.poToken;
  if (!poToken) throw new Error("PoToken.generate returned no token");

  process.stdout.write(JSON.stringify({ visitorData, poToken }) + "\n");
}

main().catch((e) => {
  process.stderr.write("POT_GEN_ERROR: " + (e?.stack || String(e)) + "\n");
  process.exit(1);
});
