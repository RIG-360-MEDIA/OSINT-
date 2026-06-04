// Curated, source-verified live YouTube news channels (channelId resolved from each
// channel's handle, 2026-06-04). Live embeds use youtube.com/embed/live_stream?channel=ID,
// which plays the channel's CURRENT live stream. Edit freely — add { name, id }.
//
// Persona-scoped: GLOBAL shows world wires; MINE shows 3 national + 5 regional for the
// persona's primary state.

export const GLOBAL_CHANNELS = [
  { name: 'Al Jazeera English', id: 'UCfiwzLy-8yKzIbsmZTzxDgw' },
  { name: 'DW News', id: 'UCbbS1GE942k3UVqpLklyhIA' },
  { name: 'France 24 English', id: 'UCCCPCZNChQdGa9EkATeye4g' },
  { name: 'WION', id: 'UCWEIPvoxRwn6llPOIn555rQ' },
  { name: 'Sky News', id: 'UCkFclpi8U9VJjfxLYoms7Aw' },
];

export const NATIONAL_CHANNELS = [
  { name: 'NDTV', id: 'UCXBD5iG5cr4ZYZ99K-fmDHg' },
  { name: 'India Today', id: 'UCYPvAwZP8pZhSMW8qs7cVCw' },
  { name: 'Republic World', id: 'UChIuMQsOdbrc4Evj_raoDZA' },
];

// Regional channels by primary-state code (districts.state_code).
export const REGIONAL_BY_STATE = {
  AP: [
    { name: 'TV9 Telugu', id: 'UCfaww9Q8C_-EaM0sXI8o-fA' },
    { name: 'Sakshi TV', id: 'UCQ_FATLW83q-4xJ2fsi8qAw' },
    { name: 'ABN Telugu', id: 'UC_2irx_BQR7RsBKmUV9fePQ' },
    { name: 'ETV Andhra Pradesh', id: 'UCSs9H1cyB3OHdy8wkit8ZKg' },
    { name: '10TV', id: 'UCBF2w5CGS8d0YLygY0nlnXQ' },
  ],
  TG: [
    { name: 'V6 News', id: 'UC239yTgdQbce3omeOjCt8_A' },
    { name: 'Mahaa News', id: 'UCf40zfa4GGOC9s8yoQhGZGg' },
    { name: 'TV9 Telugu', id: 'UCfaww9Q8C_-EaM0sXI8o-fA' },
    { name: 'Sakshi TV', id: 'UCQ_FATLW83q-4xJ2fsi8qAw' },
    { name: 'ABN Telugu', id: 'UC_2irx_BQR7RsBKmUV9fePQ' },
  ],
};

// Resolve the channel set for a given scope + primary state.
export function channelsFor(scope, stateCode) {
  if (scope === 'global') return { groups: [{ label: 'World wires', items: GLOBAL_CHANNELS }] };
  const regional = REGIONAL_BY_STATE[stateCode] || [];
  return {
    groups: [
      { label: 'National', items: NATIONAL_CHANNELS },
      { label: 'Regional', items: regional },
    ],
  };
}
