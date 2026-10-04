# W4 audit close-out — accessibility, SEO, API, and owner operations

**Repository:** Udemy Enroller
**Scope:** W4 findings F080, F083, F086, F091, F092, F043/F044, and F046
**Recorded:** 2026-10-04

This is an implementation and operations record. DNS changes, deployment changes,
and dependency publication are intentionally not performed by this document.

## Accessibility findings

### F080 — forced colors and increased contrast

The served web UI supports both media features in `app/static/css/site.css`:

- `@media (forced-colors: active)` restores system-palette focus outlines,
  borders, skeleton-loader separation, spinner visibility, and removes shadows
  that disappear in a forced palette.
- `@media (prefers-contrast: more)` raises muted text, accent text, borders,
  and focus outlines to the stronger contrast tokens used by the site.
- The page-specific inline style blocks in `app/templates/pages/login.html`,
  `app/templates/pages/login_page.html`, and
  `app/templates/pages/public_deals.html` also contain forced-colors rules for
  their local spinner/skeleton surfaces.

The CustomTkinter desktop GUI is **N/A for CSS media-query support**. It is a
native desktop surface, not served web CSS; its explicit `Dark`, `Light`, and
`System` appearance selector is implemented in `app/gui/views/sidebar.py` and
uses CustomTkinter's native appearance-mode handling.

### F083 — reduced motion

The served web UI has a global reduced-motion guard in
`app/static/css/site.css` and explicit guards beside each local animation in
`app/templates/pages/login.html`, `app/templates/pages/login_page.html`, and
`app/templates/pages/public_deals.html`. The guard disables the toast, spinner,
login spinner, and skeleton/pulse animations when
`prefers-reduced-motion: reduce` is active. Tailwind `animate-pulse` and
`animate-spin` are covered by the global static-sheet rule.

### F086 — IME composition

The only web key handler that commits text on Enter is the settings tag input in
`app/templates/pages/settings.html`. It returns before `preventDefault()` when
`KeyboardEvent.isComposing` is true or the legacy `keyCode === 229` marker is
present. This protects instructor and title tags from being committed while an
IME candidate is being confirmed.

A repository grep of served templates and `app/static/js` found no other
Enter-driven text-commit handler; native login form implicit submission is left
native because the browser commits composed text before submitting the form.

## F091 — SEO metadata and crawler headers

The shared HTML shell in `app/templates/components/base.html` emits a single
trimmed `<title>`, page-level `meta title`, description, canonical, and robots
metadata. The 404 and 500 templates explicitly use `noindex, nofollow` and
their handlers set the matching `X-Robots-Tag` response header.

`main.py` also maps public indexable roots to `X-Robots-Tag: index, follow`,
private/API/static surfaces to `noindex, nofollow`, normalizes trailing slashes,
and leaves conditional coupon/category decisions to their page-level robots
metadata. Error handlers take precedence over the general route policy.

The policy intentionally does not add an indexability header to a dynamic
coupon/category page when its meta-robots decision depends on request data; this
prevents a header/meta contradiction for thin listings.

## F092 — API advisory dispositions

| Advisory | Disposition | Evidence / rationale |
|---|---|---|
| OpenAPI and interactive docs | Mitigated in server mode | `main.py` sets `openapi_url`, `docs_url`, and `redoc_url` to `None` when `DEPLOYMENT_ENV=server`; local mode retains them for development. |
| Request abuse / rate limits | Mitigated | `app/security.py` provides bounded per-client sliding-window limiters; login, analytics, CSP reports, auth status, and public coupon API edges are limited. Settings export and enrollment start have route-specific limiters. |
| RLS | N/A + rationale | This is a single-tenant/personal-use application using one local SQLite database, not a shared PostgreSQL tenant service. Authorization is enforced at the application/session boundary; PostgreSQL row-level security is not an available runtime primitive here. |
| TLS termination | N/A in application process + documented boundary | Server mode emits HSTS and the supported deployment binds the app to loopback for the host reverse proxy. TLS certificate/termination is an owner-managed nginx/Cloudflare boundary, not an in-process SQLite/FastAPI feature. |
| DLQ | N/A + rationale | Enrollment work is an in-process, single-consumer `asyncio` queue with persisted run/course status and explicit failure/circuit-breaker handling; there is no external broker or at-least-once message stream that needs a dead-letter queue. |

Any future conversion to a multi-tenant database, external broker, or direct
internet TLS listener must reopen these dispositions before deployment.

## F043/F044 — DNSSEC and CAA record preparation

No DNS writes are performed as part of W4. The owner/provider must apply and
verify the following records at the authoritative DNS provider before marking
the operational flip complete:

1. **DNSSEC:** enable signing at the registrar/DNS provider; publish the
   provider-generated DS record at the registrar; record key-tag, algorithm,
   digest type, digest, and activation timestamp in the provider change log.
2. **CAA:** publish CAA records for the certificate authorities actually used
   by the reverse-proxy/certificate workflow. The owner must replace the
   placeholders below with the selected CA account/issuer policy before
   applying them:

   ```text
   <zone>  CAA 0 issue "<approved-certificate-authority>"
   <zone>  CAA 0 iodef "mailto:<security-contact>"
   ```

3. Verify DNSSEC with a validating resolver (`dig +dnssec`, `delv`, or the
   provider's validation check), verify CAA with `dig CAA`, then issue/renew a
   staging certificate before production renewal. Do not add a broad `issue`
   record as a shortcut, and do not commit provider secrets or DNS API tokens.
4. Rollback is provider-specific: disable the newly added CAA restriction only
   if certificate issuance is blocked, and do not remove a working DS record
   without the registrar/provider's DNSSEC rollover procedure.

The authoritative zone, chosen CA, security mailbox, and DNS provider are not
stored in this repository; therefore no concrete DNS record was applied or
claimed as live.

## F046 — SBOM/SLSA preparation

The project has no signed artifact-attestation or SBOM publisher in its current
architecture. It is a Python source distribution plus optional Docker and
standalone GUI/CLI builds; `.github/workflows/ci.yml` currently runs dependency
and test checks but does not publish provenance.

This finding is therefore recorded as **architecture preparation / not yet
applicable to the current personal-use release process**, not as a claim of
SLSA compliance. Before a public release pipeline is treated as supply-chain
hardened, add a CI-owned, least-privilege job that:

- generates an SPDX or CycloneDX SBOM from `requirements.lock`, `package-lock.json`,
  and the final container/build artifact;
- stores the SBOM as a build artifact and signs it with the release identity;
- emits SLSA provenance containing source revision, workflow run, builder,
  inputs, and immutable artifact digests; and
- verifies the signature/provenance and runs the existing secret/dependency
  checks before publication.

Until that pipeline exists, releases must be treated as source/build outputs
without a verified SBOM or SLSA provenance claim.

## Evidence commands

These commands provide the repository evidence for the dispositions above:

```bash
rg -n "forced-colors|prefers-contrast|prefers-reduced-motion" app/static/css app/templates
rg -n "isComposing|keyCode === 229|addEventListener\(\"keydown\"" app/templates app/static/js
rg -n "X-Robots-Tag|_robots_tag_for_path|openapi_url|docs_url|redoc_url" main.py
rg -n "RateLimiter|rate_limiter|raise_if_limited|DEPLOYMENT_ENV" app main.py config
rg -n "DNSSEC|CAA|SBOM|SLSA|provenance" docs .github scripts
```
