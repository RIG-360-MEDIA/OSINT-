'use client'

import { LAYERS } from './layers'
import styles from './styles.module.css'

interface LayerPanelProps {
  activeLayerId: string
  onChange: (id: string) => void
}

/**
 * Right-side toggle panel — radio-style. Active layer drives the map's
 * choropleth fill + overlay markers. Categories are colour-coded so the
 * eye groups Signal, Safety, Economy, Infra, Composite at a glance.
 */
export function LayerPanel({ activeLayerId, onChange }: LayerPanelProps) {
  return (
    <aside className={styles.layerPanel}>
      <div className={styles.layerPanelHeader}>
        <span className={styles.sectionEyebrow}>Atlas Layers</span>
        <span className={styles.sectionMeta}>{LAYERS.length}</span>
      </div>
      <ul className={styles.layerList}>
        {LAYERS.map((l) => {
          const active = l.id === activeLayerId
          return (
            <li key={l.id}>
              <button
                type="button"
                className={`${styles.layerRow} ${active ? styles.layerRowActive : ''}`}
                onClick={() => onChange(l.id)}
              >
                <span
                  className={`${styles.layerCategoryDot} ${styles[`layerCat_${l.category}`]}`}
                  aria-hidden="true"
                />
                <span className={styles.layerRowLabel}>{l.label}</span>
                <span className={styles.layerRowCategory}>{l.category}</span>
              </button>
              {active && (
                <p className={styles.layerRowDescription}>{l.description}</p>
              )}
              {active && (
                <div className={styles.layerScale}>
                  {l.scale.map((s, i) => (
                    <span key={i}>{s}</span>
                  ))}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
