export { Button } from './components/Button'
export type { ButtonProps, ButtonVariant, ButtonSize } from './components/Button'

export { Input } from './components/Input'
export type { InputProps } from './components/Input'

export { Select } from './components/Select'
// SelectOption was also re-exported here, but no such type has ever existed in
// Select.tsx — Select takes plain <option> children. It was a phantom export.
export type { SelectProps } from './components/Select'

export { Toggle } from './components/Toggle'
export type { ToggleProps } from './components/Toggle'

export { Card } from './components/Card'
export type { CardProps, CardPadding, CardShadow } from './components/Card'

export { Modal } from './components/Modal'
export type { ModalProps, ModalSize } from './components/Modal'

export { Drawer } from './components/Drawer'
export type { DrawerProps } from './components/Drawer'

export { ToastContainer } from './components/Toast'
export { useToastStore } from './stores/toastStore'
export type { Toast, ToastType } from './stores/toastStore'

export { StatusBadge } from './components/StatusBadge'
export type { StatusBadgeProps, StatusValue, BadgeSize, BadgeVariant } from './components/StatusBadge'

export { Skeleton } from './components/Skeleton'
export type { SkeletonProps, SkeletonVariant } from './components/Skeleton'

export { Spinner } from './components/Spinner'
export type { SpinnerProps, SpinnerSize, SpinnerColor } from './components/Spinner'

export { EmptyState } from './components/EmptyState'
export type { EmptyStateProps } from './components/EmptyState'

export { Logo } from './components/Logo'

export { Combobox } from './components/Combobox'
export type { ComboboxProps } from './components/Combobox'

export { OfflineBanner } from './components/OfflineBanner'

export { InstallPrompt } from './components/InstallPrompt'
export type { InstallPromptProps } from './components/InstallPrompt'

export { SearchInput } from './components/SearchInput'
export type { SearchInputProps } from './components/SearchInput'

export { ErrorBoundary } from './components/ErrorBoundary'

// ── Icon system (replaces raw emoji literals across all 3 PWAs) ──
export { Icon } from './components/Icon'
export type { IconProps, IconName } from './components/Icon'

// ── Shared app plumbing (identical in employee_pwa + station_pwa, hoisted here) ──
// owner_pwa deliberately keeps its OWN axios/authStore — those genuinely differ.
export { default as api } from './lib/axios'
export { useAuthStore } from './stores/authStore'
export type { AuthUser } from './stores/authStore'
export * from './lib/audio'

// ── Shared screens ──
// These three were byte-identical copies in employee_pwa and station_pwa. Each
// app keeps a one-line re-export at its old path so routers didn't have to change.
export { default as WaiterTabDetailScreen } from './screens/WaiterTabDetailScreen'
export { default as IncidentScreen } from './screens/IncidentScreen'
// StationQueues exports two named screens, not a default — one board component
// parameterised by station, surfaced as Kitchen and Bar.
export { KitchenQueueScreen, BarQueueScreen } from './screens/StationQueues'


// ── Glass surfaces ──
export { GlassCard } from './components/GlassCard'
export type { GlassCardProps, GlassIntensity } from './components/GlassCard'

// ── Motion presets ──
export { slideUp, fadeScale, slideFromRight } from './motion/presets'

// ── Help system ──
export { HelpTooltip } from './components/HelpTooltip'
export type { HelpTooltipProps } from './components/HelpTooltip'

// ── Form system ──
export { FormField } from './components/FormField'
export type { FormFieldProps } from './components/FormField'
export { FormSection } from './components/FormSection'
export type { FormSectionProps } from './components/FormSection'
