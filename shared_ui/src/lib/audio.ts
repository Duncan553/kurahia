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
