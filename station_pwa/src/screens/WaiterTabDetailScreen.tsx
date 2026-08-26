// Re-export shim. This screen was byte-identical in employee_pwa and
// station_pwa; it now lives in shared_ui/src/screens. Kept at the old path so
// the router's lazy import didn't have to change.
export { default } from '@shared/screens/WaiterTabDetailScreen'
