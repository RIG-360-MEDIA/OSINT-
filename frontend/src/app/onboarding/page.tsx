'use client'
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

interface Entity {
  name: string
  type: string
  why: string
}

interface Profile {
  role_type?: string | null
  organisation?: string | null
  geo_primary?: string | null
  geo_secondary?: string[]
  entities?: Entity[]
  signal_priorities?: Record<string, number>
  role_context?: string | null
}

type Stage =
  | 'loading'
  | 'q1' | 'q2' | 'q3' | 'q4' | 'q5'
  | 'extracting'
  | 'animating'
  | 'review'
  | 'saving'

const STAGE_TO_NUM: Record<string, number> = { q1: 1, q2: 2, q3: 3, q4: 4, q5: 5 }
const NUM_TO_STAGE: Record<number, Stage> = { 1: 'q1', 2: 'q2', 3: 'q3', 4: 'q4', 5: 'q5' }

const QUESTIONS = [
  "Start by telling me who you are and what you do. Don't hold back — the more you tell me about your world, the better I can serve you.",
  "What people, organisations, places, or projects do you need to monitor most closely right now? These are the things you cannot afford to miss a development on.",
  "Where in the world does your work primarily happen? Tell me the geography that matters most — a country, a state, a city, or multiple places.",
  "When you open your intelligence feed every morning, what would make you say 'this is exactly what I needed to know'? What kind of information would genuinely change how you act that day?",
  "What keeps you up at night? What is the scenario you are most worried could develop in the next 30 to 90 days that would seriously impact your work if you were not prepared for it?",
]

function EntityChip({
  entity,
  onRemove,
  visible = true,
}: {
  entity: Entity
  onRemove?: () => void
  visible?: boolean
}) {
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '4px 10px',
      backgroundColor: '#EFEBE4',
      border: '1px solid #DDD8D0',
      borderRadius: '2px',
      fontFamily: "'DM Sans', system-ui, sans-serif",
      fontSize: '13px',
      color: '#1A1614',
      opacity: visible ? 1 : 0,
      transition: 'opacity 0.4s ease',
    }}>
      {entity.name}
      {onRemove && (
        <button
          onClick={onRemove}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: '#9C928A',
            fontSize: '14px',
            lineHeight: 1,
            padding: '0 2px',
          }}
        >
          ×
        </button>
      )}
    </span>
  )
}

export default function OnboardingPage() {
  const router = useRouter()
  const [stage, setStage] = useState<Stage>('loading')
  const [token, setToken] = useState<string | null>(null)
  const [currentQ, setCurrentQ] = useState(1)
  const [answer, setAnswer] = useState('')
  const [profile, setProfile] = useState<Profile>({})
  const [allEntities, setAllEntities] = useState<Entity[]>([])
  const [visibleEntities, setVisibleEntities] = useState<Entity[]>([])
  const [animatingEntities, setAnimatingEntities] = useState<Set<string>>(new Set())
  const [followup, setFollowup] = useState<string | null>(null)
  const [history, setHistory] = useState<Array<{ q: string; a: string }>>([])
  const [addEntityInput, setAddEntityInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auth check
  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) {
        router.push('/login')
        return
      }
      // Check if already onboarded
      const t = data.session.access_token
      setToken(t)
      fetch(`${API}/api/onboarding/status`, {
        headers: { Authorization: `Bearer ${t}` },
      })
        .then(r => r.json())
        .then(s => {
          if (s.has_profile) {
            router.push('/brief')
          } else {
            setStage('q1')
          }
        })
        .catch(() => setStage('q1'))
    })
  }, [router])

  useEffect(() => {
    if (stage.startsWith('q') && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [stage])

  const animateEntities = async (newEntities: Entity[]) => {
    if (newEntities.length === 0) return
    for (const entity of newEntities) {
      await new Promise<void>(resolve => setTimeout(resolve, 300))
      setVisibleEntities(prev => [...prev, entity])
      setAnimatingEntities(prev => new Set([...prev, entity.name]))
      await new Promise<void>(resolve => setTimeout(resolve, 400))
      setAnimatingEntities(prev => {
        const next = new Set(prev)
        next.delete(entity.name)
        return next
      })
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
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          answer: currentAnswer,
          question_number: qNum,
          previous_profile: profile,
        }),
      })

      if (!res.ok) throw new Error('Extraction failed')
      const data = await res.json()

      const mergedProfile: Profile = {
        ...profile,
        ...data.profile,
        entities: [
          ...(profile.entities ?? []),
          ...(data.new_entities ?? []),
        ],
      }
      setProfile(mergedProfile)
      setAllEntities(mergedProfile.entities ?? [])
      setFollowup(data.followup_question ?? null)

      if (data.new_entities?.length > 0) {
        setStage('animating')
        await animateEntities(data.new_entities)
      }

      if (qNum < 5) {
        setStage(NUM_TO_STAGE[qNum + 1])
        setCurrentQ(qNum + 1)
      } else {
        setStage('review')
      }
    } catch (e) {
      setError('Something went wrong extracting your profile. Please try again.')
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
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
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
    } catch {
      setError('Failed to save your profile. Please try again.')
      setSaving(false)
    }
  }

  const removeEntity = (name: string) => {
    setAllEntities(prev => prev.filter(e => e.name !== name))
  }

  const addEntity = () => {
    const name = addEntityInput.trim()
    if (!name || allEntities.some(e => e.name.toLowerCase() === name.toLowerCase())) return
    setAllEntities(prev => [...prev, { name, type: 'topic', why: '' }])
    setAddEntityInput('')
  }

  const progressDots = (
    <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginBottom: '40px' }}>
      {[1, 2, 3, 4, 5].map(n => (
        <div
          key={n}
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: n <= currentQ ? '#8B1A1A' : 'transparent',
            border: '1.5px solid #8B1A1A',
            transition: 'background-color 0.3s',
          }}
        />
      ))}
    </div>
  )

  if (stage === 'loading') {
    return (
      <div style={{
        minHeight: '100vh',
        backgroundColor: '#F7F4EF',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <p style={{ fontFamily: "'DM Sans', system-ui", color: '#9C928A', fontSize: '14px' }}>
          Preparing your session...
        </p>
      </div>
    )
  }

  // Review stage
  if (stage === 'review') {
    return (
      <div style={{
        minHeight: '100vh',
        backgroundColor: '#F7F4EF',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
      }}>
        <div style={{ width: '100%', maxWidth: '560px' }}>
          <div style={{ textAlign: 'center', marginBottom: '32px' }}>
            <h1 style={{
              fontFamily: "'Playfair Display', Georgia, serif",
              fontSize: '22px',
              fontWeight: 700,
              color: '#8B1A1A',
              letterSpacing: '0.05em',
            }}>
              RIG SURVEILLANCE
            </h1>
          </div>

          <div style={{
            backgroundColor: '#EFEBE4',
            border: '1px solid #DDD8D0',
            borderRadius: '2px',
            padding: '32px',
          }}>
            <p style={{
              fontFamily: "'DM Sans', system-ui",
              fontSize: '11px',
              fontWeight: 600,
              color: '#9C928A',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              marginBottom: '20px',
            }}>
              Your Intelligence Profile
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
              {profile.role_type && (
                <div>
                  <span style={{ fontFamily: "'DM Sans', system-ui", fontSize: '12px', color: '#9C928A', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Role</span>
                  <p style={{ fontFamily: "'DM Sans', system-ui", fontSize: '15px', color: '#1A1614', marginTop: '2px' }}>
                    {profile.role_type.charAt(0).toUpperCase() + profile.role_type.slice(1)}
                    {profile.organisation ? ` · ${profile.organisation}` : ''}
                  </p>
                </div>
              )}
              {profile.geo_primary && (
                <div>
                  <span style={{ fontFamily: "'DM Sans', system-ui", fontSize: '12px', color: '#9C928A', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Focus</span>
                  <p style={{ fontFamily: "'DM Sans', system-ui", fontSize: '15px', color: '#1A1614', marginTop: '2px' }}>
                    {profile.geo_primary}
                    {(profile.geo_secondary ?? []).length > 0 ? ` + ${profile.geo_secondary!.join(', ')}` : ''}
                  </p>
                </div>
              )}
            </div>

            <div style={{ marginBottom: '20px' }}>
              <p style={{
                fontFamily: "'DM Sans', system-ui",
                fontSize: '12px',
                color: '#9C928A',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                marginBottom: '10px',
              }}>
                Monitoring ({allEntities.length} entities)
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {allEntities.map(e => (
                  <EntityChip key={e.name} entity={e} onRemove={() => removeEntity(e.name)} />
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: '8px', marginBottom: '28px' }}>
              <input
                type="text"
                value={addEntityInput}
                onChange={e => setAddEntityInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addEntity()}
                placeholder="+ Add entity"
                style={{
                  flex: 1,
                  padding: '8px 0',
                  border: 'none',
                  borderBottom: '1px solid #DDD8D0',
                  background: 'transparent',
                  fontFamily: "'DM Sans', system-ui",
                  fontSize: '14px',
                  color: '#1A1614',
                  outline: 'none',
                }}
              />
              <button
                onClick={addEntity}
                style={{
                  padding: '6px 14px',
                  backgroundColor: 'transparent',
                  border: '1px solid #DDD8D0',
                  borderRadius: '2px',
                  fontFamily: "'DM Sans', system-ui",
                  fontSize: '13px',
                  color: '#5C5249',
                  cursor: 'pointer',
                }}
              >
                Add
              </button>
            </div>

            {error && (
              <p style={{ fontFamily: "'DM Sans', system-ui", fontSize: '13px', color: '#8B1A1A', marginBottom: '16px' }}>
                {error}
              </p>
            )}

            <button
              onClick={handleConfirm}
              disabled={saving}
              style={{
                width: '100%',
                padding: '14px 24px',
                backgroundColor: saving ? '#9C928A' : '#8B1A1A',
                color: 'white',
                border: 'none',
                borderRadius: '2px',
                fontFamily: "'DM Sans', system-ui",
                fontSize: '14px',
                fontWeight: 500,
                cursor: saving ? 'not-allowed' : 'pointer',
                letterSpacing: '0.03em',
              }}
            >
              {saving ? 'Starting your feed...' : 'Start Monitoring →'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Conversation stages (q1–q5, extracting, animating)
  const qNum = STAGE_TO_NUM[stage] ?? currentQ
  const isProcessing = stage === 'extracting' || stage === 'animating'

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#F7F4EF',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
    }}>
      <div style={{ width: '100%', maxWidth: '560px' }}>
        {/* Wordmark */}
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <h1 style={{
            fontFamily: "'Playfair Display', Georgia, serif",
            fontSize: '20px',
            fontWeight: 700,
            color: '#8B1A1A',
            letterSpacing: '0.05em',
          }}>
            RIG SURVEILLANCE
          </h1>
        </div>

        {/* Progress */}
        {progressDots}

        {/* History */}
        {history.length > 0 && (
          <div style={{ marginBottom: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {history.map((item, i) => (
              <div key={i}>
                <p style={{
                  fontFamily: "'DM Sans', system-ui",
                  fontSize: '12px',
                  color: '#9C928A',
                  marginBottom: '4px',
                }}>
                  {item.q}
                </p>
                <p style={{
                  fontFamily: "'DM Sans', system-ui",
                  fontSize: '14px',
                  color: '#5C5249',
                  lineHeight: '1.5',
                }}>
                  {item.a}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Current question */}
        <h2 style={{
          fontFamily: "'Playfair Display', Georgia, serif",
          fontSize: '24px',
          fontWeight: 700,
          color: '#1A1614',
          lineHeight: '1.4',
          marginBottom: '8px',
        }}>
          {QUESTIONS[qNum - 1]}
        </h2>

        {/* Follow-up hint */}
        {followup && stage !== 'extracting' && (
          <p style={{
            fontFamily: "'DM Sans', system-ui",
            fontSize: '13px',
            color: '#9C928A',
            fontStyle: 'italic',
            marginBottom: '12px',
          }}>
            {followup}
          </p>
        )}

        {/* Entity animation area */}
        {visibleEntities.length > 0 && (
          <div style={{ margin: '16px 0' }}>
            <p style={{
              fontFamily: "'DM Sans', system-ui",
              fontSize: '11px',
              color: '#9C928A',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
              marginBottom: '8px',
            }}>
              Tracking for you...
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {visibleEntities.map(e => (
                <EntityChip
                  key={e.name}
                  entity={e}
                  visible={!animatingEntities.has(e.name)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Processing indicator */}
        {isProcessing && (
          <p style={{
            fontFamily: "'DM Sans', system-ui",
            fontSize: '13px',
            color: '#9C928A',
            fontStyle: 'italic',
            margin: '16px 0',
          }}>
            {stage === 'extracting' ? 'Analysing your answer...' : 'Building your profile...'}
          </p>
        )}

        {/* Input */}
        {!isProcessing && (
          <>
            <textarea
              ref={textareaRef}
              value={answer}
              onChange={e => setAnswer(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSubmit()
              }}
              placeholder="Your answer..."
              rows={3}
              style={{
                width: '100%',
                minHeight: '80px',
                padding: '12px 0',
                border: 'none',
                borderBottom: '1.5px solid #DDD8D0',
                background: 'transparent',
                fontFamily: "'DM Sans', system-ui",
                fontSize: '15px',
                color: '#1A1614',
                outline: 'none',
                resize: 'vertical',
                lineHeight: '1.6',
                marginTop: '20px',
              }}
              onFocus={e => (e.target.style.borderBottom = '1.5px solid #8B1A1A')}
              onBlur={e => (e.target.style.borderBottom = '1.5px solid #DDD8D0')}
            />
            {error && (
              <p style={{
                fontFamily: "'DM Sans', system-ui",
                fontSize: '13px',
                color: '#8B1A1A',
                marginTop: '8px',
              }}>
                {error}
              </p>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button
                onClick={handleSubmit}
                disabled={!answer.trim()}
                style={{
                  background: 'none',
                  border: 'none',
                  fontFamily: "'DM Sans', system-ui",
                  fontSize: '14px',
                  fontWeight: 500,
                  color: answer.trim() ? '#8B1A1A' : '#9C928A',
                  cursor: answer.trim() ? 'pointer' : 'default',
                  letterSpacing: '0.03em',
                  padding: '8px 0',
                }}
              >
                Continue →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
