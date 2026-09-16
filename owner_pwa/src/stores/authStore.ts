// Re-export shim — see lib/axios.ts. Real store in shared_ui/src/stores.
//
// This file used to hold a SECOND, near-identical copy of the store, and that
// copy is what the owner app actually wrote its token into. shared_ui's axios
// reads the SHARED store, so the moment a shared screen was mounted here the
// request went out with no Authorization header at all, came back 401, and the
// interceptor signed the owner out. Clicking "Disputes" in the owner nav
// bounced straight to the login page, every time.
//
// The half-healed state was visible in main.tsx, which was already importing
// setAuthCacheReset from '@shared/stores/authStore' — registering the sign-out
// cache wipe on a store nothing in this app used. station_pwa and employee_pwa
// were shimmed onto the shared store long ago; the owner app was the one left
// behind, and nothing caught it because no shared screen was mounted here
// until now.
export * from '@shared/stores/authStore'
