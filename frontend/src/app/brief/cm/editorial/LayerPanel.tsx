'use client'

import { LAYERS } from './layers'
import styles from './styles.module.css'

interface LayerPanelProps {
  activeLayerId: string
  onChange: (id: string) => void
}

/**
 * Horizontal pill toggles — World-Monitor inspired layer chooser.
 * Active pill carries the wax-red wash and the category dot tinted to
 * match the layer family. Sits above the [map | feed] grid.
 */
export function LayerPanel({ activeLayerId, onChange }: LayerPanelProps) {
  return (
    <div className={styles.layerPills} role="tablist" aria-label="Atlas layers">
      {LAYERS.map((l) => {
        const active = l.id === activeLayerId
        return (
          <button
            key={l.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={`${styles.layerPill} ${active ? styles.layerPillActive : ''}`}
            onClick={() => onChange(l.id)}
          >
            <span
              className={`${styles.layerCategoryDot} ${styles[`layerCat_${l.category}`]}`}
              aria-hidden="true"
            />
            <span className={styles.layerPillLabel}>{l.label}</span>
            <span className={styles.layerPillCategory}>{l.category}</span>
          </button>
        )
      })}
    </div>
  )
}
