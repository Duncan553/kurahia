# shared_ui

Code shared between `employee_pwa` and `owner_pwa`.

Both PWAs import from here via relative paths (e.g. `../../shared_ui/components/Button`).

As of Phase F-0 this folder is empty. Population begins in:
- **Phase F-1** — design tokens (Tailwind theme config, colour constants, type scale)
- **Phase F-2** — component primitives (Button, Input, Select, Toggle)
- **Phase F-3** — containers (Card, Modal, Drawer, Toast)
- **Phase F-4** — feedback components (StatusBadge, Skeleton, Spinner, EmptyState)
- **Phase F-6** — domain composites (BookingCard, AlertCard, KitchenTicket, etc.)

## Structure

```
shared_ui/
├── components/   ← 17 shared components (F-2 through F-6)
├── styles/       ← design tokens, Tailwind theme config (F-1)
└── utils/        ← shared helpers (formatters, axios instance, auth interceptor)
```

## Design tokens reference

Colour system, typography, and animation rules are specified in `docs/FRONTEND_DESIGN.md`
Sections 2–3 and 14. Tokens are encoded in `styles/tokens.ts` (created at F-1).
