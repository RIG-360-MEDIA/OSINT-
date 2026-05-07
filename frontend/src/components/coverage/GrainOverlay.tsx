/**
 * GrainOverlay — fixed-position animated film grain over the whole viewport.
 *
 * Implementation: SVG turbulence noise rasterised once into a CSS background,
 * positioned with negative inset so the animated translate doesn't reveal
 * edges, blended with `overlay`. Animation is a stepped translate keyframe
 * (10 steps, 8s) that creates the classic shifting-grain look without
 * needing a video file or GIF.
 *
 * The keyframe and base styles live in globals.css under .onyx-grain.
 */

export function GrainOverlay() {
  return <div className="onyx-grain" aria-hidden="true" />
}
