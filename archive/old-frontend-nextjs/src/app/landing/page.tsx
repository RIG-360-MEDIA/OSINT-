"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { ShaderAnimation } from "@/components/ui/shader-animation"
import styles from "./landing.module.css"

interface DossierEntry {
  numeral: string
  title: string
  lede: string
  body: string
  tag: string
}

const DOSSIER: DossierEntry[] = [
  {
    numeral: "I",
    title: "Intake",
    lede: "Every wire, every feed, every stream.",
    body:
      "RSS rooms of record, YouTube channels, Telegram MTProto, press cuttings, vision-extracted newspapers. The firehose arrives here — not for you to read.",
    tag: "Sources · Multilingual",
  },
  {
    numeral: "II",
    title: "Interpretation",
    lede: "Language, geography, intent.",
    body:
      "Entities resolved. Coordinates placed. Sentiment weighted against history. An analyst's instincts, rendered as an operator you can audit line by line.",
    tag: "NLP · Geo · Groq",
  },
  {
    numeral: "III",
    title: "The Brief",
    lede: "Seven minutes of the day that mattered.",
    body:
      "An editorial brief written for the one person whose time is expensive. Threads, signals, opposition reads, policy shifts — ordered by consequence, not chronology.",
    tag: "Daily · Editorial",
  },
  {
    numeral: "IV",
    title: "Coverage",
    lede: "Who is saying what, and who is silent.",
    body:
      "Every outlet that ran the story. Every outlet that didn't. Patterns across tiers, geographies, and dialects — the shape of consensus and the shape of its absence.",
    tag: "Tiered · Comparative",
  },
]

function CompassGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="11" stroke="currentColor" strokeWidth="0.6" opacity="0.55" />
      <path
        d="M12 1 L13.2 10.8 L22 12 L13.2 13.2 L12 23 L10.8 13.2 L2 12 L10.8 10.8 Z"
        fill="currentColor"
        opacity="0.9"
      />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" />
    </svg>
  )
}

function useNow(): string {
  const [now, setNow] = useState<string>("")
  useEffect(() => {
    const tick = () => setNow(`${new Date().toISOString().slice(11, 19)} UTC`)
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [])
  return now
}

export default function LandingPage() {
  const now = useNow()

  return (
    <main className={styles.root}>
      <section className={styles.hero}>
        <div className={styles.videoLayer}>
          <ShaderAnimation />
        </div>
        <div className={styles.shaderTint} />
        <div className={styles.vignette} />
        <div className={styles.readingScrim} />
        <div className={styles.grain} />

        <div className={styles.heroInner}>
          <div className={styles.heroHeader}>
            <Link href="/" className={styles.brand} aria-label="Robin OSINT">
              <span className={styles.brandOrnament} aria-hidden="true">
                <CompassGlyph />
              </span>
              <span className={styles.brandRig}>Robin</span>
              <span className={styles.brandSurveillance}>OSINT</span>
              <span className={styles.brandTerminal}>.</span>
            </Link>
            <div className={styles.heroHud}>
              <div className={styles.hudCoord}>28.6139° N  ·  77.2090° E</div>
              <div className={styles.hudTime}>{now || "— : — : —"}</div>
            </div>
          </div>

          <div className={styles.heroCenter}>
            <div className={styles.eyebrow}>
              <span className={styles.rule} />
              <span>Dispatch</span>
              <span className={styles.diamond}>◆</span>
              <span>Vol. I</span>
              <span className={styles.rule} />
            </div>

            <h1 className={styles.title}>
              The signal,
              <br />
              <span className={styles.titleItalic}>through the noise.</span>
            </h1>

            <p className={styles.deck}>
              A reading room for a world that speaks too fast. Robin listens across
              channels, languages, and rooms — and files a brief by morning.
            </p>

            <div className={styles.motto}>Scientia · Potentia · Est</div>
          </div>

          <div className={styles.heroFooter}>
            <span aria-hidden="true" />
            <Link href="/login" className={styles.ctaLink}>
              <span className={styles.ctaKicker}>Access</span>
              <span className={styles.ctaLabel}>
                Enter the room
                <span className={styles.arrow}>→</span>
              </span>
              <span className={styles.ctaRule} />
            </Link>
          </div>
        </div>
      </section>

      <section className={styles.dossier}>
        <div className={styles.dossierInner}>
          <div className={styles.dossierHead}>
            <div>
              <div className={styles.dossierKicker}>§ The Dossier</div>
              <div className={styles.dossierTitle}>
                Four movements, one <em>instrument</em>.
              </div>
            </div>
            <div className={styles.folio}>Folio · 04</div>
          </div>

          {DOSSIER.map((entry, idx) => (
            <article key={entry.numeral} className={styles.entry}>
              <div className={styles.numeral}>{entry.numeral}.</div>

              <div className={styles.entryBody}>
                <div className={styles.entryKicker}>Movement {idx + 1}</div>
                <h3>{entry.title}</h3>
                <p className={styles.entryLede}>{entry.lede}</p>
              </div>

              <div className={styles.entryRight}>
                <p>{entry.body}</p>
                <div className={styles.tag}>{entry.tag}</div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.stats}>
        <div className={styles.statsGrid}>
          <div>
            <div className={styles.statLabel}>Channels Monitored</div>
            <div className={styles.statNumber}>412</div>
            <div className={styles.statSub}>RSS · YouTube · Telegram · Press</div>
          </div>
          <div>
            <div className={styles.statLabel}>Languages Covered</div>
            <div className={styles.statNumber}>17</div>
            <div className={styles.statSub}>Including regional dialects</div>
          </div>
          <div>
            <div className={styles.statLabel}>Cadence</div>
            <div className={styles.statNumber}>06:00</div>
            <div className={styles.statSub}>Brief filed daily, IST</div>
          </div>
        </div>
      </section>

      <section className={styles.colophon}>
        <div className={styles.colophonVideo}>
          <ShaderAnimation />
        </div>
        <div className={styles.shaderTint} />
        <div className={styles.colophonVignette} />

        <div className={styles.colophonInner}>
          <div className={styles.eyebrow}>
            <span className={styles.rule} />
            <span>Colophon</span>
            <span className={styles.rule} />
          </div>

          <h2 className={styles.colophonTitle}>
            Built for the <em>one reader</em>
            <br />
            whose time is <em>borrowed</em>.
          </h2>

          <p className={styles.colophonDeck}>
            Not a dashboard. Not a feed. A morning paper of one — filed by an
            instrument that reads everything, so the desk does not have to.
          </p>

          <div className={styles.ctaGroup}>
            <Link href="/signup" className={styles.btnPrimary}>
              Request Press Credentials
              <span className={styles.arrow}>→</span>
            </Link>
            <Link href="/login" className={styles.btnOutline}>
              Returning Reader
            </Link>
          </div>

          <div className={styles.masthead}>
            <div>
              <div className={styles.mastheadKey}>File Code</div>
              <div className={styles.mastheadVal}>RIG/26/I</div>
            </div>
            <div>
              <div className={styles.mastheadKey}>Issue</div>
              <div className={styles.mastheadVal}>Vol. I · №. 01</div>
            </div>
            <div>
              <div className={styles.mastheadKey}>Clearance</div>
              <div className={styles.mastheadVal}>Editorial</div>
            </div>
            <div>
              <div className={styles.mastheadKey}>Timestamp</div>
              <div className={styles.mastheadVal}>{now || "— : — : —"}</div>
            </div>
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div>© Robin OSINT · Desk of Record</div>
          <div className={styles.footerMid}>Set in Playfair Display &amp; DM Mono</div>
          <div>End of dispatch —</div>
        </div>
      </footer>
    </main>
  )
}
