// Re-export shim. The real client lives in shared_ui — employee_pwa and
// station_pwa had byte-identical copies, so it was hoisted there. This file
// stays so the ~65 existing `../lib/axios` imports keep working unchanged.
export * from '@shared/lib/axios'
export { default } from '@shared/lib/axios'
