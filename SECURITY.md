# Security Policy

## Supported versions

Security fixes are considered for the latest code on the `main` branch of this repository.

## Reporting a vulnerability

Please report security issues **privately**. Do not open a public GitHub issue for vulnerabilities that could expose user session data or credentials.

### Preferred contacts (concrete)

| Method | Where |
|--------|--------|
| **GitHub Private Vulnerability Reporting** | [Open a security advisory](https://github.com/madhu2456/udemy_enroller_fastapi/security/advisories/new) (if enabled on the repository) |
| **Maintainer profile / contact** | [https://madhudadi.in/profile/](https://madhudadi.in/profile/) |
| **security.txt** (live site) | [https://udemyenroller.madhudadi.in/.well-known/security.txt](https://udemyenroller.madhudadi.in/.well-known/security.txt) |

### Email

There is **no separate `security@` inbox published in this repository** at this time.

- Prefer **GitHub security advisories** or the **contact method on the maintainer profile** above.
- If you need a direct email address, use only an address the maintainer has **publicly listed** for contact (do not use addresses found only in old git history or private commits).

### What to include

- A clear description of the issue and impact  
- Steps to reproduce (against a **local** or **self-hosted** instance when possible)  
- Affected version or commit hash if known  

### Please do not

- Test against third-party production systems (including Udemy) in ways that violate their terms or the law  
- Include real production secrets, cookies, or personal data in reports  
- Perform denial-of-service or high-volume scanning against the hosted demo  

## Scope notes

- This project is an **independent** tool and is **not affiliated with, endorsed by, or authorized by Udemy**.
- Hosted demo deployments may store **encrypted** Udemy session cookies for users who connect. Prefer **self-hosting** when you need full control over session data location.
- Authentication to Udemy uses user-supplied session cookies (and optional local email login in non-server deployments). Treat cookies as highly sensitive.
- Branding, automation, and platform-terms residual risk is an **owner/counsel** matter. See `docs/legal-counsel-review.md` (process checklist; not legal advice).

## Maintainer response

There is no formal SLA. Reports will be reviewed as capacity allows. You may request a confirmation of receipt; a timeline for a fix is not guaranteed.
