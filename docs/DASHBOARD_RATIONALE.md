# Dashboard Rationale — Every Feature Justified

> Every feature earns its place with a reason. If it can't be justified for the role, it doesn't belong.

---

## Visual Language (all dashboards)

Deep dimensional glass (VisionOS spatial). Floating frosted panels with depth, soft layered shadows, light-catching top edges. Left-side nav rail. Personal greeting headers. Numbers always visible as headlines; charts augment, never replace. Colors are FREE per dashboard — modern, not old palette-bound. WCAG AA enforced (measure, don't assume). Heavy Framer Motion everywhere.

Reference targets: `docs/references/visionos-home.jpeg`, `docs/references/management-dashboard.jpeg`, `docs/references/audi-visionos.jpeg`.

---

## 1. OWNER DASHBOARD

**Role:** The owner checks the pulse of the resort 1-3x daily. They're NOT operating — they're observing. They want: "Is today healthy? Is money flowing? Are problems handled? Am I making or losing?"

**BELONGS (justified):**
| Feature | Why |
|---------|-----|
| Revenue today (exact KSh + area chart + delta) | The first thing they check — "how much money came in today?" |
| Payment method donut (cash/M-Pesa/card/bank) | "Where is the money coming from?" — critical for reconciliation confidence |
| Budget burn per dept (radial rings) | "Is any department overspending?" — early warning before month-end surprise |
| Staff on duty (count + names) | "Who's working right now?" — accountability |
| Judge alerts (count + severity) | "Are there anomalies I need to investigate?" |
| Bookings (arrivals/departures today) | "What's the occupancy picture?" |
| Feedback (avg rating + trend) | "Are guests happy or complaining?" |
| Reconciliation health | "Is today's money accounted for, or is something unreconciled?" — ties to auto-close |
| Low stock alerts | "Is the kitchen about to run out of something?" |
| Calendar/events | "What's coming up that I should know about?" |

**REMOVED (justified):**
| Feature | Why removed |
|---------|------------|
| Clock-in | Owner doesn't clock in. They own the place. |
| Inventory management | Owner doesn't count stock. Manager does. Owner sees alerts only. |
| Menu management | Owner doesn't edit the menu. Head chef + manager do. |
| Staff creation | Owner can do this, but it's in Settings, not the observation surface. |

**Arrangement:** Greeting header → hero revenue tile (full-width, area chart + donut) → 3-col grid of metric tiles → reconciliation health bar at bottom.

**Colors:** Dark glass panels (#1a1a2e → #16213e gradient bg), white/cream text, emerald accents for positive, amber for warnings.

---

## 2. MANAGER HUB

**Role:** The manager runs daily operations. They create shifts, manage inventory, assign tablets, approve purchases, handle attendance. They're the operational brain.

**BELONGS:**
| Feature | Why |
|---------|-----|
| Overview landing (upcoming events, calendar) | "What's happening today/this week that I need to prepare for?" |
| Schedule (create shifts for everyone) | Core daily task — "who's working when?" |
| Inventory (stock BEHAVIOR per dept, not raw counts) | "Which departments are burning through stock? Which are overstocked?" — clickable grids with high/low/over visualization |
| Per-dept budget/balance | "Am I within budget per department?" |
| Staff creation + tablet assignment | "New hire? Here. Assign this tablet to this person." |
| Pending approvals (purchases, leave) | "What decisions are waiting for me?" |

**REMOVED:**
| Feature | Why removed |
|---------|------------|
| Clock-in tile | Manager may clock in, but it's a utility in the nav, not a hub tile. The hub is for MANAGING, not personal tasks. |
| Services tile | Does nothing meaningful. |
| Revenue (detailed) | That's the owner's observation. Manager gets a lightweight revenue summary at most. |

**Arrangement:** Left nav rail → calendar/events overview (wide) → inventory behavior grid (2-col, click to expand per dept) → pending approvals sidebar → staff/shifts section.

---

## 3. HEAD CHEF DASHBOARD

**Role:** The head chef manages recipes, watches ingredient costs, and adds menu items. They don't manage staff or budgets — that's the manager.

**BELONGS:**
| Feature | Why |
|---------|-----|
| Recipe management (enter recipes + quantity) | Core task — "what goes into each dish and how much?" |
| Variance reports | "Are we using more ingredients than the recipes say?" — catches waste/theft |
| Weekly reports | "How did the kitchen perform this week?" |
| Add/edit menu items | "New seasonal dish? Add it here with recipe." |
| Kitchen stock overview (read-only) | "What do I have to work with today?" |

**REMOVED:**
| Feature | Why removed |
|---------|------------|
| Shift management | Manager's job |
| Budget | Manager's job |
| Clock-in | Separate utility |
| POS/ordering | Waiter's job |

---

## 4. KITCHEN STATION

**Role:** The kitchen display tablet sits in the kitchen. Kitchen staff see incoming orders and work through them. They're cooking, not managing.

**BELONGS:**
| Feature | Why |
|---------|-----|
| Order queue (receipt-style cards) | "What do I need to cook right now?" — animated, scannable, large text |
| Stock behavior view (own dept) | "Am I about to run out of something mid-service?" |
| "Almost over" warning | FIRES BEFORE selling out-of-stock — prevents selling what can't be made |
| Recipes reference icon | "How much garlic in the burger again?" — quick reference, not management |
| Always-visible clock | Kitchen needs to know the time at a glance. No phones in kitchen. |
| Audio alert on new order | "Ding — new ticket" |

**REMOVED:**
| Feature | Why removed |
|---------|------------|
| Inventory management | Manager manages. Kitchen VIEWS own stock. |
| Schedule | Manager's screen |
| Clock-in | Not on the station tablet |
| Staff management | Not kitchen's job |
| Services | Meaningless here |
| Mail/notifications | Not during service |

---

## 5. BAR STATION — identical to Kitchen, bar-scoped.

---

## 6. SPA & GYM

**Role:** Spa/gym staff sell services (massages, personal training, gym access) and observe their own stock (oils, towels, products). They request restocking from the manager.

**BELONGS:**
| Feature | Why |
|---------|-----|
| POS (sell services, charge to tab/band) | Core task — "guest wants a massage, charge it" |
| Own stock behavior view (read-only) | "Am I low on massage oil?" |
| Request-to-manager box | "I need more oil — submit request" |
| Spa/gym photos (ambience) | Makes the interface feel like it belongs in a spa |

**REMOVED:** Everything else — inventory management, menu editing, shifts, budgets, reports. Manager handles all of that.

---

## 7. WATER ACTIVITIES — same pattern as Spa (POS + stock view + request). Jet skis, kayaking, boat rides, fishing.

---

## 8. WAITER

**Role:** The waiter takes orders from guests and serves food. They're on the floor, moving fast, on their feet.

**BELONGS:**
| Feature | Why |
|---------|-----|
| Order screen (the redesigned two-pane from Chunk 5.3) | Core task — "take this order" |
| "Show Menu or Straight to Order?" prompt on table open | Some guests want to browse, some know what they want |
| Stock VIEW button | "Is the tilapia still available?" — view only, not manage |
| Band check (on tab) | "Does this guest have a wristband?" — required before selling |

**REMOVED:**
| Feature | Why removed |
|---------|------------|
| Inventory management | Not waiter's job |
| Clock-in tile | Utility in nav, not order screen |
| Schedule | Manager's screen |
| Staff management | Not their role |
| Recipe editing | Head chef's job |

---

## 9. VILLA BOOKING

**Role:** Front desk staff (not owner, not waiter) book and manage villa stays. This is a BOOKING dashboard, not a general dashboard.

**BELONGS:**
| Feature | Why |
|---------|-----|
| Real villa cards (Villa 1/2/4/6/14/15, real KSh prices, photos) | "Which villas are available? How much?" |
| Availability calendar per villa | "Is Villa 6 free next weekend?" |
| Booking creation | "Book this guest into Villa 14" |
| Active bookings list | "Who's in which villa right now?" |
| Check-in/check-out | "Guest arrived — check them in" |

**REMOVED:** Everything unrelated to bookings.

---

## 10. FRONT DESK

**Role:** The front desk is the universal cashier. They handle money from all sources, reconcile cash, and manage villa bookings.

**BELONGS:**
| Feature | Why |
|---------|-----|
| Villa booking (links to Villa dashboard) | "Book this guest in" |
| Receipts store (search + calendar) | "Find the receipt from Tuesday for table 7" |
| Cash reconciliation (from any point) | "Count this cash drawer and submit" |
| Who-reconciles-what view | "Which staff member reconciled the bar cash?" |
| M-Pesa auto-confirmation display | "These M-Pesa payments are verified" — read-only |
| Today's arrivals/departures | "Who's coming, who's leaving?" |

---

## 11. GATE

**Role:** Gate staff admit guests. Two paths only.

**BELONGS:**
| Feature | Why |
|---------|-----|
| Day guest: pay KSh 3,000 → issue wristband | Path A |
| Booked guest: verify booking → admit (check in) | Path B |
| Today's stats (inside, issued, revenue) | "How busy are we?" |
| Band lookup | "What band number is this guest?" |
| Waiver alert (water guests need waivers) | Safety requirement |

**REMOVED:** Everything else. Gate staff don't manage inventory, edit menus, or handle payments.

---

## 12. FRONTLINE STAFF (Level 1)

**Role:** Staff who aren't waiters, kitchen, bar, spa, water, gate — general employees.

**BELONGS (only these):**
| Feature | Why |
|---------|-----|
| Clock in/out | "I'm here / I'm leaving" |
| Schedule | "When's my next shift?" |
| Notifications | "Any messages for me?" |
| Confidential-to-owner suggestion | "I want to report something privately" |

**REMOVED:** Everything else — they're not operating any system.
