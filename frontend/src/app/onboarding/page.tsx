'use client'
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

interface Entity { name: string; type: string; why: string }
interface Profile {
  role_type?: string | null
  organisation?: string | null
  geo_primary?: string | null
  geo_secondary?: string[]
  entities?: Entity[]
  signal_priorities?: Record<string, number>
  role_context?: string | null
}

type Stage = 'loading' | 'q1' | 'q2' | 'q3' | 'q4' | 'q5' | 'extracting' | 'animating' | 'review' | 'saving'

const STAGE_TO_NUM: Record<string, number> = { q1: 1, q2: 2, q3: 3, q4: 4, q5: 5 }
const NUM_TO_STAGE: Record<number, Stage>  = { 1: 'q1', 2: 'q2', 3: 'q3', 4: 'q4', 5: 'q5' }

const QUESTIONS = [
  "Start by telling me who you are and what you do. Don't hold back — the more you tell me about your world, the better I can serve you.",
  "What people, organisations, places, or projects do you need to monitor most closely right now? These are the things you cannot afford to miss a development on.",
  "Where in the world does your work primarily happen? Tell me the geography that matters most — a country, a state, a city, or multiple places.",
  "When you open your intelligence feed every morning, what would make you say 'this is exactly what I needed to know'? What kind of information would genuinely change how you act that day?",
  "What keeps you up at night? What is the scenario you are most worried could develop in the next 30 to 90 days that would seriously impact your work if you were not prepared for it?",
]

const STEP_LABELS = ['Identity', 'The watch', 'Geography', 'Signals', 'The risks']
const STEP_ROMAN  = ['I', 'II', 'III', 'IV', 'V']

const QUESTION_KICKER = [
  'On the record',
  'The watch',
  'The ground',
  'The dispatch',
  'The apprehension',
]

// ── Compass wordmark ───────────────────────────────────────────────────────────

function Wordmark() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="14" cy="14" r="13" stroke="var(--rig-gold)" strokeWidth="1" fill="none" />
        <circle cx="14" cy="14" r="9" stroke="var(--rig-gold)" strokeWidth="0.5" fill="none" opacity="0.5" />
        <path d="M14 2 L16 14 L14 26 L12 14 Z" fill="var(--rig-gold)" opacity="0.9" />
        <path d="M2 14 L14 12 L26 14 L14 16 Z" fill="var(--rig-copper)" opacity="0.7" />
        <circle cx="14" cy="14" r="1.5" fill="var(--rig-ink)" />
      </svg>
      <div>
        <div style={{
          fontFamily:    "'DM Mono', monospace",
          fontSize:      '9px',
          letterSpacing: '0.2em',
          color:         'var(--rig-ink-3)',
          textTransform: 'uppercase',
        }}>Rig · Editions</div>
        <div style={{
          fontFamily: "'Cormorant Garamond', serif",
          fontStyle:  'italic',
          fontSize:   '22px',
          lineHeight: 1,
          color:      'var(--rig-ink)',
          marginTop:  '2px',
        }}>The Surveillance</div>
      </div>
    </div>
  )
}

export default function OnboardingPage() {
  const router = useRouter()
  const [stage, setStage]                       = useState<Stage>('loading')
  const [token, setToken]                       = useState<string | null>(null)
  const [currentQ, setCurrentQ]                 = useState(1)
  const [answer, setAnswer]                     = useState('')
  const [profile, setProfile]                   = useState<Profile>({})
  const [allEntities, setAllEntities]           = useState<Entity[]>([])
  const [visibleEntities, setVisibleEntities]   = useState<Entity[]>([])
  const [animatingEntities, setAnimatingEntities] = useState<Set<string>>(new Set())
  const [followup, setFollowup]                 = useState<string | null>(null)
  const [history, setHistory]                   = useState<Array<{ q: string; a: string }>>([])
  const [addEntityInput, setAddEntityInput]     = useState('')
  const [saving, setSaving]                     = useState(false)
  const [error, setError]                       = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) { router.push('/login'); return }
      const t = data.session.access_token
      setToken(t)
      fetch(`${API}/api/onboarding/status`, { headers: { Authorization: `Bearer ${t}` } })
        .then(r => r.json())
        .then(s => s.has_profile ? router.push('/brief') : setStage('q1'))
        .catch(() => setStage('q1'))
    })
  }, [router])

  useEffect(() => {
    if (stage.startsWith('q') && textareaRef.current) textareaRef.current.focus()
  }, [stage])

  const animateEntities = async (newEntities: Entity[]) => {
    if (newEntities.length === 0) return
    for (const entity of newEntities) {
      await new Promise<void>(r => setTimeout(r, 300))
      setVisibleEntities(prev => [...prev, entity])
      setAnimatingEntities(prev => new Set([...prev, entity.name]))
      await new Promise<void>(r => setTimeout(r, 400))
      setAnimatingEntities(prev => { const n = new Set(prev); n.delete(entity.name); return n })
    }
  }

  const handleSubmit = async () => {
    if (!answer.trim() || !token) return
    const qNum = STAGE_TO_NUM[stage]
    if (!qNum) return
    const currentAnswer = answer.trim()
    setHistory(prev => [...prev, { q: QUESTIONS[qNum - 1], a: currentAnswer }])
    setAnswer('')
    setStage('extracting')
    setError(null)

    try {
      const res = await fetch(`${API}/api/onboarding/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ answer: currentAnswer, question_number: qNum, previous_profile: profile }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Extraction failed' }))
        throw new Error((err as { detail?: string }).detail ?? 'Extraction failed')
      }
      const data = await res.json()
      const mergedProfile: Profile = {
        ...profile,
        ...data.profile,
        entities: [...(profile.entities ?? []), ...(data.new_entities ?? [])],
      }
      setProfile(mergedProfile)
      setAllEntities(mergedProfile.entities ?? [])
      setFollowup(data.followup_question ?? null)
      if (data.new_entities?.length > 0) { setStage('animating'); await animateEntities(data.new_entities) }
      if (qNum < 5) { setStage(NUM_TO_STAGE[qNum + 1]); setCurrentQ(qNum + 1) }
      else setStage('review')
    } catch (e) {
      setError(`The desk couldn't file that. ${e instanceof Error ? e.message : 'Please try again.'}`)
      setStage(NUM_TO_STAGE[qNum] as Stage)
      setAnswer(currentAnswer)
    }
  }

  const handleConfirm = async () => {
    if (!token) return
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/onboarding/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          role_type: profile.role_type ?? 'other',
          geo_primary: profile.geo_primary ?? '',
          geo_secondary: profile.geo_secondary ?? [],
          entities: allEntities,
          signal_priorities: profile.signal_priorities ?? {},
          role_context: profile.role_context ?? '',
        }),
      })
      if (!res.ok) throw new Error('Failed to save profile')
      router.push('/brief')
    } catch { setError('The file could not be saved. Please try again.'); setSaving(false) }
  }

  const removeEntity = (name: string) => setAllEntities(prev => prev.filter(e => e.name !== name))
  const addEntity = () => {
    const name = addEntityInput.trim()
    if (!name || allEntities.some(e => e.name.toLowerCase() === name.toLowerCase())) return
    setAllEntities(prev => [...prev, { name, type: 'topic', why: '' }])
    setAddEntityInput('')
  }

  /* ── Loading ─────────────────────────────────────────────── */
  if (stage === 'loading') {
    return (
      <div style={{
        minHeight: '100vh', backgroundColor: 'var(--rig-paper-2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <div style={{
          width: '24px', height: '24px', borderRadius: '50%',
          border: '2px solid var(--rig-rule-hair)',
          borderTopColor: 'var(--rig-gold)',
          animation: 'spin 0.8s linear infinite',
        }} />
      </div>
    )
  }

  /* ── Review stage ────────────────────────────────────────── */
  if (stage === 'review') {
    return (
      <div style={{
        minHeight: '100vh', backgroundColor: 'var(--rig-paper-2)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', padding: '48px 24px',
      }}>
        <div style={{ marginBottom: '40px' }}>
          <Wordmark />
        </div>

        <div style={{
          width: '100%', maxWidth: '620px',
          backgroundColor: 'var(--rig-paper)',
          border: '1px solid var(--rig-rule)',
          borderTop: '3px solid var(--rig-gold)',
        }}>
          {/* Masthead */}
          <div style={{
            padding: '24px 32px 22px',
            borderBottom: '1px solid var(--rig-rule-hair)',
          }}>
            <div style={{
              fontFamily:    "'DM Mono', monospace",
              fontSize:      '10px',
              color:         'var(--rig-gold)',
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              marginBottom:  '8px',
            }}>
              The desk memo · filed
            </div>
            <h2 style={{
              fontFamily:    "'Cormorant Garamond', serif",
              fontSize:      '36px',
              fontWeight:    400,
              color:         'var(--rig-ink)',
              letterSpacing: '-0.01em',
              lineHeight:    1.05,
            }}>
              Your <span style={{ fontStyle: 'italic', color: 'var(--rig-gold)' }}>brief</span>, as the desk understands it
            </h2>
            <p style={{
              fontFamily: "'Cormorant Garamond', serif",
              fontStyle:  'italic',
              fontSize:   '16px',
              color:      'var(--rig-ink-3)',
              marginTop:  '8px',
            }}>
              Correct the record before we go to press.
            </p>
          </div>

          <div style={{ padding: '26px 32px' }}>
            {/* Profile fields */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', marginBottom: '26px' }}>
              {profile.role_type && (
                <ProfileRow
                  label="Identity"
                  value={`${profile.role_type.charAt(0).toUpperCase() + profile.role_type.slice(1)}${profile.organisation ? ` · ${profile.organisation}` : ''}`}
                />
              )}
              {profile.geo_primary && (
                <ProfileRow
                  label="Geography"
                  value={`${profile.geo_primary}${(profile.geo_secondary ?? []).length > 0 ? ` · ${profile.geo_secondary!.join(', ')}` : ''}`}
                />
              )}
            </div>

            {/* Entities */}
            <div style={{ marginBottom: '22px' }}>
              <div style={{
                fontFamily:    "'DM Mono', monospace",
                fontSize:      '10px',
                fontWeight:    700,
                color:         'var(--rig-ink-3)',
                textTransform: 'uppercase',
                letterSpacing: '0.14em',
                marginBottom:  '12px',
              }}>
                On the watch · {allEntities.length} files
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {allEntities.map(e => (
                  <span key={e.name} className="rig-chip" style={{
                    display: 'inline-flex', alignItems: 'center', gap: '8px',
                  }}>
                    {e.name}
                    <button
                      onClick={() => removeEntity(e.name)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        color: 'var(--rig-ink-3)', fontSize: '14px', lineHeight: 1, padding: 0,
                      }}
                    >×</button>
                  </span>
                ))}
              </div>
            </div>

            {/* Add entity */}
            <div style={{ display: 'flex', gap: '10px', marginBottom: '26px' }}>
              <input
                type="text"
                value={addEntityInput}
                onChange={e => setAddEntityInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addEntity()}
                placeholder="Add to the watch…"
                className="rig-input"
                style={{ flex: 1 }}
              />
              <button onClick={addEntity} className="rig-btn-ghost">Add to file</button>
            </div>

            {error && (
              <div style={{
                padding: '12px 16px',
                marginBottom: '18px',
                backgroundColor: 'var(--rig-paper-2)',
                border: '1px solid var(--rig-rule-hair)',
                borderLeft: '2px solid var(--rig-oxblood)',
                fontFamily: "'Cormorant Garamond', serif",
                fontStyle: 'italic',
                fontSize: '15px',
                color: 'var(--rig-oxblood)',
              }}>{error}</div>
            )}

            <button
              onClick={handleConfirm}
              disabled={saving}
              className="rig-btn-primary"
              style={{
                width: '100%',
                fontFamily: "'Cormorant Garamond', serif",
                fontStyle: 'italic',
                fontSize: '19px',
                padding: '14px 20px',
                opacity: saving ? 0.5 : 1,
                cursor: saving ? 'not-allowed' : 'pointer',
              }}
            >
              {saving ? 'Going to press…' : 'Send the edition to press →'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  /* ── Conversation (q1–q5, extracting, animating) ─────────── */
  const qNum         = STAGE_TO_NUM[stage] ?? currentQ
  const isProcessing = stage === 'extracting' || stage === 'animating'

  return (
    <div style={{
      minHeight: '100vh', backgroundColor: 'var(--rig-paper-2)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      padding: '48px 24px',
    }}>
      <div style={{ width: '100%', maxWidth: '680px' }}>
        {/* Wordmark */}
        <div style={{ marginBottom: '36px' }}>
          <Wordmark />
        </div>

        {/* Progress steps — Roman numerals */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 0,
          marginBottom: '40px',
          padding: '18px 20px',
          backgroundColor: 'var(--rig-paper)',
          border: '1px solid var(--rig-rule-hair)',
        }}>
          {STEP_LABELS.map((label, i) => {
            const n = i + 1
            const done   = n < currentQ
            const active = n === currentQ
            return (
              <div key={n} style={{ display: 'flex', alignItems: 'center', flex: i < 4 ? 1 : 'none' }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                  <div style={{
                    width: '32px', height: '32px', borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    backgroundColor: done
                      ? 'var(--rig-gold)'
                      : active
                        ? 'var(--rig-ink)'
                        : 'var(--rig-paper-2)',
                    border: `1px solid ${done ? 'var(--rig-gold)' : active ? 'var(--rig-ink)' : 'var(--rig-rule)'}`,
                    color: done
                      ? 'var(--rig-ink)'
                      : active
                        ? 'var(--rig-gold)'
                        : 'var(--rig-ink-3)',
                    fontFamily: "'Cormorant Garamond', serif",
                    fontStyle: 'italic',
                    fontSize: '15px',
                    fontWeight: 500,
                    transition: 'all 0.3s',
                  }}>
                    {done ? '✓' : STEP_ROMAN[i]}
                  </div>
                  <span style={{
                    fontFamily:    "'DM Mono', monospace",
                    fontSize:      '9px',
                    color:         active ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
                    fontWeight:    active ? 700 : 400,
                    whiteSpace:    'nowrap',
                    textTransform: 'uppercase',
                    letterSpacing: '0.1em',
                  }}>{label}</span>
                </div>
                {i < 4 && (
                  <div style={{
                    flex: 1, height: '1px', marginBottom: '20px',
                    backgroundColor: n < currentQ ? 'var(--rig-gold)' : 'var(--rig-rule)',
                    transition: 'background-color 0.4s',
                  }} />
                )}
              </div>
            )
          })}
        </div>

        {/* Previous answers — filed record */}
        {history.length > 0 && (
          <div style={{ marginBottom: '26px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {history.map((item, i) => (
              <div key={i} style={{
                padding: '14px 18px',
                backgroundColor: 'var(--rig-paper)',
                border: '1px solid var(--rig-rule-hair)',
                borderLeft: '2px solid var(--rig-copper)',
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  gap: '10px',
                  marginBottom: '6px',
                }}>
                  <span style={{
                    fontFamily: "'Cormorant Garamond', serif",
                    fontStyle: 'italic',
                    fontSize: '16px',
                    color: 'var(--rig-copper)',
                    lineHeight: 1,
                  }}>
                    {STEP_ROMAN[i]}
                  </span>
                  <span style={{
                    fontFamily:    "'DM Mono', monospace",
                    fontSize:      '9px',
                    color:         'var(--rig-ink-3)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.12em',
                  }}>
                    {QUESTION_KICKER[i]} · on file
                  </span>
                </div>
                <p style={{
                  fontFamily: "'Cormorant Garamond', serif",
                  fontSize: '17px',
                  color: 'var(--rig-ink-2)',
                  lineHeight: 1.5,
                }}>{item.a}</p>
              </div>
            ))}
          </div>
        )}

        {/* Current question card */}
        <div style={{
          backgroundColor: 'var(--rig-paper)',
          border: '1px solid var(--rig-rule)',
          borderTop: '3px solid var(--rig-ink)',
        }}>
          {/* Question masthead */}
          <div style={{
            padding: '24px 28px 20px',
            borderBottom: '1px solid var(--rig-rule-hair)',
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: '12px',
              marginBottom: '10px',
            }}>
              <span style={{
                fontFamily: "'Cormorant Garamond', serif",
                fontStyle: 'italic',
                fontSize: '20px',
                color: 'var(--rig-gold)',
                lineHeight: 1,
              }}>
                {STEP_ROMAN[qNum - 1]}
              </span>
              <span style={{
                fontFamily:    "'DM Mono', monospace",
                fontSize:      '10px',
                color:         'var(--rig-gold)',
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
              }}>
                {QUESTION_KICKER[qNum - 1]} · of five
              </span>
            </div>
            <h2 style={{
              fontFamily: "'Cormorant Garamond', serif",
              fontSize:   '24px',
              fontWeight: 400,
              color:      'var(--rig-ink)',
              lineHeight: 1.35,
              letterSpacing: '-0.01em',
            }}>
              {QUESTIONS[qNum - 1]}
            </h2>
            {followup && !isProcessing && (
              <p style={{
                fontFamily: "'Cormorant Garamond', serif",
                fontStyle:  'italic',
                fontSize:   '16px',
                color:      'var(--rig-copper)',
                marginTop:  '10px',
                paddingLeft: '12px',
                borderLeft: '2px solid var(--rig-copper)',
              }}>
                {followup}
              </p>
            )}
          </div>

          {/* Entity animation area */}
          {visibleEntities.length > 0 && (
            <div style={{
              padding: '14px 28px',
              backgroundColor: 'var(--rig-paper-2)',
              borderBottom: '1px solid var(--rig-rule-hair)',
            }}>
              <div style={{
                fontFamily:    "'DM Mono', monospace",
                fontSize:      '10px',
                fontWeight:    700,
                color:         'var(--rig-gold)',
                textTransform: 'uppercase',
                letterSpacing: '0.14em',
                marginBottom:  '10px',
              }}>
                Entered on the watch
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {visibleEntities.map(e => (
                  <span
                    key={e.name}
                    className="rig-chip"
                    data-tone="gold"
                    style={{
                      opacity: animatingEntities.has(e.name) ? 0 : 1,
                      transition: 'opacity 0.4s ease',
                    }}
                  >{e.name}</span>
                ))}
              </div>
            </div>
          )}

          {/* Input area */}
          <div style={{ padding: '22px 28px 24px' }}>
            {isProcessing ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '18px 0' }}>
                <div style={{
                  width: '18px', height: '18px', borderRadius: '50%',
                  border: '2px solid var(--rig-rule-hair)',
                  borderTopColor: 'var(--rig-gold)',
                  animation: 'spin 0.8s linear infinite', flexShrink: 0,
                }} />
                <span style={{
                  fontFamily: "'Cormorant Garamond', serif",
                  fontStyle: 'italic',
                  fontSize: '17px',
                  color: 'var(--rig-ink-2)',
                }}>
                  {stage === 'extracting' ? 'The desk is reading your dispatch…' : 'Filing entities to the watch…'}
                </span>
              </div>
            ) : (
              <>
                <textarea
                  ref={textareaRef}
                  value={answer}
                  onChange={e => setAnswer(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSubmit() }}
                  placeholder="File your dispatch… (Ctrl+Enter to send)"
                  rows={5}
                  className="rig-input"
                  style={{
                    width: '100%',
                    fontFamily: "'Cormorant Garamond', serif",
                    fontSize: '18px',
                    lineHeight: 1.55,
                    resize: 'vertical',
                  }}
                />
                {error && (
                  <p style={{
                    fontFamily: "'Cormorant Garamond', serif",
                    fontStyle: 'italic',
                    fontSize: '15px',
                    color: 'var(--rig-oxblood)',
                    marginTop: '10px',
                  }}>{error}</p>
                )}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
                  <span style={{
                    fontFamily:    "'DM Mono', monospace",
                    fontSize:      '9px',
                    color:         'var(--rig-ink-3)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.12em',
                  }}>
                    Ctrl + Enter files the dispatch
                  </span>
                  <button
                    onClick={handleSubmit}
                    disabled={!answer.trim()}
                    className="rig-btn-primary"
                    style={{
                      opacity: answer.trim() ? 1 : 0.4,
                      cursor: answer.trim() ? 'pointer' : 'not-allowed',
                      fontFamily: "'Cormorant Garamond', serif",
                      fontStyle: 'italic',
                      fontSize: '17px',
                      padding: '10px 22px',
                    }}
                  >
                    {qNum < 5 ? 'File and continue →' : 'File and review the brief →'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function ProfileRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'baseline',
      gap: '16px',
      paddingBottom: '14px',
      borderBottom: '1px solid var(--rig-rule-hair)',
    }}>
      <div style={{
        fontFamily:    "'DM Mono', monospace",
        fontSize:      '10px',
        fontWeight:    700,
        color:         'var(--rig-ink-3)',
        textTransform: 'uppercase',
        letterSpacing: '0.14em',
        flexShrink:    0,
        width:         '110px',
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: "'Cormorant Garamond', serif",
        fontSize:   '20px',
        color:      'var(--rig-ink)',
        lineHeight: 1.3,
        flex:       1,
      }}>
        {value}
      </div>
    </div>
  )
}
