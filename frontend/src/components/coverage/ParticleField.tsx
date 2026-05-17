/**
 * ParticleField — multi-layer drifting particle background with parallax.
 *
 * Three layers at increasing depth:
 *   - far: dim, large, slow — provides atmosphere
 *   - mid: brighter, medium-sized, drifts up
 *   - near: bright, smaller, fastest, cursor-tracks for parallax
 *
 * Cursor parallax shifts each layer by a fraction proportional to depth
 * (near layer shifts most). Combined with subtle camera roll the result
 * has the depth of the reference particle sites without the cost of a
 * full shader pipeline.
 *
 * Honors prefers-reduced-motion: renders one frame and stops.
 */

'use client'

import { useEffect, useRef } from 'react'
import * as THREE from 'three'

interface ParticleLayerSpec {
  count: number
  spread: { x: number; y: number; z: number }
  baseSize: number
  sizeJitter: number
  driftMin: number
  driftMax: number
  opacity: number
  parallaxStrength: number  // 0..1, how much it tracks the cursor
}

const LAYERS: ReadonlyArray<ParticleLayerSpec> = [
  // Far — atmosphere, slow, dim
  {
    count: 320,
    spread: { x: 200, y: 130, z: 30 },
    baseSize: 0.6,
    sizeJitter: 0.6,
    driftMin: 0.001,
    driftMax: 0.006,
    opacity: 0.18,
    parallaxStrength: 0.05,
  },
  // Mid — main field
  {
    count: 420,
    spread: { x: 140, y: 100, z: 40 },
    baseSize: 1.0,
    sizeJitter: 0.9,
    driftMin: 0.008,
    driftMax: 0.022,
    opacity: 0.28,
    parallaxStrength: 0.18,
  },
  // Near — sparse, bright, parallax-strong
  {
    count: 180,
    spread: { x: 90, y: 70, z: 20 },
    baseSize: 1.4,
    sizeJitter: 1.2,
    driftMin: 0.018,
    driftMax: 0.04,
    opacity: 0.42,
    parallaxStrength: 0.55,
  },
]

interface ConstructedLayer {
  points: THREE.Points
  geom: THREE.BufferGeometry
  material: THREE.ShaderMaterial
  speeds: Float32Array
  spec: ParticleLayerSpec
  basePosition: THREE.Vector3
}

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
    camera.position.z = 60

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(width, height)
    renderer.setClearColor(0x000000, 0)
    mount.appendChild(renderer.domElement)

    /* ── Build the three layers ─────────────────────────────── */
    const layers: ConstructedLayer[] = LAYERS.map((spec) => {
      const positions = new Float32Array(spec.count * 3)
      const speeds = new Float32Array(spec.count)
      const sizes = new Float32Array(spec.count)

      for (let i = 0; i < spec.count; i++) {
        positions[i * 3]     = (Math.random() - 0.5) * spec.spread.x
        positions[i * 3 + 1] = (Math.random() - 0.5) * spec.spread.y
        positions[i * 3 + 2] = (Math.random() - 0.5) * spec.spread.z
        speeds[i] = spec.driftMin + Math.random() * (spec.driftMax - spec.driftMin)
        sizes[i]  = spec.baseSize + Math.random() * spec.sizeJitter
      }

      const geom = new THREE.BufferGeometry()
      geom.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      geom.setAttribute('size',     new THREE.BufferAttribute(sizes, 1))

      const material = new THREE.ShaderMaterial({
        uniforms: {
          uColor:   { value: new THREE.Color(0xF2EEE3) },
          uOpacity: { value: spec.opacity },
          uTime:    { value: 0 },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        vertexShader: `
          attribute float size;
          varying float vSize;
          uniform float uTime;
          void main() {
            // tiny per-particle wobble for organic motion
            vec3 p = position;
            p.x += sin(uTime * 0.4 + position.y * 0.05) * 0.4;
            vec4 mv = modelViewMatrix * vec4(p, 1.0);
            gl_PointSize = size * (220.0 / -mv.z);
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
            // Gaussian-like falloff for soft edges.
            float a = exp(-d * d * 14.0) * uOpacity * (0.45 + vSize * 0.45);
            gl_FragColor = vec4(uColor, a);
          }
        `,
      })

      const points = new THREE.Points(geom, material)
      scene.add(points)

      return {
        points,
        geom,
        material,
        speeds,
        spec,
        basePosition: points.position.clone(),
      }
    })

    /* ── Cursor tracking ────────────────────────────────────── */
    const cursor = { x: 0, y: 0, tx: 0, ty: 0 }
    const onMouseMove = (e: MouseEvent) => {
      cursor.tx = (e.clientX / window.innerWidth - 0.5) * 2   // -1..1
      cursor.ty = (e.clientY / window.innerHeight - 0.5) * 2  // -1..1
    }
    window.addEventListener('mousemove', onMouseMove, { passive: true })

    /* ── Animation loop ─────────────────────────────────────── */
    let raf: number | null = null
    const clock = new THREE.Clock()

    const tick = () => {
      const dt = clock.getDelta()
      const t = clock.elapsedTime

      // Smooth cursor — exponential easing toward target.
      cursor.x += (cursor.tx - cursor.x) * 0.06
      cursor.y += (cursor.ty - cursor.y) * 0.06

      for (const layer of layers) {
        const { points, geom, material, speeds, spec } = layer
        const pos = geom.attributes.position
        const arr = pos.array as Float32Array
        for (let i = 0; i < spec.count; i++) {
          arr[i * 3 + 1] += speeds[i] * dt * 60
          if (arr[i * 3 + 1] > spec.spread.y * 0.5) {
            arr[i * 3 + 1] = -spec.spread.y * 0.5
            arr[i * 3]     = (Math.random() - 0.5) * spec.spread.x
          }
        }
        pos.needsUpdate = true

        // Parallax displacement — strength scales with depth.
        const px = -cursor.x * 6 * spec.parallaxStrength
        const py = cursor.y * 4 * spec.parallaxStrength
        points.position.x = px
        points.position.y = py

        material.uniforms.uTime.value = t
      }

      renderer.render(scene, camera)
      if (!reduced) raf = requestAnimationFrame(tick)
    }

    if (reduced) {
      renderer.render(scene, camera)
    } else {
      raf = requestAnimationFrame(tick)
    }

    /* ── Resize ─────────────────────────────────────────────── */
    const onResize = () => {
      const w = window.innerWidth
      const h = window.innerHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', onResize)

    /* ── Cleanup ────────────────────────────────────────────── */
    return () => {
      if (raf !== null) cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('mousemove', onMouseMove)
      for (const layer of layers) {
        layer.geom.dispose()
        layer.material.dispose()
      }
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
