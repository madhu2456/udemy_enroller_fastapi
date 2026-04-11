# Quick Reference Guide - Udemy Enroller Security Features

## ✅ Implemented Features

| Feature | Status | Location | Usage |
|---------|--------|----------|-------|
| **Bcrypt Password Hashing** | ✅ | `app/security.py` | Automatic on login/registration |
| **CORS Policy** | ✅ | `main.py` | Configured in `.env` |
| **Alembic Migrations** | ✅ | `alembic/`, `MIGRATIONS.md` | `alembic upgrade head` |
| **URL Validation** | ✅ | `app/security.py`, `app/schemas/schemas.py` | Auto-validated on input |
| **Pytest Tests** | ✅ | `tests/test_*.py` | `pytest tests/ -v` |
| **JSON Logging** | ✅ | `app/logging_config.py` | Config: `LOG_FORMAT=json` |
| **Sentry Tracking** | ✅ | `app/sentry_config.py` | Config: `SENTRY_DSN=...` |
| **Rate Limiting** | ✅ | `main.py`, `slowapi` | Config: `RATE_LIMIT_*` |

---

## 🔐 Security Improvements

### Password Hashing
```python
from app.security import hash_password, verify_password

# Hash password
hashed = hash_password("SecurePassword123!")  # 12-round bcrypt

# Verify password
is_valid = verify_password("SecurePassword123!", hashed)  # Returns True/False
```

**Benefits:**
- 12-round bcrypt (exceeds NIST recommendations)
- Automatic salt generation
- Protection against rainbow tables
- Validates minimum 8-character password

### URL Validation
```python
from app.security import validate_proxy_url, URLValidator

# Simple validation
is_valid = validate_proxy_url("socks5://proxy.example.com:1080")  # True

# Detailed validation
try:
    validator = URLValidator(url="http://example.com")
except ValueError as e:
    print(f"Invalid: {e}")
```

**Validates:**
- Allowed schemes (http, https, socks4, socks5, socks4a)
- Max length (2048 chars)
- Injection patterns (newlines, nulls, etc.)
- Required network location

---

## 📊 Logging Examples

### JSON Logging (Production)
```env
LOG_FORMAT=json
```
Output:
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "logger": "app.routers.auth",
  "module": "auth",
  "function": "login_with_credentials",
  "line": 52,
  "message": "Login successful: user@example.com"
}
```

### Text Logging (Development)
```env
LOG_FORMAT=text
```
Output:
```
2024-01-15 10:30:45 | INFO     | app.routers.auth:52 - Login successful: user@example.com
```

### Structured Data Logging
```python
from app.logging_config import log_structured

log_structured(
    "enrollment_complete",
    level="info",
    user_id=123,
    courses_enrolled=5,
    amount_saved=99.99
)
```

---

## 🚨 Error Tracking with Sentry

### Enable Sentry
```env
SENTRY_DSN=https://key@sentry.io/project-id
SENTRY_ENVIRONMENT=production
```

### Capture Exceptions
```python
from app.sentry_config import capture_exception

try:
    risky_operation()
except Exception as e:
    capture_exception(e, level="error")
```

**Automatic Capture:**
- All unhandled exceptions in routes
- Database errors (via SQLAlchemy integration)
- Async errors (via asyncio integration)
- HTTP requests (via FastAPI integration)

---

## ⏱️ Rate Limiting

### Configuration
```env
RATE_LIMIT_ENABLED=True
RATE_LIMIT_AUTH=100/minute      # /login, /login/cookies
RATE_LIMIT_API=500/minute       # General endpoints
```

### Current Limits
- Auth endpoints: 100 requests/minute per IP
- Health check: 60 requests/minute per IP
- General API: 500 requests/minute per IP

### Test Rate Limit
```bash
# Will succeed
curl http://localhost:8000/api/health

# After 60 requests in 1 minute, will fail
for i in {1..70}; do curl http://localhost:8000/api/health; done
```

### Response When Rate Limited
```json
{
  "status": "error",
  "message": "Rate limit exceeded",
  "detail": "60 per 1 minute"
}
```

---

## 🧪 Testing

### Run All Tests
```bash
python -m pytest tests/ -v
```

### Run Specific Test Class
```bash
python -m pytest tests/test_security_validation.py::TestPasswordSecurity -v
```

### Run with Coverage
```bash
python -m pytest tests/ --cov=app --cov-report=html
```

### Key Test Classes
- `TestPasswordSecurity` - Password hashing & verification
- `TestURLValidation` - URL validation edge cases
- `TestAuthEndpoints` - Authentication flow
- `TestSettingsValidation` - Input validation
- `TestCORS` - CORS configuration
- `TestRateLimiting` - Rate limit enforcement

---

## 🔄 Database Migrations

### Create Alembic Structure
```bash
python scripts/init_alembic.py
```

### Apply Migrations
```bash
# Latest version
alembic upgrade head

# Specific migration
alembic upgrade 001_initial_schema
```

### Create New Migration
```bash
# Auto-detect changes
alembic revision --autogenerate -m "Add new field"

# Manual migration
alembic revision -m "Custom migration"
```

### Rollback
```bash
# One step back
alembic downgrade -1

# To specific version
alembic downgrade 001_initial_schema
```

See `MIGRATIONS.md` for detailed guide.

---

## 📋 Input Validation Rules

### Passwords
- Minimum 8 characters
- Must be non-empty string
- Validated on login/registration

### Proxy URLs
- Valid schemes: http, https, socks4, socks4a, socks5
- Max 2048 characters
- Must have network location (host:port)
- No injection patterns

### Min Rating
- Range: 0.0 - 5.0
- Optional (None is valid)
- Validated in settings update

### Schedule Interval
- Non-negative integer
- 0 = disabled, >0 = hours between runs
- Optional

---

## 🚀 Deployment Checklist

### Pre-Deployment
- [ ] Review and update `.env` for production
- [ ] Set up Sentry project
- [ ] Configure CORS origins
- [ ] Run tests: `pytest tests/ -v`
- [ ] Check migrations: `alembic current`

### Deployment
- [ ] Back up production database
- [ ] Run migrations: `alembic upgrade head`
- [ ] Set environment variables
- [ ] Start application
- [ ] Verify health check: `/api/health`
- [ ] Monitor logs and Sentry

### Post-Deployment
- [ ] Smoke test login/enrollment
- [ ] Verify logging in Sentry
- [ ] Check rate limiting working
- [ ] Monitor error rates
- [ ] Review JSON logs

---

## 🔧 Environment Variables

```bash
# Security
SECRET_KEY=your-secret-key

# CORS (separate values with comma or use array)
CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000"]

# Logging
LOG_FORMAT=json                    # or "text"
LOG_LEVEL=INFO                     # DEBUG, INFO, WARNING, ERROR
LOG_FILE=logs/app.log

# Error Tracking
SENTRY_DSN=https://key@sentry.io/project-id
SENTRY_ENVIRONMENT=production      # development, staging, production

# Rate Limiting
RATE_LIMIT_ENABLED=True
RATE_LIMIT_AUTH=100/minute
RATE_LIMIT_API=500/minute

# Application
APP_NAME=Udemy Course Enroller
APP_VERSION=1.0.0
DEBUG=False
HOST=0.0.0.0
PORT=8000

# Database
DATABASE_URL=sqlite:///./udemy_enroller.db
```

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `IMPLEMENTATION.md` | Complete feature documentation |
| `MIGRATIONS.md` | Database migration guide |
| `README.md` | Project overview |

---

## 🆘 Troubleshooting

### Tests Won't Run
```bash
# Install test dependencies
pip install -r requirements.txt

# Check Python version (3.9+)
python --version

# Run with more verbose output
pytest tests/ -vv -s
```

### Sentry Not Capturing
- Verify `SENTRY_DSN` is correct
- Check network connectivity
- Review Sentry project settings
- Enable debug: `DEBUG=True`

### CORS Errors
- Check origin in `CORS_ORIGINS`
- Verify frontend is using configured origin
- Check cookie settings (`httponly`, `samesite`, `secure`)

### Rate Limiting Too Aggressive
- Increase limits in `.env`
- Check load patterns
- Consider user-based limiting (advanced)

---

## 📞 Support

For issues or questions:
1. Check `IMPLEMENTATION.md` for detailed docs
2. Review test cases for usage examples
3. Check logs: `logs/app.log`
4. Review Sentry dashboard for errors

---

**Last Updated**: 2024
**Version**: 1.0.0
**All Features**: ✅ Complete
