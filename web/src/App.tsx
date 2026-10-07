import {
  BarVisualizer,
  RoomAudioRenderer,
  SessionProvider,
  useAgent,
  useSession,
} from '@livekit/components-react'
import { TokenSource } from 'livekit-client'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import '@livekit/components-styles'
import './App.css'

const tokenEndpoint = import.meta.env.VITE_TOKEN_ENDPOINT_URL?.trim() ?? ''
const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY?.trim() ?? ''
const agentName = 'voice-ai-receptionist'

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'The call could not be started.'
}

function App() {
  const [challengeToken, setChallengeToken] = useState<string | null>(null)
  const [turnstileReady, setTurnstileReady] = useState(false)
  const [error, setError] = useState('')
  const [callStatus, setCallStatus] = useState<'ready' | 'connecting' | 'connected'>('ready')
  const [roomName, setRoomName] = useState(
    () => `smilecare-demo-${window.crypto.randomUUID()}`,
  )

  const handleVerified = useCallback((token: string) => {
    setChallengeToken(token)
    setError('')
    setCallStatus('ready')
  }, [])

  const handleChallengeError = useCallback(() => {
    setChallengeToken(null)
    setError('Human verification could not load. Please try again.')
  }, [])

  const handleChallengeExpired = useCallback(() => {
    setChallengeToken(null)
    setError('Human verification expired. Please complete it again.')
  }, [])

  const handleCallError = useCallback((message: string) => {
    setChallengeToken(null)
    setRoomName(`smilecare-demo-${window.crypto.randomUUID()}`)
    setCallStatus('ready')
    setError(message)
  }, [])

  const handleCallEnded = useCallback(() => {
    setChallengeToken(null)
    setRoomName(`smilecare-demo-${window.crypto.randomUUID()}`)
    setCallStatus('ready')
    setError('')
  }, [])

  useEffect(() => {
    const markReady = () => setTurnstileReady(true)
    if (window.turnstile) markReady()
    window.addEventListener('turnstile-ready', markReady)
    return () => window.removeEventListener('turnstile-ready', markReady)
  }, [])

  return (
    <div className="site-shell">
        <header className="topbar">
          <a className="brand" href="#top" aria-label="SmileCare home">
            <span className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 32 32" fill="none">
                <path
                  d="M16 27c-1.7-2-9-8.1-9-14.1A5.2 5.2 0 0 1 16 10a5.2 5.2 0 0 1 9 2.9C25 18.9 17.7 25 16 27Z"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <path
                  d="M12 17h8m-4-4v8"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span>smilecare</span>
          </a>
          <nav aria-label="Main navigation">
            <a href="#experience">Try the demo</a>
            <a href="#how-it-works">How it works</a>
          </nav>
          <a
            className="github-link"
            href="https://github.com/aJ23101/voice-ai-receptionist"
            target="_blank"
            rel="noreferrer"
          >
            View source
          </a>
        </header>

        <main id="top">
          <section className="hero">
            <div className="hero-copy">
              <div className="eyebrow">
                <span className="eyebrow-dot" />
                A voice AI receptionist, built for real calls
              </div>
              <h1>
                A better first
                <br />
                <span>hello.</span>
              </h1>
              <p className="hero-description">
                Meet the always-ready receptionist for SmileCare Dental. Ask a
                question, check an appointment time, or hear how a thoughtful
                voice experience can feel.
              </p>
              <a className="text-link" href="#experience">
                Talk to the receptionist
              </a>
              <div className="hero-proof">
                <span className="proof-icon" aria-hidden="true">
                  <svg viewBox="0 0 20 20" fill="none">
                    <path
                      d="m5 10 3.2 3.2L15.5 6"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                <span>Checks real availability before offering a time</span>
              </div>
            </div>

            <section
              className="demo-card"
              id="experience"
              aria-labelledby="demo-title"
            >
              <div className="demo-card-top">
                <div>
                  <p className="card-kicker">LIVE VOICE DEMO</p>
                  <h2 id="demo-title">Say hello to SmileCare</h2>
                </div>
                <span className={`status-pill ${callStatus === 'connected' ? 'is-live' : ''}`}>
                  <span />
                  {callStatus === 'connected'
                    ? 'Connected'
                    : callStatus === 'connecting'
                      ? 'Connecting'
                      : challengeToken
                        ? 'Verified'
                        : 'Ready'}
                </span>
              </div>

              {challengeToken ? (
                <DemoCall
                  challengeToken={challengeToken}
                  roomName={roomName}
                  onStatusChange={setCallStatus}
                  onEnded={handleCallEnded}
                  onError={handleCallError}
                />
              ) : (
                <>
                  <div className="voice-stage">
                    <div className="orb-wrap" aria-hidden="true">
                      <div className="orb-ring orb-ring-one" />
                      <div className="orb-ring orb-ring-two" />
                      <div className="voice-orb">
                        <svg viewBox="0 0 48 48" fill="none">
                          <path
                            d="M24 8a5 5 0 0 0-5 5v10a5 5 0 0 0 10 0V13a5 5 0 0 0-5-5Z"
                            stroke="currentColor"
                            strokeWidth="2"
                          />
                          <path
                            d="M14 22v1a10 10 0 0 0 20 0v-1M24 33v7m-6 0h12"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                          />
                        </svg>
                      </div>
                    </div>
                    <p className="voice-status" aria-live="polite">
                      Your next conversation starts here
                    </p>
                    <div className="voice-hint">
                      <span className="hint-line" />
                      <span>Clear, natural, and ready when you are</span>
                      <span className="hint-line" />
                    </div>
                  </div>

                  <div className="verification">
                    {tokenEndpoint && turnstileSiteKey ? (
                      turnstileReady ? (
                        <TurnstileChallenge
                          siteKey={turnstileSiteKey}
                          onVerified={handleVerified}
                          onError={handleChallengeError}
                          onExpired={handleChallengeExpired}
                        />
                      ) : (
                        <p className="setup-notice">Loading human verification...</p>
                      )
                    ) : (
                      <p className="setup-notice">
                        The live demo is being configured. Please check back soon.
                      </p>
                    )}
                  </div>

                  {error && (
                    <p className="error-message" role="alert">
                      {error}
                    </p>
                  )}

                  <div className="demo-actions">
                    <button className="call-button" disabled>
                      <span className="button-icon" aria-hidden="true">
                        <svg viewBox="0 0 20 20" fill="none">
                          <path
                            d="M10 3a3 3 0 0 0-3 3v4a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z"
                            stroke="currentColor"
                            strokeWidth="1.6"
                          />
                          <path
                            d="M4 9v1a6 6 0 0 0 12 0V9m-6 7v2m-4 0h8"
                            stroke="currentColor"
                            strokeWidth="1.6"
                            strokeLinecap="round"
                          />
                        </svg>
                      </span>
                      Complete verification to begin
                    </button>
                    <p className="privacy-note">
                      Your browser will ask for microphone access.
                    </p>
                  </div>
                </>
              )}
              <div className="demo-disclaimer">
                <span aria-hidden="true">i</span>
                Use fictional details only. This demo can create calendar
                events; please do not share real patient or medical information.
              </div>
            </section>

            <div className="floating-note note-one">
              <span className="note-icon note-icon-green" aria-hidden="true">
                <svg viewBox="0 0 20 20" fill="none">
                  <path
                    d="M10 3v14m-5-9 5-5 5 5"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              <span>
                <strong>One question at a time</strong>
                <small>A more natural conversation</small>
              </span>
            </div>
            <div className="floating-note note-two">
              <span className="note-icon note-icon-peach" aria-hidden="true">
                <svg viewBox="0 0 20 20" fill="none">
                  <path
                    d="M10 2.8 16 5v4.2c0 3.7-2.5 6.2-6 8-3.5-1.8-6-4.3-6-8V5l6-2.2Z"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                  <path
                    d="m7.5 9.8 1.7 1.7 3.4-3.6"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              <span>
                <strong>Never guesses availability</strong>
                <small>Live calendar checks, every time</small>
              </span>
            </div>
          </section>

          <section className="how-section" id="how-it-works">
            <div className="section-heading">
              <p className="card-kicker">THOUGHTFULLY ENGINEERED</p>
              <h2>Helpful by design. Honest by default.</h2>
              <p>
                Real-time voice, carefully scoped tools, and safe fallbacks work
                together to make every call feel considered.
              </p>
            </div>
            <div className="feature-grid">
              <article className="feature-card">
                <span className="feature-number">01</span>
                <h3>Understands spoken time</h3>
                <p>
                  Handles phrases like "half past two" and "tomorrow" without
                  guessing at a date or an off-grid slot.
                </p>
              </article>
              <article className="feature-card">
                <span className="feature-number">02</span>
                <h3>Checks before it offers</h3>
                <p>
                  Reads live free/busy data, then checks again at booking time
                  to catch last-second changes.
                </p>
              </article>
              <article className="feature-card">
                <span className="feature-number">03</span>
                <h3>Knows when to hand off</h3>
                <p>
                  For medical advice, cancellations, and unknown details, it
                  sets a clear boundary and asks staff to follow up.
                </p>
              </article>
            </div>
          </section>
        </main>

        <footer className="footer">
          <a className="brand footer-brand" href="#top">
            <span className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 32 32" fill="none">
                <path
                  d="M16 27c-1.7-2-9-8.1-9-14.1A5.2 5.2 0 0 1 16 10a5.2 5.2 0 0 1 9 2.9C25 18.9 17.7 25 16 27Z"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <path
                  d="M12 17h8m-4-4v8"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span>smilecare</span>
          </a>
          <p>Portfolio demonstration. SmileCare Dental is a fictional clinic.</p>
          <a
            href="https://github.com/aJ23101/voice-ai-receptionist"
            target="_blank"
            rel="noreferrer"
          >
            Built with LiveKit Agents
          </a>
        </footer>
    </div>
  )
}

interface TurnstileChallengeProps {
  siteKey: string
  onVerified: (token: string) => void
  onError: () => void
  onExpired: () => void
}

function TurnstileChallenge({
  siteKey,
  onVerified,
  onError,
  onExpired,
}: TurnstileChallengeProps) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current || !window.turnstile) return

    const widgetId = window.turnstile.render(container.current, {
      sitekey: siteKey,
      action: 'voice-demo',
      callback: onVerified,
      'expired-callback': onExpired,
      'error-callback': onError,
    })
    return () => window.turnstile?.remove(widgetId)
  }, [onError, onExpired, onVerified, siteKey])

  return (
    <div
      className="turnstile-widget"
      ref={container}
      aria-label="Human verification"
    />
  )
}

interface DemoCallProps {
  challengeToken: string
  roomName: string
  onStatusChange: (status: 'ready' | 'connecting' | 'connected') => void
  onEnded: () => void
  onError: (message: string) => void
}

function DemoCall({
  challengeToken,
  roomName,
  onStatusChange,
  onEnded,
  onError,
}: DemoCallProps) {
  const [starting, setStarting] = useState(false)
  const [connected, setConnected] = useState(false)
  const [ending, setEnding] = useState(false)
  const [error, setError] = useState('')

  const tokenSource = useMemo(
    () =>
      TokenSource.custom(async (options) => {
        if (!tokenEndpoint) {
          throw new Error('The demo connection service is not configured yet.')
        }

        const response = await fetch(tokenEndpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Turnstile-Token': challengeToken,
          },
          body: JSON.stringify({ room_name: options.roomName }),
        })
        const payload = (await response.json()) as {
          server_url?: string
          participant_token?: string
          detail?: string
        }

        if (!response.ok || !payload.server_url || !payload.participant_token) {
          throw new Error(payload.detail ?? 'Could not connect to the demo.')
        }

        return {
          serverUrl: payload.server_url,
          participantToken: payload.participant_token,
        }
      }),
    [challengeToken],
  )
  const session = useSession(tokenSource, { agentName, roomName })

  async function startCall() {
    setError('')
    setStarting(true)
    onStatusChange('connecting')
    try {
      await session.start()
      setConnected(true)
      onStatusChange('connected')
    } catch (startError) {
      onError(getErrorMessage(startError))
    } finally {
      setStarting(false)
    }
  }

  async function endCall() {
    setEnding(true)
    setError('')
    try {
      await session.end()
      onEnded()
    } catch (endError) {
      setError(getErrorMessage(endError))
      setEnding(false)
    }
  }

  return (
    <SessionProvider session={session}>
      <div className={`voice-stage ${connected ? 'is-active' : ''}`}>
        <div className="orb-wrap" aria-hidden="true">
          <div className="orb-ring orb-ring-one" />
          <div className="orb-ring orb-ring-two" />
          <div className="voice-orb">
            <svg viewBox="0 0 48 48" fill="none">
              <path
                d="M24 8a5 5 0 0 0-5 5v10a5 5 0 0 0 10 0V13a5 5 0 0 0-5-5Z"
                stroke="currentColor"
                strokeWidth="2"
              />
              <path
                d="M14 22v1a10 10 0 0 0 20 0v-1M24 33v7m-6 0h12"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </div>
        </div>
        <p className="voice-status" aria-live="polite">
          {connected ? (
            <AgentStatus />
          ) : starting ? (
            'Connecting you now...'
          ) : (
            'Ready when you are'
          )}
        </p>
        {connected ? (
          <AgentVisualizer />
        ) : (
          <div className="voice-hint">
            <span className="hint-line" />
            <span>Clear, natural, and ready when you are</span>
            <span className="hint-line" />
          </div>
        )}
      </div>

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      <div className="demo-actions">
        {connected ? (
          <button
            className="call-button end-button"
            disabled={ending}
            onClick={endCall}
          >
            End conversation
          </button>
        ) : (
          <button
            className="call-button"
            disabled={starting}
            onClick={startCall}
          >
            <span className="button-icon" aria-hidden="true">
              <svg viewBox="0 0 20 20" fill="none">
                <path
                  d="M10 3a3 3 0 0 0-3 3v4a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z"
                  stroke="currentColor"
                  strokeWidth="1.6"
                />
                <path
                  d="M4 9v1a6 6 0 0 0 12 0V9m-6 7v2m-4 0h8"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            {starting ? 'Connecting...' : 'Start conversation'}
          </button>
        )}
        <p className="privacy-note">
          Your browser will ask for microphone access.
        </p>
      </div>
      <RoomAudioRenderer />
    </SessionProvider>
  )
}

function AgentStatus() {
  const agent = useAgent()
  const labels: Record<string, string> = {
    listening: 'Listening. How can I help?',
    thinking: 'One moment while I check that for you.',
    speaking: 'SmileCare is speaking.',
    initializing: 'Getting your call ready...',
    idle: 'You are connected. Go ahead whenever you are ready.',
  }

  return <>{labels[agent.state] ?? 'You are connected. Go ahead whenever you are ready.'}</>
}

function AgentVisualizer() {
  const agent = useAgent()

  return (
    <div className="visualizer" aria-label="Live audio activity">
      <BarVisualizer
        track={agent.microphoneTrack}
        state={agent.state}
        barCount={31}
      />
    </div>
  )
}

export default App
