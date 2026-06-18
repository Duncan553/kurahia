import { useState, useEffect, useRef, useCallback } from 'react'

export interface SearchInputProps {
  value: string
  onChange: (query: string) => void
  placeholder?: string
  label?: string
  debounceMs?: number
}

export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  label = 'Search',
  debounceMs = 300,
}: SearchInputProps) {
  const [local, setLocal] = useState(value)
  const inputRef = useRef<HTMLInputElement>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => { setLocal(value) }, [value])

  const emitDebounced = useCallback((v: string) => {
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => onChange(v), debounceMs)
  }, [onChange, debounceMs])

  useEffect(() => () => clearTimeout(timerRef.current), [])

  function handleChange(v: string) {
    setLocal(v)
    emitDebounced(v)
  }

  function clear() {
    setLocal('')
    onChange('')
    inputRef.current?.focus()
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) {
        e.preventDefault()
        inputRef.current?.focus()
      }
      if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        clear()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="relative">
      <label htmlFor="search-input" className="sr-only">{label}</label>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"
        className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-tertiary pointer-events-none">
        <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
      <input
        ref={inputRef}
        id="search-input"
        type="search"
        value={local}
        onChange={e => handleChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        className="w-full rounded-xl border border-cream-alt bg-cream-card pl-9 pr-8 py-2.5
          text-sm text-ink-primary placeholder:text-ink-tertiary/60
          focus:outline-none focus:border-primary-dark transition-colors"
      />
      {local && (
        <button onClick={clear} aria-label="Clear search"
          className="absolute right-2.5 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full
            bg-cream-alt flex items-center justify-center text-ink-tertiary
            hover:bg-ink-tertiary hover:text-white transition-colors">
          <span aria-hidden="true" className="text-xs leading-none font-bold">×</span>
        </button>
      )}
    </div>
  )
}
