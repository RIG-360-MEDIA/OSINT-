'use client'

/**
 * District modal — opens centred over the state brief when a district
 * is clicked on the atlas. Renders the same district panels the
 * full-page route uses, minus the masthead and atlas (since the user
 * is already on the state page with the map behind the modal).
 *
 * Closes on:
 *   - clicking the backdrop
 *   - pressing Escape
 *   - clicking the close (×) button
 *
 * "Open as full page →" link in the corner takes the user to
 * /brief/cm/preview/<id> for sharing / printing.
 */
import { useEffect } from 'react'
import Link from 'next/link'

import {
  CounterNarrativeCard,
  DistrictHero,
  DistrictPanels,
} from '../CMDistrictBrief'
import { getDistrictBrief } from './district-data'
import styles from './styles.module.css'

interface DistrictModalProps {
  districtId: string
  onClose: () => void
}

export function DistrictModal({ districtId, onClose }: DistrictModalProps) {
  const data = getDistrictBrief(districtId)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  if (!data) return null

  return (
    <div
      className={styles.modalOverlay}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`District focus: ${data.name}`}
    >
      <div
        className={styles.modalCard}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.modalToolbar}>
          <Link
            href={`/brief/cm/preview/${data.id}`}
            className={styles.modalOpenFull}
          >
            Open as full page →
          </Link>
          <button
            type="button"
            className={styles.modalClose}
            onClick={onClose}
            aria-label="Close district focus"
          >
            ×
          </button>
        </div>
        <div className={styles.modalBody}>
          <DistrictHero data={data} />
          {data.counterNarrative && <CounterNarrativeCard data={data} />}
          <DistrictPanels data={data} />
        </div>
      </div>
    </div>
  )
}
