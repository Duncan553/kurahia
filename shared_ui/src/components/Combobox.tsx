import { useState, useRef, useId, useEffect } from 'react'

export interface ComboboxProps {
  label: string
  value: string
  onChange: (value: string) => void
  suggestions: string[]           // list of known values to autocomplete from
  placeholder?: string
  disabled?: boolean
  error?: string
  allowFreeEntry?: boolean        // true (default): user can submit anything, not just suggestions
}

export function Combobox({
  label,
  value,
  onChange,
  suggestions,
  placeholder = 'Type or choose…',
  disabled = false,
  error,
  allowFreeEntry = true,
}: ComboboxProps) {
  const id = useId()
  const listId = `${id}-list`
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  // Filter suggestions by current input (case-insensitive prefix + substring)
  const filtered = value.trim()
    ? suggestions.filter((s) => s.toLowerCase().includes(value.toLowerCase()))
    : suggestions

  // Show dropdown when there are filtered options and input is focused
  const showList = open && filtered.length > 0

  function select(val: string) {
    onChange(val)
    setOpen(false)
    setActiveIdx(-1)
    inputRef.current?.focus()
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!showList) {
      if (e.key === 'ArrowDown') { setOpen(true); setActiveIdx(0) }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0 && activeIdx < filtered.length) {
        select(filtered[activeIdx])
      } else if (allowFreeEntry && value.trim()) {
        select(value.trim())
        setOpen(false)
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
      setActiveIdx(-1)
    }
  }

  // Scroll active item into view
  useEffect(() => {
    if (activeIdx >= 0 && listRef.current) {
      const item = listRef.current.children[activeIdx] as HTMLElement
      item?.scrollIntoView({ block: 'nearest' })
    }
  }, [activeIdx])

  return (
    <div className="flex flex-col gap-1 relative">
      <label htmlFor={id} className="text-sm font-medium text-ink-primary">
        {label}
      </label>

      <input
        ref={inputRef}
        id={id}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={activeIdx >= 0 ? `${id}-opt-${activeIdx}` : undefined}
        aria-autocomplete="list"
        type="text"
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActiveIdx(-1) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={handleKeyDown}
        className={[
          'w-full rounded border bg-cream-card text-ink-primary text-base',
          'px-3 py-2 min-h-[44px]',
          'focus:outline-none focus:border-primary-dark focus:ring-0',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          error ? 'border-status-failed' : 'border-ink-tertiary',
        ].join(' ')}
      />

      {showList && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          className="absolute top-full left-0 right-0 z-50 mt-0.5
            max-h-52 overflow-y-auto rounded border border-cream-alt
            bg-cream-card shadow-md"
        >
          {filtered.map((s, i) => (
            <li
              key={s}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === activeIdx}
              onMouseDown={() => select(s)}
              onMouseEnter={() => setActiveIdx(i)}
              className={[
                'px-3 py-2.5 text-sm cursor-pointer transition-colors',
                i === activeIdx
                  ? 'bg-primary-dark text-white'
                  : 'text-ink-primary hover:bg-cream-alt',
              ].join(' ')}
            >
              {s}
            </li>
          ))}
          {allowFreeEntry && value.trim() && !filtered.some((s) => s.toLowerCase() === value.toLowerCase()) && (
            <li
              role="option"
              aria-selected={false}
              onMouseDown={() => select(value.trim())}
              className="px-3 py-2.5 text-sm cursor-pointer text-ink-secondary
                italic border-t border-cream-alt hover:bg-cream-alt transition-colors"
            >
              Add "{value.trim()}"
            </li>
          )}
        </ul>
      )}

      {error && <p className="text-sm text-status-failed">{error}</p>}
    </div>
  )
}
