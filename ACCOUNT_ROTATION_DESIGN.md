# Account Rotation — Design Note

## Why this is needed

The 403 pattern we've been chasing is **application-layer**, not network-layer.
Every failing response has been `server: cloudflare` + `cf-ray` (i.e. Cloudflare
cleanly forwarded the request) with a Udemy-branded `<title>Error • Udemy</title>
… Forbidden` body — the origin is making the decision, not CF. The homepage
works; the course pages don't. The determinant is the `access_token` cookie:
the account has **5,000 enrolled courses**, which is a near-unmistakable
automation signature, and Udemy has flagged it for the course-page route.

No stealth improvement (Referer rotation, header parity, fresh cf_clearance,
separate pages, Google referer) clears the block once the account is in this
state. We verified that by ratcheting through all of them. The only fixes with
real leverage are:

1. **Avoid attaching `access_token` to course-ID resolution.** Already shipped
   in this change (public slug-API + anonymous Playwright context).
2. **Stop treating a single Udemy account as a permanent resource.** That's
   the subject of this document.

## Goals

- Keep the enrollment pipeline running at useful throughput even when any one
  account is flagged.
- Detect "burnt" state cheaply, swap in a fresh account, and resume — without
  double-enrolling courses the user already has.
- Preserve `EnrolledCourses` (the 5,000-course ledger) across swaps so
  dedup keeps working.
- Keep the user in control — nothing silently creates accounts; the pool is
  hand-curated.

## Out of scope

- Creating Udemy accounts programmatically (violates ToS; also not reliable).
- CAPTCHA-solver plumbing. If we ever get there, it's a separate doc.
- Sharing session cookies between machines. Single-host only.

## Concepts

### Account
A credential tuple:

```
{
  id: str,                # opaque local name, e.g. "primary", "alt-01"
  cookies_file: Path,     # Netscape-format cookie jar exported from user's browser
  created_at: datetime,
  enrollments_count: int, # last observed count (from get_enrolled_courses)
  state: enum { active, cooling, burnt, disabled }
}
```

States:

- **active** — eligible to be selected.
- **cooling** — recently hit a 403 threshold; off-rotation for a cooldown
  window (e.g. 24h) before re-probe.
- **burnt** — consistently 403s even after cooldown. Not selected until
  user re-classifies.
- **disabled** — user removed it from rotation manually.

### AccountPool
Owns the list, persistence (JSON at `F:\Codes\Claude\Udemy Enroller\.accounts\pool.json`),
and selection policy. Tiny, single-process, no DB needed.

### Burn detection

A single 403 doesn't prove burnout — but a run of them against course pages
does, and critically, they're **course-specific** in pattern: the homepage
works, course pages 403. The existing `session_recovery_state` already tracks
`consecutive_403_errors`. Extending that into a pool-wide signal:

- Promote an account from `active` → `cooling` when it hits
  `consecutive_403_errors ≥ N` on course-page fetches **and** a homepage probe
  still succeeds (to rule out network-layer issues).
- Promote from `cooling` → `burnt` if re-entry probe 403s within 60s.

Default `N = 10`. Tunable via `.env` as `ACCOUNT_BURN_THRESHOLD`.

## Pipeline integration

### Where to plug it in

`UdemyClient.__init__` currently takes cookies from a single source. Two changes:

1. Replace the singleton `UdemyClient` with an `AccountPool` that hands out a
   `UdemyClient` bound to the currently-selected account.
2. `enrollment_manager` asks the pool for a client at the top of each course;
   a successful enrollment increments the pool's internal enrollment counter.
   A 403 spike triggers rotation mid-run.

Pseudocode:

```python
pool = AccountPool.load()
for course in targets:
    async with pool.acquire() as client:   # may swap account transparently
        await client.get_course_id(course)
        await client.check_course(course)
        if course.is_valid:
            await client.free_checkout(course)
```

`pool.acquire()` picks the most-recently-successful `active` account; if its
burn signal trips during the block, the context manager fails the single
attempt and the outer retry on `enrollment_manager` retries with a freshly
selected account.

### Dedup across accounts

`get_enrolled_courses` is per-account. For cross-account dedup, persist a
**union ledger** at `F:\Codes\Claude\Udemy Enroller\.accounts\enrolled-union.json`:

```
{
  "slugs": { "<slug>": { "first_seen_account": "primary", "enroll_time": "..." }, ... }
}
```

On each client init we:
1. Read the union.
2. Fetch the current account's enrolled list.
3. Merge into the union (write-back).
4. Pass `known_slugs = union.keys()` into `is_already_enrolled()`.

This means rotating accounts doesn't cause you to re-enroll courses that
another account already holds. It also means the 5,000-course ledger isn't
lost — it just moves from "per-account" to "per-pool".

### Storage layout

```
F:\Codes\Claude\Udemy Enroller\.accounts\
  pool.json              # account metadata + state
  enrolled-union.json    # cross-account slug union
  cookies\
    primary.cookies      # Netscape cookies export
    alt-01.cookies
    alt-02.cookies
```

Added to `.gitignore` — cookies are sensitive.

## Operational workflow

### Adding an account

User exports cookies from a logged-in Udemy browser session (EditThisCookie or
similar) and drops the Netscape-format file in `.accounts\cookies\`. A
one-time CLI command registers it:

```
python -m app.cli account add --id alt-01 --cookies .accounts\cookies\alt-01.cookies
```

Registration does a homepage + `/api-2.0/users/me/` probe to confirm the
cookies are valid, then appends to `pool.json` with `state=active`.

### Marking an account burnt manually

```
python -m app.cli account burn alt-01
```

Sets state to `burnt`. Useful when the user sees Udemy's "your account is
under review" banner in their browser for that account.

### Recovery

`cooling → active` is automatic after the cooldown window (24h by default,
tunable via `ACCOUNT_COOLDOWN_HOURS`). `burnt → active` is manual only —
the user has to re-probe and explicitly `account revive <id>`. Automation
should never do this because the whole point of `burnt` is "even cooldown
didn't help, human judgment required".

## What this does NOT fix

- If **every** account in the pool is flagged (e.g. same IP, shared
  behaviour pattern), rotation won't help. At that point the intervention
  has to be IP-level (residential proxy rotation) or behavioural (lower
  enrollment cadence per account, spread the 5,000 over months not days).
- A new account still has to clear CF challenges for its first session —
  the anon-context + slug-API path already handles that and doesn't care
  which account is "active".

## Rollout order (if/when you want this built)

1. `AccountPool` class + `pool.json` persistence + CLI `account add/list`.
2. Cross-account union ledger in `get_enrolled_courses`.
3. Burn-detection hook in `UdemyClient` that flips pool state on 403 spikes.
4. `pool.acquire()` integration into `enrollment_manager`.
5. CLI for `burn` / `revive` / `remove`.

Steps 1–2 are prerequisites and cheap (a few hundred lines). Step 3 is the
interesting one — don't over-build it; start with a simple threshold and
iterate from production signal.

## Estimated impact

With 2–3 accounts in rotation and this change already shipped (slug-API +
anonymous context), I'd expect the course-page 403 rate to drop from ~100%
to near zero on fresh accounts, and the current account's burn state to
stop being pipeline-fatal. The 5,000-enrollment account can stay in the
pool for `free_checkout` work (where having history is actually OK) while
`get_course_id` uses the anonymous paths regardless of which account is
"active".
