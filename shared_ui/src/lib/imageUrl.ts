/**
 * Where an uploaded picture actually lives.
 *
 * The API stores photos and serves them back at /images/<folder>/<file>, so a
 * bare path like "/images/menu/ab12.jpg" has to be asked of the API, not of
 * whichever PWA happens to be drawing the screen. Resolving it against the
 * app's own origin is why the menu showed broken pictures: Vite answered the
 * request with index.html and the <img> silently failed.
 */
const API = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

export function imageUrl(path?: string | null): string | undefined {
  if (!path) return undefined
  // Already absolute (http, blob:, data:) — leave it alone.
  if (/^[a-z]+:/i.test(path)) return path
  return `${API.replace(/\/$/, '')}${path.startsWith('/') ? '' : '/'}${path}`
}
