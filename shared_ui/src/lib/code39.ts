/**
 * Code 39 barcode — the encoding, nothing more.
 *
 * Why this and not a QR: the gate already looks a band up by typing its number.
 * A KSh 3,000 USB/Bluetooth barcode scanner behaves exactly like a keyboard —
 * it "types" what it reads and presses Enter — so a Code 39 barcode works with
 * the lookup screen that already exists, with no camera, no permissions and no
 * library. Forty lines beat a dependency.
 *
 * How Code 39 works: every character is nine elements wide — bar, space, bar,
 * space, … starting and ending on a bar. Exactly three of the nine are WIDE,
 * which is where the name comes from. A wide element is 2-3× a narrow one; the
 * scanner reads the pattern, not the absolute size, so the printout survives
 * being scaled. Every barcode is wrapped in the * character, which is the
 * start/stop marker and never appears in the data.
 */

// 'n' = narrow, 'w' = wide. Index 0 is a bar, 1 a space, 2 a bar, and so on.
const PATTERNS: Record<string, string> = {
  '0': 'nnnwwnwnn', '1': 'wnnwnnnnw', '2': 'nnwwnnnnw', '3': 'wnwwnnnnn',
  '4': 'nnnwwnnnw', '5': 'wnnwwnnnn', '6': 'nnwwwnnnn', '7': 'nnnwnnwnw',
  '8': 'wnnwnnwnn', '9': 'nnwwnnwnn', '-': 'nnnwnnwnw', '*': 'nnwnwwnwn',
}

export interface Bar { bar: boolean; wide: boolean }

/**
 * Turn a string of digits into the bars to draw, start/stop markers included.
 * Anything the table does not know is dropped rather than drawn wrong — a
 * barcode that lies is worse than no barcode.
 */
export function code39(value: string): Bar[] {
  const chars = ['*', ...value.toUpperCase().split('').filter(c => c in PATTERNS), '*']
  const out: Bar[] = []
  chars.forEach((ch, i) => {
    PATTERNS[ch].split('').forEach((el, idx) => {
      out.push({ bar: idx % 2 === 0, wide: el === 'w' })
    })
    // One narrow space between characters — part of the spec, not decoration.
    if (i < chars.length - 1) out.push({ bar: false, wide: false })
  })
  return out
}
