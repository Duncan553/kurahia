// Re-export shim. The screen itself lives in shared_ui because the station app
// renders the same one — reporting an incident is the identical job wherever
// you are standing, so there is one copy rather than two that drift.
//
// (The comment here used to point at WaiterTabDetailScreen.tsx for the
// explanation. That file was a station screen and no longer exists in this app,
// so the pointer went nowhere.)
export { default } from '@shared/screens/IncidentScreen'
