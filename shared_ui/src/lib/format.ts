
/**
 * A role, written the way a person writes it.
 *
 * Roles are stored as `water_lead`, `spa_attendant`, `head_chef` — which is
 * the right shape for a database key and the wrong shape for a screen. The
 * owner's Staff list read "@francis.njoroge · water_lead · Water Activities",
 * and every other place a role appeared did the same. It is the resort's own
 * staff list; it should read like one.
 *
 * Deliberately not a lookup table: roles are data the owner can add to, so a
 * table would go stale the moment they created one. Underscores become spaces
 * and the first letter goes up — which is correct for every role they can name.
 */
export function roleLabel(role: string | null | undefined): string {
  if (!role) return ''
  const words = String(role).replace(/_/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}
