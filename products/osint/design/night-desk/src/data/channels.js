// Curated, source-verified live YouTube news channels (channelId + current live
// videoId resolved from each channel's /live page, 2026-06-04).
//
// Why videoId and not live_stream?channel=ID: several Indian channels (NDTV, India
// Today) run MULTIPLE simultaneous live streams, so the live_stream redirect can't
// pick one and returns "Video unavailable". A specific videoId embeds deterministically.
// `live` is the current live videoId where we confirmed it live + embeddable; if a
// channel rotates its stream the embed falls back to live_stream?channel=ID.
//
// Persona-scoped: GLOBAL = world wires; MINE = national + regional for the persona's
// primary state. Capped at 6 tiles, World-Monitor style.

const GLOBAL = [
  { name: 'Al Jazeera English', id: 'UCfiwzLy-8yKzIbsmZTzxDgw', live: 'N8xxOD0nT1Y' },
  { name: 'France 24 English', id: 'UCCCPCZNChQdGa9EkATeye4g', live: 'a47ckXKZjxI' },
  { name: 'DW News', id: 'UCbbS1GE942k3UVqpLklyhIA' },
  { name: 'WION', id: 'UCWEIPvoxRwn6llPOIn555rQ' },
  { name: 'Sky News', id: 'UCkFclpi8U9VJjfxLYoms7Aw' },
];

// MINE pool, ordered so the confirmed-live channels come first (sliced to 6).
const BY_STATE = {
  AP: [
    { name: 'NDTV', id: 'UCXBD5iG5cr4ZYZ99K-fmDHg', live: 'Z39sKDk6Goc' },
    { name: 'India Today', id: 'UCYPvAwZP8pZhSMW8qs7cVCw', live: 'S_vIHNXkiNA' },
    { name: 'Republic World', id: 'UChIuMQsOdbrc4Evj_raoDZA', live: '3xmHIN3XRmc' },
    { name: 'TV9 Telugu', id: 'UCfaww9Q8C_-EaM0sXI8o-fA', live: 'MuLKRPmOamM' },
    { name: 'ABN Telugu', id: 'UC_2irx_BQR7RsBKmUV9fePQ', live: 'eNCV9ooxf_Y' },
    { name: 'Sakshi TV', id: 'UCQ_FATLW83q-4xJ2fsi8qAw' },
    { name: 'ETV Andhra Pradesh', id: 'UCSs9H1cyB3OHdy8wkit8ZKg' },
    { name: '10TV', id: 'UCBF2w5CGS8d0YLygY0nlnXQ' },
  ],
  TG: [
    { name: 'NDTV', id: 'UCXBD5iG5cr4ZYZ99K-fmDHg', live: 'Z39sKDk6Goc' },
    { name: 'India Today', id: 'UCYPvAwZP8pZhSMW8qs7cVCw', live: 'S_vIHNXkiNA' },
    { name: 'TV9 Telugu', id: 'UCfaww9Q8C_-EaM0sXI8o-fA', live: 'MuLKRPmOamM' },
    { name: 'V6 News', id: 'UC239yTgdQbce3omeOjCt8_A' },
    { name: 'Mahaa News', id: 'UCf40zfa4GGOC9s8yoQhGZGg' },
    { name: 'ABN Telugu', id: 'UC_2irx_BQR7RsBKmUV9fePQ', live: 'eNCV9ooxf_Y' },
  ],
};

const MAX_TILES = 6;

// Flat channel list for a given scope + primary state, capped at 6.
export function channelsFor(scope, stateCode) {
  const pool = scope === 'global' ? GLOBAL : (BY_STATE[stateCode] || GLOBAL);
  return pool.slice(0, MAX_TILES);
}
