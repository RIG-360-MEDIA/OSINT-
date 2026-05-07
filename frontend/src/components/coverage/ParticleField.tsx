/**
 * ParticleField — drifting monochrome particles in deep background.
 *
 * Uses three.js (already a project dep at v0.160) with a single Points
 * mesh. Roughly 600 particles, slow drift on Y, very dim. Fixed-position
 * full-viewport canvas, pointer-events:none. Sits behind everything.
 *
 * Performance: pre-allocates buffers once, animates via raf, cleans up on
 * unmount. Honors prefers-reduced-motion (renders a single static frame
 * then stops).
 */

'use client'

import { useEffect, useRef } from 'react'
import * as THREE from 'three'

export function ParticleField() {
  const mountRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const width = window.innerWidth
    const height = window.innerHeight

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(70, width / height, 0.1, 1000)
    camera.position.z = 40

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(width, height)
    renderer.setClearColor(0x000000, 0)
    mount.appendChild(renderer.domElement)

    /* ── Particle geometry ───────────────────────────────────────────── */
    const COUNT = 600
    const positions = new Float32Array(COUNT * 3)
    const speeds = new Float32Array(COUNT)
    const sizes = new Float32Array(COUNT)

    for (let i = 0; i < COUNT; i++) {
      positions[i * 3]     = (Math.random() - 0.5) * 120  // x
      positions[i * 3 + 1] = (Math.random() - 0.5) * 80   // y
      positions[i * 3 + 2] = (Math.random() - 0.5) * 60   // z
      speeds[i] = 0.005 + Math.random() * 0.015
      sizes[i]  = 0.4 + Math.random() * 0.8
    }

    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geom.setAttribute('size',     new THREE.BufferAttribute(sizes, 1))

    /* Custom shader: round soft particles, bone-tinted, very dim */
    const material = new THREE.ShaderMaterial({
      uniforms: {
        uColor: { value: new THREE.Color(0xF2EEE3) },
        uOpacity: { value: 0.32 },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: `
        attribute float size;
        varying float vSize;
        void main() {
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * (180.0 / -mv.z);
          gl_Position = projectionMatrix * mv;
          vSize = size;
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        uniform float uOpacity;
        varying float vSize;
        void main() {
          vec2 p = gl_PointCoord - 0.5;
          float d = length(p);
          if (d > 0.5) discard;
          float alpha = smoothstep(0.5, 0.0, d) * uOpacity * (0.4 + vSize * 0.4);
          gl_FragColor = vec4(uColor, alpha);
        }
      `,
    })

    const points = new THREE.Points(geom, material)
    scene.add(points)

    /* ── Animation loop ─────────────────────────────────────────────── */
    let raf: number | null = null
    const clock = new THREE.Clock()

    const tick = () => {
      const dt = clock.getDelta()
      const pos = geom.attributes.position
      const arr = pos.array as Float32Array
      for (let i = 0; i < COUNT; i++) {
        arr[i * 3 + 1] += speeds[i] * dt * 60  // drift up
        // Wrap when off-screen top
        if (arr[i * 3 + 1] > 50) {
          arr[i * 3 + 1] = -50
          arr[i * 3] = (Math.random() - 0.5) * 120
        }
      }
      pos.needsUpdate = true
      // Tiny camera parallax based on mouse (set via CSS var elsewhere)
      renderer.render(scene, camera)
      if (!reduced) raf = requestAnimationFrame(tick)
    }

    if (reduced) {
      // Render one frame and stop
      renderer.render(scene, camera)
    } else {
      raf = requestAnimationFrame(tick)
    }

    /* ── Resize ─────────────────────────────────────────────────────── */
    const onResize = () => {
      const w = window.innerWidth
      const h = window.innerHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', onResize)

    /* ── Cleanup ────────────────────────────────────────────────────── */
    return () => {
      if (raf !== null) cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      geom.dispose()
      material.dispose()
      renderer.dispose()
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement)
      }
    }
  }, [])

  return (
    <div
      ref={mountRef}
      aria-hidden="true"
      style={{
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 0,
      }}
    />
  )
}
