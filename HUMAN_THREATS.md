# Human Attacks & Collusion — Owner's Threat Runbook

> This document is for **you (the owner)**, not for developers.
> It tells you what the system catches on its own, what it cannot catch, and what you need to do yourself.

---

## 1. What the system catches automatically

| Threat | How it's caught | Where to look |
|---|---|---|
| **Waiter voids too many orders** | Silent judge computes void rate per staff member. Anyone above 2× the team average is flagged. | Dashboard → Judge Alerts (VOID_ABUSE) |
| **Bartender over-consumes stock** | Weekly judge compares stock consumption to revenue ratio. Deviation beyond tolerance fires an alert. | Dashboard → Judge Alerts (RATIO) |
| **Unusual spoilage** | Daily judge flags any watch-list item with spoilage above the spike threshold. | Dashboard → Judge Alerts (SPOILAGE_SPIKE) |
| **Gate revenue shortfall** | End-of-day reconciliation: bands issued × entry fee vs actual gate payments. Mismatch is flagged. | Dashboard → Gate Reconciliation |
| **More people than bands** | If headcount recorded at gate exceeds bands issued, the reconciliation flags it. | Dashboard → Gate Reconciliation |
| **Cash safe mismatch** | Period close compares recorded cash vs physical safe count. Any shortfall fires a HIGH alert. | Dashboard → Judge Alerts (SAFE_COUNT_MISMATCH) |
| **Manager overrides someone's clock** | Every manual clock override is permanently audit-logged with the manager's name and reason. | Dashboard → Audit Log |
| **Any login, PIN change, or deactivation** | All auth events are audit-logged. PIN changes create a named entry. | Dashboard → Audit Log |
| **Tampered audit log** | The audit log is hash-chained. Run `flask audit verify-chain` to detect any row deletion or edit. | CLI |

---

## 2. What the system cannot catch

These are real gaps. No code change will close them — they require your presence and your processes.

### Off-books sales (the "ghost drink")
A bartender serves a drink from stock that was never entered into the system, takes cash, and keeps it. If the ingredient was never counted into inventory, there is zero trace. The judge's ratio detection only works on items that ARE in inventory.

**Signal to watch for:** Unexplained stock shrinkage during a physical count vs what the system shows.

### Gate friends (the "ghost guest")
A gate staff member waves a friend through without issuing a wristband. If that friend eats nothing, drinks nothing, and uses no chargeable service, they are completely invisible.

**Signal to watch for:** Headcount camera vs bands issued. The system can flag the headcount mismatch only if someone records the count honestly.

### PIN sharing
A senior staff member pressures a junior to share their PIN. Once the PIN is shared, every action the senior takes looks like it came from the junior.

**Signal to watch for:** Login times that don't match the junior's shift. Back-to-back logins from different staff at unusual hours. Audit log actions that don't match the person's role or department.

### Willing coercion (the "I'll explain later" override)
A manager pressures a waiter to skip a step or approve something irregular. If the waiter complies and never reports it, the action is logged under the manager's name (if they did it directly) or lost entirely (if the waiter did it on their behalf).

**Signal to watch for:** Nothing in the system. This requires your direct, regular conversations with junior staff.

### Key-person departure
A manager or trusted staff member leaves suddenly without a handover. Passwords, PIN codes, process knowledge, and supplier contacts may walk out the door.

**No system detection possible.** See Owner Checklist below.

---

## 3. Recommended human controls

### Daily (takes 5 minutes)
- Glance at the Dashboard Judge Alerts. Any new HIGH alert = investigate today, not tomorrow.
- Check the gate reconciliation before you leave. Any mismatch = ask the gate manager face-to-face.

### Weekly
- Review the void rate report. Call in anyone flagged above the threshold. Ask a simple question: "Walk me through why these items were cancelled."
- Do a spot physical count on two or three bar items. Compare to what the system shows. Unexplained differences are a red flag.
- Read the last week of audit log entries for auth events (logins, PIN changes, deactivations). Anything you didn't expect → investigate.

### Monthly
- Rotate who does the cash reconciliation. Cashier and counter should not always be the same person. Separation of duties.
- Physically count one full category (e.g., all spirits). Compare to system. Variance beyond 5% should be explained.
- Run `flask audit verify-chain` from the server terminal. If it fails, the audit log has been tampered with.

### When hiring
- Give every employee their own account. Never share credentials. One person = one PIN = one accountability trail.
- Make the PIN-sharing policy explicit on day one, in writing.
- New hires at the gate or bar get a 30-day shadowing period before working unsupervised at end-of-day.

### Key-person departure checklist
When a manager or trusted staff member leaves (voluntarily or otherwise):

1. **Immediately:** Deactivate their account (`/auth/deactivate/<user_id>`). JWT tokens expire within 30 minutes. PIN is unusable as soon as `is_active = False`.
2. **Within 24 hours:** Change any shared access passwords (server SSH, router admin, etc.).
3. **Within 1 week:** Audit the last 30 days of their actions in the audit log. Look for unusual patterns in the days before departure.
4. **Ongoing:** Do not rely on verbal handover alone. Written process documentation for all key tasks.

### If you suspect active theft
1. Do not confront immediately — review the audit log first to build evidence.
2. Run `flask audit verify-chain` — a tampered chain means someone deleted records.
3. Pull the void rate report for the suspected period.
4. Pull the gate reconciliation for the suspected dates.
5. Do a full physical stock count before your conversation — not after.
6. If the evidence is strong: deactivate the account first, then confront.

---

## 4. Escape valves for junior staff

Juniors who are pressured by a manager have two protected channels:

1. **OWNER_PRIVATE suggestion** — submitted anonymously, structurally invisible to managers. The system filters it at the database query level — managers cannot see it even if they look.
2. **Owner-only dispute** — flagged `is_owner_only=true`, same structural protection.

**Your job:** Make sure every staff member knows these channels exist. Say it at onboarding. Remind them quarterly. The channels are useless if no one knows they exist.

---

*Generated by the security review — Phase B, Category 6.*
*Keep this document updated as the system evolves.*
