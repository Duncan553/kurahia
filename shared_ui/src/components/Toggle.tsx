import { useId } from 'react'
import { motion } from 'framer-motion'

export interface ToggleProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  disabled?: boolean
  id?: string
}

// Track: w-11 (44px) × h-6 (24px)
// Thumb: 18×18px, 3px from each edge
// Off → x=3, On → x=23 (44 - 18 - 3 = 23)
const THUMB_ON_X = 23
const THUMB_OFF_X = 3

const SPRING = { type: 'spring' as const, stiffness: 400, damping: 30 }

export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
  id,
}: ToggleProps) {
  const generatedId = useId()
  const labelId = id ?? generatedId

  return (
    <div className="inline-flex items-center gap-3">
      {/* role="switch" + aria-checked is the correct pattern for toggles */}
      <motion.button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        disabled={disabled}
        onClick={() => { if (!disabled) onChange(!checked) }}
        animate={{
          backgroundColor: checked
            ? 'var(--color-primary-dark)'
            : 'var(--color-cream-alt)',
        }}
        transition={SPRING}
        className={[
          'relative w-11 h-6 rounded-full',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-1',
          disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
        ].join(' ')}
      >
        <motion.span
          aria-hidden="true"
          className="absolute top-[3px] left-0 w-[18px] h-[18px] rounded-full"
          animate={{
            x: checked ? THUMB_ON_X : THUMB_OFF_X,
            backgroundColor: checked ? 'white' : 'var(--color-ink-tertiary)',
          }}
          transition={SPRING}
        />
      </motion.button>

      {/* Label must always be visible — never a toggle without a label */}
      <span
        id={labelId}
        className={[
          'text-base text-ink-primary select-none',
          disabled ? 'opacity-50' : '',
        ].join(' ')}
      >
        {label}
      </span>
    </div>
  )
}
