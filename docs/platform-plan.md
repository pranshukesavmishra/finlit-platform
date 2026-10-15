# FinLit platform plan: security, data quality, UI, scaling, login

Status as of 15 Oct 2026. ✅ = built and tested in this repo · ⏳ = designed here, built in the phase noted.

A note on "no loophole at all": no real system can promise that. Banks and brokers don't either. What we
can do, and what this plan does, is **defence in depth**:
- several independent layers, so one failure doesn't expose users or money;
- no stored passwords, so there is nothing to steal;
- server-side checks for everything that matters (plans, payments, amounts);
- fast detection and a tested response when something does go wrong.

The target checklist is **OWASP ASVS 5.0 Level 2**, the standard for apps that handle sensitive personal
and financial data. Before payments go live we add an external penetration test.

---

## 1. Security

### Layer map

| # | Layer | What protects it | Status |
|---|---|---|---|
| 1 | Edge | Cloudflare proxy, WAF managed rules, rate-limit rules, Bot Fight Mode, Turnstile on login | ⏳ deploy |
| 2 | Server | Firewall only accepts Cloudflare IPs; SSH by key over Tailscale; automatic OS security updates | ⏳ deploy |
| 3 | Containers | Non-root, read-only filesystem, no Linux capabilities, no-new-privileges; DB and Redis on localhost only, Redis password | ✅ |
| 4 | API | Strict security headers, trusted hosts, per-client rate limits, strict input validation, no stack traces, no docs in production | ✅ |
| 5 | Database | Parameterised SQL only; API connects as a **read-only role** that cannot change or delete data | ✅ |
| 6 | Identity | Email OTP + Google + passkeys; no passwords stored anywhere | ⏳ Phase 3 |
| 7 | Sessions | Opaque session ID in a `__Host-` HttpOnly Secure SameSite cookie; rotation; device list with sign-out | ⏳ Phase 3 |
| 8 | Authorization | Plans (Basic/Bronze/Gold) enforced on the server for every request | ⏳ Phase 3 |
| 9 | Payments | Razorpay orders created server-side, both signatures verified, webhook idempotency, append-only ledger | ⏳ Phase 3 |
| 10 | Data protection | TLS everywhere; encrypted backups; minimal personal data; field-level encryption for sensitive IDs | ⏳ Phase 3 |
| 11 | Supply chain | pip-audit, bandit, gitleaks, Dependabot, read-only CI tokens, pinned versions | ✅ |
| 12 | Detection | Audit log, alerts on login and OTP spikes, error tracking with personal data scrubbed, incident runbook | ⏳ Phase 3 |

### What is already in the code (✅)

- **Headers on every response** (`backend/finlit/security.py`): HSTS (2 years, preload), CSP `default-src 'none'`,
  `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, CORP/COOP, Permissions-Policy. The
  `Server` header is removed.
- **Rate limiting** in Redis per client: 300 requests/minute by default, IPv6 counted per /64.
  - The real client IP is read from `cf-connecting-ip` only when configured, because otherwise anyone can fake it.
  - Opening a stock that isn't prepared yet costs about 21 FinEdge calls. So it is capped per client
    (30/hour) and in total (500 pending), and this cap stays closed if Redis is down.
- **Production safety switch:** with `ENVIRONMENT=production` the API refuses to start if any of these is true:
  - a password is still the default;
  - Redis has no password;
  - the allowed hosts are a wildcard;
  - a CORS origin isn't `https`;
  - it is set to use test (fixture) data.
- **Least privilege:** migration `002_api_role.sql`. Tested: the API role can read snapshots, while
  `DELETE` is refused with *permission denied*.
- **Supply chain:** the first scan found **16 known vulnerabilities** in the pinned Starlette and orjson
  versions. Both were upgraded and `pip-audit` now reports none. The scans run on every push and weekly:
  - `pip-audit`: dependency CVEs;
  - `bandit`: risky code patterns; one finding fixed;
  - `gitleaks`: leaked secrets across the whole git history; clean.

### Identity and login (Phase 3)

**No passwords.** Most account takeovers are password reuse and credential stuffing. Without passwords
there is nothing to stuff, leak or reset.

| Method | Library | Key rules |
|---|---|---|
| Google sign-in | `google-auth`: verify the ID token server-side | Check `aud` = our client ID, `iss`, `exp`, `email_verified`, and a one-time `nonce`. Never trust the email sent from the browser. |
| Email OTP | Python `secrets`, Resend for delivery | 6 digits, valid 10 minutes, single use, max 5 attempts, then 15-minute lockout. Resend after 60 s. Stored as HMAC-SHA256 with a server secret, never in plain text. Turnstile check before sending. Same reply whether or not the email exists. |
| Passkeys | `webauthn` (Duo Labs py_webauthn) | Phishing-resistant (NIST SP 800-63B-4 brings synced passkeys into scope). Offered after first login; **required for admins**. |
| If passwords are ever added | `pwdlib` with Argon2id (`argon2-cffi`) | `passlib` is unmaintained and stopped working on Python 3.13+. |

**Sessions**
- The session ID is 256 bits from `secrets.token_urlsafe`. Only its SHA-256 hash is stored, so a
  database leak can't be replayed as a login.
- Cookie: `__Host-session; Secure; HttpOnly; SameSite=Lax; Path=/`. **No JWT in browser storage.** The
  current site keeps an admin JWT in `sessionStorage`, where any XSS bug can read it.
- Lifetimes:

  | Account | Idle timeout | Absolute limit |
  |---|---|---|
  | Users | 30 days | 90 days |
  | Admins | 15 min | 12 hours |

- A new session ID is issued at login and whenever privileges change.
- The account page lists devices, and users can sign out any one of them or all of them (ASVS 7.5.2).
- **Step-up re-authentication** is required before changing email, deleting the account, or admin
  actions such as refunds and plan overrides (ASVS 7.5.1).
- CSRF protection: SameSite cookies plus an `Origin` check plus a CSRF token on every request that changes something.
- Alert email on sign-in from a new device. Every login, OTP and failure goes into the audit log.

### Payments with Razorpay (Phase 3)

1. **The server sets the price.** The browser sends only a plan ID. The server creates the Razorpay
   order with the amount from its own price table, in paise as integers. A tampered amount can never reach Razorpay.
2. **Checkout signature:** check HMAC-SHA256 of `order_id|payment_id` with the API key secret, using
   `hmac.compare_digest` (constant-time comparison).
3. **Webhook signature:** HMAC-SHA256 of the **raw request body** (do not parse it first) with the
   *webhook* secret, which is different from the API key secret.
4. **Idempotency:** store each Razorpay event ID in a unique column. A replayed or duplicate webhook does nothing.
5. **Only a verified webhook (or a server-side payment fetch) activates a plan**, never the browser's
   "success" redirect.
6. **Append-only ledger:** payments, refunds and plan changes are inserted, never updated or deleted.
   The database role enforces this.
7. **No card data touches our servers.** Razorpay Checkout handles it, which keeps us out of PCI DSS scope.
8. 2FA on the Razorpay dashboard, keys separated by environment (test and live), and keys rotated on any suspicion.

**Plan gating:** the API decides what each plan may see and strips gated sections (Gold quarterly
ratios, the advanced model and so on) before sending. Hiding something in the UI is cosmetic only.
Watchlists and alerts always take the user ID from the session, never from the request.

### Compliance to confirm with your CA or lawyer

- **DPDP Act 2023 and DPDP Rules 2025** (Rules notified 13 Nov 2025; most obligations, including breach
  notification, apply from about **May 2027**). Prepare now:
  - a consent notice at sign-up;
  - purpose limitation;
  - export and delete-my-data;
  - breach notice to the Data Protection Board and to affected users (a detailed report within 72 hours).
- **SEBI Research Analyst rules** (amended Dec 2024):
  - client communications kept at least 5 years;
  - KYC through a KRA;
  - mandatory disclosure of AI use in research and reports. **This applies to our score and thesis text.**
- **SEBI CSCRF:** under the April 2025 clarification, RAs and IAs with no other SEBI registration are
  exempt. If FinLit holds another SEBI registration, the stricter framework applies.

### Account hygiene (do now)

- **Change the admin password that was shared in chat.**
- Turn on 2FA, ideally a passkey or security key, for every one of these accounts:
  - GitHub, Cloudflare, Razorpay, DigitalOcean or Oracle, FinEdge, Google Workspace and the domain registrar.
- On GitHub: branch protection on `main` (required checks and review), secret scanning and push protection on.
- Secrets live only in `.env` on the server (mode 600) or a secrets manager. Never in git, chat or screenshots.

---

## 2. Data quality

### Built (✅ `backend/finlit/quality.py`)

Every snapshot runs **23 checks** before it is published. On real RELIANCE data all 23 pass. The
accounting identities hold exactly:
- assets 1,165,809 = equity 566,235 + liabilities 599,574;
- price × shares equals market cap within 0.01%.

| Severity | Examples | What happens |
|---|---|---|
| Critical | Balance sheet off by >10% · market cap vs price × shares off by >60% (unit slip) · price ≤ 0 · dividend return not believable (the old 89% bug) | **Not published.** The last good snapshot stays live; the issue is logged in `ingest_runs`. |
| Warning | Stale price or results · P/E, ROE or yield outside believable ranges · holdings or segments not summing to 100% · live price vs last close >20% apart | Published with a data note on the page, and logged for review. |

Tests inject the old site's bugs and confirm each one is caught.

### Next

- **Cross-source reconciliation:** every evening, compare FinEdge closing prices with the NSE bhavcopy
  (the official file) and flag any difference above 0.5%.
- **Golden set:** about 30 hand-verified companies as permanent regression tests, covering banks,
  NBFCs, insurers, holding companies, loss-makers, recent IPOs, companies with splits and bonuses, and
  standalone-only companies.
- **Financial-sector models:** banks need NIM, GNPA/NNPA, CASA and capital adequacy, not operating
  margin. Their score pillars must change too.
- **Raw payload archive in R2:** keep every FinEdge response, so any number can be traced back and
  re-processed after a fix.
- **Admin data-health page:** a list of warnings and rejections, a one-click re-ingest, and per-stock freshness.

---

## 3. UI improvements (Phase 2)

- **Speed you can feel:**
  - the summary paints first and other sections stream in;
  - skeleton placeholders instead of spinners;
  - prefetch a stock when the cursor hovers over a search result;
  - instant search from the 89 KB index held in the browser.
- **Performance budget:** largest content painted in under 1.5 s on 4G; under 170 KB of compressed
  JavaScript on first load.
- Remove `lenis` smooth scrolling and heavy framer-motion effects (the source of the scroll jank). Use
  TradingView `lightweight-charts` (about 45 KB) for price charts instead of Recharts.
- **Trust signals:**
  - an "as of" date on every number;
  - data notes from the quality checks;
  - the score's "how it's built" drawer;
  - glossary tooltips on every ratio;
  - the SEBI disclaimer and AI-use disclosure.
- Indian number formats (₹ lakh and crore), tabular figures, accessible colours (WCAG 2.2 AA), full
  keyboard use, reduced-motion support, mobile-first layout.
- Keep the approved stock.html look: research-report hero, gold accents, dark and light themes, plan tiers.

---

## 4. Scaling options

Measured today: **0.3 ms of server time per request** (one Redis read). A single core serves well over
2,000 requests per second, and Cloudflare serves repeat views from its cache. The real limit is the
**FinEdge API quota**, not our servers.

| Stage | Users (rough) | Setup | Cost (approx.) |
|---|---|---|---|
| 1. Now | up to ~50k/day | 1 VPS, 4 GB (API + Postgres/Timescale + Redis + worker) behind Cloudflare | ₹2–3k/mo (or Oracle free) |
| 2. Growth | ~50k–500k/day | API on 2 small VPSs behind a Cloudflare load balancer · managed Postgres with point-in-time recovery · managed Redis · separate worker box | ₹10–20k/mo |
| 3. Scale | 500k+/day | Postgres read replicas · ingest queue (Redis Streams / arq) with several workers · live prices over SSE from a separate service · versioned cached URLs | grows with usage |

Rules that keep scaling cheap:
- **Never compute on request.** Everything is precomputed.
- **Cache at the edge.** Every response has an ETag and `stale-while-revalidate`.
- **Stay stateless.** API servers keep nothing locally, so adding one is a config change.

Open question for you: **the FinEdge plan's rate and daily limits.** A full nightly refresh of 5,745
stocks is about 120,000 calls.

---

## 5. Client login design (Phase 3)

A live mock-up of these screens is in the design repo (`login.html`).

1. **Welcome:**
   - "Continue with Google" as the main button;
   - "Continue with email";
   - "Sign in with a passkey", which appears automatically when the device has one.
2. **Email code:** six separate digit boxes that accept paste.
   - A countdown before "resend" works.
   - Clear errors: "Wrong code, 3 tries left", "Code expired", "Too many tries, wait 15 minutes".
3. **First sign-in:**
   - name;
   - an unticked marketing opt-in;
   - required agreement to the Terms, Privacy Policy and research disclaimer (DPDP consent and SEBI RA disclosure).
4. **Suggest a passkey:** "Sign in with your fingerprint next time". One tap, or skip.
5. **Account → Security:**
   - signed-in devices with "sign out", plus "sign out everywhere";
   - recent sign-in activity;
   - passkeys and the linked Google account;
   - download my data, delete my account.
6. **Admin sign-in** (`/admin`) is separate. A passkey is mandatory, and a new admin device needs approval.

What users never see: passwords, password resets, or security questions.

---

## Sources

- OWASP ASVS 5.0, session abuse defences: https://cornucopia.owasp.org/taxonomy/asvs-5.0/07-session-management/05-defenses-against-session-abuse
- OWASP WSTG, cookie attributes: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/06-Session_Management_Testing/02-Testing_for_Cookies_Attributes
- NIST SP 800-63B-4 (final, July 2025): https://csrc.nist.gov/pubs/sp/800/63/b/4/final
- Synced passkeys in 800-63-4: https://www.wwpass.com/blog/phishing-resistant-mfa-in-2025-buyer-s-guide-to-nist-sp-800-63-4-omb-m-22-09/
- Razorpay webhook validation: https://razorpay.com/docs/webhooks/validate-test.md
- Webhook vs payment signature: https://dev.to/eventdock/how-to-verify-razorpay-webhook-signatures-and-why-it-is-not-the-payment-signature-1pei
- Cloudflare form and abuse protection (Turnstile + rate limiting): https://developers.cloudflare.com/use-cases/solutions/protect-sensitive-forms-fraud-abuse/
- pwdlib (passlib successor): https://polar.sh/frankie567/posts/introducing-pwdlib-a-modern-password-hash-helper-for-python
- argon2-cffi: https://argon2-cffi.readthedocs.io/
- py_webauthn: https://pypi.org/project/webauthn/
- google-auth ID token verification: https://googleapis.dev/python/google-auth/latest/_modules/google/oauth2/id_token.html
- DPDP Rules 2025: https://www.hoganlovells.com/en/publications/indias-digital-personal-data-protection-act-2023-brought-into-force-
- DPDP breach timeline: https://ksandk.com/md/data-protection-and-data-privacy/dpdp-data-breach-notification-timeline/
- SEBI CSCRF clarification for IAs and RAs (NSE circular): https://nsearchives.nseindia.com/content/circulars/INSP67808.pdf
- SEBI RA amendments and FAQs: https://www.lkslaw.com/insights/articles/key-clarifications-under-the-sebi-issued-faqs-2025
- Semgrep vs Bandit: https://aicodereview.cc/blog/semgrep-vs-bandit
