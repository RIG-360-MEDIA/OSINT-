"use client"

import { useEffect, useRef } from "react"

interface VideoBackgroundProps {
  src: string
  poster?: string
}

export function VideoBackground({ src, poster }: VideoBackgroundProps) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.playbackRate = 0.9
    const tryPlay = () => video.play().catch(() => undefined)
    tryPlay()
  }, [])

  return (
    <video
      ref={videoRef}
      src={src}
      poster={poster}
      autoPlay
      muted
      loop
      playsInline
      preload="auto"
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        objectFit: "cover",
        objectPosition: "center",
        pointerEvents: "none",
        transform: "scale(1.09) translate(-0.8%, 0)",
        transformOrigin: "center center",
        willChange: "transform",
      }}
    />
  )
}
