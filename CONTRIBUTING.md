# Contributing to Udemy Enroller

Thanks for your interest in improving this project.

This is an **independent, open-source** tool. It is **not affiliated with, endorsed by, or authorized by Udemy**. Contributors must not add features that encourage or implement:

- CAPTCHA / MFA / auth bypass
- Stealth or anti-detection “improvements” beyond existing owner-approved code without discussion
- Rate-limit evasion or residential proxy rotation for abuse
- Credential harvesting or logging of secrets
- Real automated abuse of Udemy or third-party sites in CI or docs

See [SECURITY.md](SECURITY.md) for vulnerability reporting (private preferred).

## Development setup

### Prerequisites

- **Python 3.11+** (CI and Docker use **3.11**; newer local versions often work)
- **Git**
- Optional: **Node.js** + npm (Tailwind CSS builds only)
- Optional: **Docker** + Docker Compose

### Local app

```bash
git clone https://github.com/madhu2456/udemy_enroller_fastapi.git
cd udemy_enroller_fastapi

python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env as needed. For local defaults, DEPLOYMENT_ENV=local is fine.

alembic upgrade head
python run.py
```

App: `http://localhost:8000`

### Frontend CSS (optional)

```bash
npm ci
npm run build:css
```

### Accessibility smoke (optional)

With the app running locally:

```bash
BASE_URL=http://127.0.0.1:8000 npm run audit:wcag
```

See `docs/wcag-audit.md`. This is an automated target check, not a formal WCAG conformance claim.

### Performance lab (optional)

```bash
# Against production (default)
npm run audit:performance
npm run audit:performance:baseline   # update tests/performance-baseline.json
npm run audit:performance:check      # regression vs baseline

# Against local
PERF_BASE_URL=http://127.0.0.1:8000 npm run audit:performance
```

See `docs/performance-baseline.md`.

### Multi-browser smoke (optional)

```bash
# Requires Playwright browsers: npx playwright install firefox webkit
# WebKit may need: sudo npx playwright install-deps
BASE_URL=http://127.0.0.1:8000 SMOKE_TOKEN='<session_id>' npm run smoke:browsers
```

See `docs/browser-smoke.md`.

### Viewport matrix (optional)

```bash
BASE_URL=http://127.0.0.1:8000 SMOKE_TOKEN='<session_id>' npm run smoke:viewports
```

See `docs/viewport-smoke.md`.

### Tests and lint

```bash
# Prefer the project venv
source venv/bin/activate

ruff check .
python -m pytest
```

CI runs on pull requests: ruff, migrations, pytest (with Playwright Chromium for relevant tests).

**Do not** add tests that perform real Udemy login, enrollment, purchase, or coupon redemption against production Udemy. Use mocks, fixtures, and cassettes.

## How to contribute

1. **Open an issue** (or discuss in a PR) for non-trivial changes. Use the bug/feature templates under `.github/ISSUE_TEMPLATE/` when filing on GitHub.
2. **Fork** and create a branch from `main`:
   ```bash
   git checkout -b fix/short-description
   ```
3. Make a **focused** change (avoid unrelated refactors or mass formatting).
4. Add/update tests when behavior changes.
5. Update docs if user-facing behavior or setup changes:
   - [README.md](README.md)
   - [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]`
   - Privacy/copy pages if processing or claims change
6. Ensure `ruff check .` and `pytest` pass.
7. Open a **Pull Request** against `main` with:
   - What changed and why
   - How you tested
   - Any risk/migration notes

## Code style

- Python: **Ruff** (`ruff.toml` — target `py311`, line length 120)
- Prefer small, reviewable PRs
- No secrets in the repo (use `.env`; never commit `.env`)
- Do not invent analytics, enrollment counts, or affiliation claims in UI or SEO copy

## Project layout (high level)

| Path | Role |
|------|------|
| `main.py` / `run.py` | App entry |
| `app/routers/` | HTTP routes |
| `app/services/` | Scraper, enrollment, Udemy client |
| `app/templates/` | Jinja HTML |
| `app/models/` | SQLAlchemy models |
| `alembic/` | Migrations |
| `tests/` | Pytest suite |
| `chrome-extension/` | Optional cookie helper extension |
| `.github/workflows/` | CI and deploy |

## Deploy note

Production deploy is primarily via **GitHub Actions** (see `.github/workflows/deploy.yaml`) or **Docker Compose**. Treat `scripts/deploy.sh` as an older droplet bootstrap; review carefully before any use on a real server.

See README sections **Updating** and **Uninstall / remove** for end-user upgrade and teardown steps.

## License

By contributing, you agree that your contributions are licensed under the same [MIT License](LICENSE) as the project.
