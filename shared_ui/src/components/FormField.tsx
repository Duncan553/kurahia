import { cloneElement, isValidElement } from 'react'
import type { ReactNode, ReactElement } from 'react'

export interface FormFieldProps {
  label: string
  /** Must match the `id` on the control passed as `children`. */
  htmlFor: string
  /** Validation message. Its presence is what puts the field into the error state. */
  error?: string
  help?: string
  children: ReactNode
  required?: boolean
}

/** Props FormField injects into its child control. */
interface InjectedProps {
  error?: boolean
  'aria-invalid'?: true
  'aria-describedby'?: string
}

export function FormField({ label, htmlFor, error, help, children, required }: FormFieldProps) {
  // Stable ids derived from htmlFor, so the <p> tags below can be pointed at.
  const errorId = `${htmlFor}-error`
  const helpId = `${htmlFor}-help`
  const showHelp = help && !error

  /**
   * Wire the child control to the label/error text.
   *
   * Why this clone exists: previously the caller had to remember to pass
   * `error` down to <Input> themselves — and NOT ONE of the 10 call sites did.
   * The red border on Input.tsx was dead code; a failed field showed the message
   * below but the box stayed grey. Injecting here fixes every call site at once
   * and means a new one can't forget.
   *
   * `aria-describedby` is the other half: without it a screen reader announces
   * the input and the error as two unrelated things, so the user hears "Phone
   * Number, edit text" and never learns WHY it was rejected.
   */
  // Only inject into COMPONENT children (Input, Select, …), never a raw DOM
  // element. `error` is not a real HTML attribute, so cloning it onto a plain
  // <div> or <textarea> would trip React's "unknown prop" console warning.
  const isComponent = isValidElement(children) && typeof children.type !== 'string'

  const control = isComponent
    ? cloneElement(children as ReactElement<InjectedProps>, {
        // Boolean flag — drives Input/Select's red border styling.
        error: Boolean(error),
        // Omit rather than render ="false", same reasoning as Button's aria props.
        'aria-invalid': error ? true : undefined,
        'aria-describedby': error ? errorId : showHelp ? helpId : undefined,
      })
    : children

  return (
    <div className="space-y-1.5">
      <label
        htmlFor={htmlFor}
        className="block text-sm font-semibold text-ink-secondary"
      >
        {label}
        {required && <span className="text-status-failed ml-1">*</span>}
      </label>
      {control}
      {error && (
        // role="alert" so the message is announced the moment validation fails,
        // not only when the user happens to tab back onto the field.
        <p id={errorId} role="alert" className="text-xs text-status-failed font-medium">
          {error}
        </p>
      )}
      {showHelp && (
        <p id={helpId} className="text-xs text-ink-tertiary">{help}</p>
      )}
    </div>
  )
}
