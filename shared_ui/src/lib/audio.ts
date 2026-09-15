type Station = 'KITCHEN' | 'BAR' | 'GATE'

const TONE_MAP: Record<Station, string> = {
  KITCHEN: '/sounds/tone-kitchen.wav',
  BAR:     '/sounds/tone-bar.wav',
  GATE:    '/sounds/tone-gate.wav',
}

const THROTTLE_MS = 2000

let audioEnabled = false
let muted = false
let lastPlayTime = 0
const audioCache = new Map<string, HTMLAudioElement>()

export function enableAudio() { audioEnabled = true }
export function isAudioEnabled() { return audioEnabled }
export function setMuted(m: boolean) { muted = m }
export function isMuted() { return muted }

function getAudio(path: string): HTMLAudioElement {
  let el = audioCache.get(path)
  if (!el) {
    el = new Audio(path)
    el.preload = 'auto'
    audioCache.set(path, el)
  }
  return el
}

export async function playOrderAlert(station: Station): Promise<void> {
  if (!audioEnabled || muted) return

  const now = Date.now()
  if (now - lastPlayTime < THROTTLE_MS) return
  lastPlayTime = now

  const path = TONE_MAP[station]
  if (!path) return

  try {
    const audio = getAudio(path)
    audio.currentTime = 0
    await audio.play()
  } catch {
    // Browser blocked autoplay or audio unavailable — silent fail
  }
}

export async function playTestTone(station: Station = 'KITCHEN'): Promise<void> {
  const path = TONE_MAP[station]
  if (!path) return
  try {
    const audio = getAudio(path)
    audio.currentTime = 0
    await audio.play()
  } catch {
    // silent fail
  }
}


// ── The waiter's chime ────────────────────────────────────────────────────
//
// The kitchen has had a tone since the first build; the waiter had nothing.
// An item marked ready raised a card on the Tables screen and made no sound,
// which for a person carrying plates around a restaurant is the same as no
// alert at all — the food goes cold on the pass while the tablet sits on a
// counter showing a notice nobody is looking at.
//
// Synthesised rather than sampled, for two reasons: it must not sound like
// the kitchen's tone (they can be within earshot of each other, and an alert
// that means "collect" must not be confused with one that means "cook"), and
// a rising two-note figure is unmistakably "ready" where a buzzer is
// ambiguous. It also ships no file — nothing to fetch on a tablet that just
// lost the WiFi.
let readyCtx: AudioContext | null = null
let lastChimeTime = 0

export async function playReadyChime(): Promise<void> {
  if (!audioEnabled || muted) return

  // Same throttle as the station tones: a kitchen sending out four plates at
  // once should sound once, not four times.
  const now = Date.now()
  if (now - lastChimeTime < THROTTLE_MS) return
  lastChimeTime = now

  try {
    readyCtx = readyCtx ?? new (window.AudioContext
      || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    // A tab restored from background starts suspended; without this the chime
    // silently does nothing for the rest of the shift.
    if (readyCtx.state === 'suspended') await readyCtx.resume()

    const t0 = readyCtx.currentTime
    // C6 then G6 — up, not down. Rising reads as "come and get it".
    for (const [freq, at] of [[1046.5, 0], [1568.0, 0.13]] as const) {
      const osc  = readyCtx.createOscillator()
      const gain = readyCtx.createGain()
      osc.type = 'sine'
      osc.frequency.value = freq
      // Shaped envelope, not a square on/off — an abrupt gate clicks, and a
      // click on a cheap tablet speaker is what people mute.
      gain.gain.setValueAtTime(0.0001, t0 + at)
      gain.gain.exponentialRampToValueAtTime(0.28, t0 + at + 0.015)
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + at + 0.32)
      osc.connect(gain).connect(readyCtx.destination)
      osc.start(t0 + at)
      osc.stop(t0 + at + 0.34)
    }
  } catch {
    // No audio device, blocked autoplay, or a context the browser refused —
    // the visual alert still stands on its own.
  }
}
