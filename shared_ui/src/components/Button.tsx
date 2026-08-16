import { motion } from 'framer-motion'
import type { ComponentPropsWithoutRef } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

// HTML drag + animationStart handlers conflict with Framer Motion's own signatures.
type HTMLMotionConflicts =
| 'onDrag' | 'onDragEnd' | 'onDragStart'
| 'onDragEnter' | 'onDragExit' | 'onDragLeave' | 'onDragOver'
| 'onDragCapture' | 'onDragEndCapture' | 'onDragStartCapture'
| 'onDragEnterCapture' | 'onDragExitCapture' | 'onDragLeaveCapture' | 'onDragOverCapture'
| 'onAnimationStart' | 'onAnimationStartCapture'

export interface ButtonProps extends Omit<ComponentPropsWithoutRef<'button'>, HTMLMotionConflicts> {
 variant?: ButtonVariant
 size?: ButtonSize
 loading?: boolean
}

const VARIANT: Record<ButtonVariant, string> = {
 primary: 'bg-gradient-to-b from-primary-main to-primary-dark text-white shadow-[0_4px_14px_rgba(250,92,41,0.3)] hover:from-primary-light hover:to-primary-main hover:shadow-[0_6px_20px_rgba(250,92,41,0.4)] border border-primary-main/30',
 secondary: 'bg-white/8 text-ink-primary border border-white/15 backdrop-blur-md hover:bg-white/14 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]',
 ghost: 'bg-transparent text-white/50 hover:text-primary-main hover:bg-primary-main/8 hover:shadow-[0_0_12px_rgba(250,92,41,0.1)]',
 danger: 'bg-gradient-to-b from-red-500 to-red-700 text-white shadow-[0_4px_14px_rgba(239,68,68,0.3)] hover:from-red-400 hover:to-red-600 border border-red-500/30',
}

const SIZE: Record<ButtonSize, string> = {
 sm: 'text-sm px-4 py-1.5 min-h-[44px] rounded-xl',
 md: 'text-base px-5 py-2.5 min-h-[44px] rounded-xl',
 lg: 'text-base px-7 py-3.5 min-h-[44px] rounded-xl',
}

function Spinner() {
 return (
 <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
 <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
 <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
 </svg>
 )
}

export function Button({
 variant = 'primary',
 size = 'md',
 loading = false,
 disabled = false,
 children,
 className = '',
 ...rest
}: ButtonProps) {
 const isDisabled = disabled || loading

 return (
 <motion.button
 whileTap={{ scale: 0.97 }}
 disabled={isDisabled}
 className={[
 'inline-flex items-center justify-center gap-2 font-semibold transition-all duration-200',
 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main focus-visible:ring-offset-2 focus-visible:ring-offset-cream-card',
 'disabled:opacity-50 disabled:cursor-not-allowed',
 VARIANT[variant],
 SIZE[size],
 className,
 ].join(' ')}
 {...rest}
 >
 {loading && (
 <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
 <Spinner />
 </span>
 )}
 <span className={loading ? 'opacity-0' : ''}>{children}</span>
 </motion.button>
 )
}
