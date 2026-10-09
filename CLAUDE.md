# Panosu: customer behavior panel (multi-tenant SaaS)

Win-back engine for small businesses (studios, barbers, hair salons, cafes, gyms): per-customer churn risk and
**Riskteki Para** (revenue at risk), a "contact these people" list, and measured recovered revenue.
ERP (stock, accounting, POS) is out of scope.

Roles: the owner (Hüseyin) decides architecture, product logic and math. The agent writes code.
On a design ambiguity, do not guess: ask.

## Language and token rules
- Chat with the owner: Turkish. Everything written to the repo is English: this file, new docs (`.md` only),
  commit messages, new code comments.
- Code identifiers keep the existing Turkish domain names (isletme, uye, paket, ...) because they mirror the SQL
  schema. Never rename existing identifiers, files or columns. Existing Turkish docs are not translated.
- Keep this file short (max 150 lines); detail lives in docs/. Read only what the task needs.
- When the conversation gets long, remind the owner to run `/compact`. If an approach turns out wrong, suggest
  `/rewind` instead of stacking fixes on top.
- The owner is a math student new to software: explain each new concept once, in plain Turkish, with a concrete
  example; give one next action per reply.
- In Turkish replies, every English or technical word gets its Turkish meaning in parentheses, e.g. commit
  (kayıt), push (GitHub'a gönderme).
- Never ask the owner to paste or screenshot a password, token or secret URL; they run the command themselves
  and reply "hazır".
- Firm data (KVKK): never read, upload or copy a firm's real member files into Claude or any cloud service; the
  firm runs the pilot tools on its own machine and sends only the report.
- Firm-facing material (pilot kit, `docs/entegrasyon.md`) stays Turkish.

## Stack
Python 3.14, FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), Pydantic v2, PostgreSQL 15+, Alembic, pytest.
Windows + PowerShell. Virtualenv: `.venv`.

## Layout and dependency direction
```
main.py → rotalar/ → (bagimliliklar.py, servisler/, semalar/) → models.py → database.py → config.py
```
- `rotalar/`: HTTP layer, maps service exceptions to HTTP codes. `web.py` panel (cookie session, CSRF),
  `ara_katman.py` read-only demo (K25) and security headers (K27).
- `servisler/`: business rules; never imports FastAPI or raises HTTPException.
- `semalar/`: Pydantic schemas. `models.py` mirrors columns only; SQL is the single schema source
  (`faz1_sema.sql` = readable copy of `alembic/sql/0001_faz1_sema.sql`).
- `analitik/`: models (V1, BG/NBD, MBG/NBD, Gamma-Gamma, renewal probability) and "why risky"; no database.
- `backtest/`: model comparison on synthetic scenarios S0-S6; no database.
- `sentetik/`: synthetic data, demo setup, refresh and export; writes only to databases ending in `_demo`.
- `sablonlar/` (Jinja2), `statik/` (htmx, `panel.css`; keep `panel.css`: the uptime monitor and the Render health
  check request it). Landing page `web/tanitim.html` + `statik/tanitim.css`/`tanitim.js`; vendored three.js in
  `statik/vendor/`, self-hosted fonts in `statik/yazitipi/`, promo video and share image in `statik/medya/` (no CDN,
  K55, K74).
- `Dockerfile`, `requirements-uretim.txt` (runtime deps; update on a new runtime import),
  `.github/workflows/` (`demo-tazele.yml` nightly, `demo-kur.yml` manual with confirm word "KUR", `testler.yml`
  full pytest on every push to main and on PRs, throwaway PostgreSQL with trust auth).
Module detail: `docs/commands.md` and the step docs `docs/adim-*.md`.

## Non-negotiable rules
1. No `create_all` / `drop_all` / `reflect`. No DDL outside `alembic/`. Guarded by `tests/test_guvenlik_bekcisi.py`.
2. Never modify `faz1_sema.sql`, `alembic/sql/*`, `tests/test_guvenlik_bekcisi.py`, `tests/test_izolasyon_db.py`.
3. Tenant isolation is PostgreSQL RLS. `isletme_id` never comes from the client; never add manual `isletme_id`
   filters. The `after_begin` event in `database.py` sets `app.isletme_id` / `app.kullanici_id` per transaction;
   do not break it. `isletme_id` is read only from the signed access token; on the business-select endpoint the
   client's value is used only after membership is verified.
4. The app connects as `panosu_app` (RLS-bound, no DDL). Migrations run with `PANOSU_MIGRASYON_URL`.
   No autogenerate; migrations are hand-written.
5. Money is `Decimal` only, never float.
6. Never delete or weaken tests, no `skip`/`xfail`. If a security/isolation test is red, do not fix it: stop and report.
7. Passwords never appear in output, reports or commits. `.env` is never committed. `PANOSU_JWT_GIZLI` and the demo
   password are never printed. K26: the public live demo password (`PANOSU_DEMO_GIRIS_PAROLA`) differs from local
   ones and still never appears in code, tests (as a literal), output or commits.
8. New packages need approval.
9. Commit and push only with the owner's explicit OK in this chat. Before a push, say in plain words what it
   changes (a push to main redeploys the live site).
10. Unrequested refactors or new files/folders: ask first.

## Databases
| Name | Purpose | Rule |
|---|---|---|
| `panosu` | Live, real business data only | Read-only queries; every write needs explicit approval; never `alembic upgrade` (approved `stamp` only) |
| `panosu_test` | pytest | Can be dropped and rebuilt with `alembic upgrade head` |
| `panosu_demo` | Synthetic demo data, 5 [DEMO] businesses | Loaders write only to `_demo` names; detail in `docs/commands.md` |
| Neon `panosu_demo` | Live demo https://panosu.onrender.com | Only Render (`panosu_app`) and GitHub Actions connect; never from local |

Synthetic data is NEVER written to `panosu`. Tests refuse to run on a database whose name does not end in `_test`.

## Core commands
```powershell
.\.venv\Scripts\python.exe -m pytest -v                  # full suite (panosu_test)
.\.venv\Scripts\python.exe -c "import main"              # import check
.\.venv\Scripts\python.exe -m backtest --tohum-sayisi 2  # quick backtest
.\.venv\Scripts\python.exe -m sentetik.demo_sunucu       # panel on panosu_demo, 127.0.0.1:8000
```
All other commands (synthetic data, demo setup/refresh, import/export, reports), test URL rules and schema setup:
`docs/commands.md`.

## Roadmap
This table is the single source of step status; README only summarizes. Step details, hypotheses, ideas and the
research shelf: `docs/roadmap.md`. Math decisions (model choice, assumptions) belong to the owner.

| # | Step | Status |
|---|---|---|
| 1 | Security lock (RLS, guard tests) | Done |
| 2 | Alembic baseline | Done |
| 3 | Customer API | Done |
| 4a | Services + visits API, synthetic data engine | Done |
| 4b | CSV/Excel import (`docs/adim-4b-tasarim.md`) | 4b-1 Done; 4b-2 validation command done (pilot step), first real run at the first pilot; 4b-3 web screen pending |
| 5a | Model library: V1, BG/NBD, MBG/NBD, Gamma-Gamma, Riskteki Para (`docs/adim-5-6-tasarim.md`) | Done |
| 5b | Memberships, renewal risk, S6 backtest (`docs/adim-5b-tasarim.md`) | Done |
| 5c | Renewal model calibration with real renewal data | Waiting for Faz 0 data |
| 6 | Backtest S0-S5 (`docs/backtest-sonuclari.md`) | Done |
| 7 | Panel: silent members, revenue and profit, weekly report (`docs/adim-7-tasarim.md`) | Done |
| 8 | Auth + business sign-up (`docs/adim-8-tasarim.md`); live `panosu` migration needs separate approval | Done |
| 8a | Cold-start mode (prior learned from other businesses) | Planned |
| 8b | Automatic recalculation for real businesses | Planned |
| 9 | Web panel, Jinja + HTMX (`docs/adim-9-tasarim.md`) | Done |
| 10 | Consent, messaging, win-back measurement | Planned |
| 11 | Deployment (`docs/adim-11-tasarim.md`) | Done (live 2026-10-02; payments later) |
| - | Model fix (μ, κ): MAP, weak prior, two starts (`docs/adim-mu-kappa-tasarim.md`) | Done |
| - | Math report: model, MAP, validation, limitations (`docs/matematik-raporu.md`) | Done |
| - | Ritmeva brand + public landing page (`docs/adim-ritmeva-tasarim.md`) | Done |
| - | Exact renewal probability (Rao-Blackwell), `mbgnbd-map-v3` (`docs/adim-rao-blackwell-tasarim.md`) | Done |
| - | Pilot: validation report + score list without a database (`docs/adim-pilot-tasarim.md`) | Done |
| - | Score command: nightly risk list, model version column (`docs/adim-skor-tasarim.md`) | Done |

## Open issues (Açık konular)
- After the (μ, κ) fix (`docs/adim-mu-kappa-tasarim.md` section 4): tune prior centers (`analitik.bgnbd` ONSEL_*)
  on real data in 4b-2; minimum-data guard (all single-visit or 1-day history gives confident but meaningless
  output; thresholds are the owner's call); similar ridge in Gamma-Gamma (q → ∞, backtest only); full Bayes
  for parameter uncertainty in the renewal probability (Rao-Blackwell done: exact formula, K61).
- Synthetic generator (low priority): in [DEMO] Butik Reformer 2% of members visit several times a day (up to 6.2),
  and 9 members have 22 same-second visit pairs (different dis_kimlik); import collapses them (K33). Fixing changes
  demo numbers: separate decision.

## Working rules
- After every task report: changed files, pytest summary line, every deviation from the instruction.
- "Done" needs evidence: command output or test result.
- When a step finishes, update the roadmap table here.
- Reports go to `raporlar/` (gitignored).

## Reference notes
- docs/agent-ideas.md: owner constraints and notes on the "agent company" idea. Read it only when the owner
  mentions agents, automation, loops, or game development.
