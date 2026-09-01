import type { ComponentPropsWithoutRef } from 'react'

/**
 * Avatar — a person's face, or their initials when there is no photo.
 *
 * Every staff profile shows one. Guests do not get one: the resort holds a
 * name and a phone for a guest, not a portrait, and inventing a face for
 * somebody who never gave us one is not a feature.
 *
 * The fallback is deliberately NOT a grey silhouette. Twelve identical grey
 * heads on a roster tell you nothing; initials in a stable colour let someone
 * find a person at a glance, which is the entire job of a face on a list.
 */

export type AvatarSize = 'sm' | 'md' | 'lg' | 'xl'

export interface AvatarProps extends Omit<ComponentPropsWithoutRef<'div'>, 'children'> {
  /** Full name. Drives both the initials and the colour. */
  name: string
  /** Uploaded image path, e.g. /images/profiles/ab12cd34.jpg. */
  photoPath?: string | null
  size?: AvatarSize
}

const SIZES: Record<AvatarSize, string> = {
  sm: 'h-8 w-8 text-xs',
  md: 'h-12 w-12 text-sm',
  lg: 'h-16 w-16 text-lg',
  xl: 'h-24 w-24 text-2xl',
}

/**
 * Fixed palette, picked by hashing the name — so the same person is the same
 * colour on every screen, on every device, forever. Random or index-based
 * colours would reshuffle whenever a list re-sorted, which defeats the point
 * of using colour to recognise someone.
 *
 * All eight are dark enough for white text to clear WCAG AA.
 */
const COLOURS = [
  'bg-emerald-700', 'bg-sky-700', 'bg-violet-700', 'bg-amber-700',
  'bg-rose-700', 'bg-teal-700', 'bg-indigo-700', 'bg-orange-700',
]

function colourFor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    // Same cheap string hash used everywhere; stable across JS engines.
    hash = (hash * 31 + name.charCodeAt(i)) | 0
  }
  return COLOURS[Math.abs(hash) % COLOURS.length]
}

/** "Amina Wekesa" -> "AW". "Otieno" -> "OT". Never more than two letters. */
export function initialsFor(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return '?'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
}

export function Avatar({ name, photoPath, size = 'md', className = '', ...rest }: AvatarProps) {
  const base = `${SIZES[size]} rounded-full shrink-0 overflow-hidden ` +
               `flex items-center justify-center font-semibold select-none`

  if (photoPath) {
    return (
      <img
        src={photoPath}
        alt={name}
        // A path can go stale — the row still holds it after the file is gone.
        // Hiding the broken image leaves the initials showing underneath rather
        // than the browser's torn-page icon on a staff roster.
        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        className={`${base} object-cover bg-slate-200 ${className}`}
      />
    )
  }

  return (
    <div
      className={`${base} ${colourFor(name)} text-white ${className}`}
      // Screen readers get the name; the initials are decoration on top of it.
      role="img"
      aria-label={name}
      {...rest}
    >
      {initialsFor(name)}
    </div>
  )
}
