Moved from CLAUDE.md on 2026-10-03. CLAUDE.md links here.

# Panosu: commands, databases and module detail

## Module detail (layout and dependency direction)
```
main.py → rotalar/ → (bagimliliklar.py, servisler/, semalar/) → models.py → database.py → config.py
```
- `rotalar/`: HTTP layer. Maps service exceptions to HTTP codes. `rotalar/web.py`: web panel HTML endpoints
  (cookie session, CSRF; `docs/adim-9-tasarim.md`). `rotalar/ara_katman.py`: read-only demo (K25) and production
  security headers (K27, `docs/adim-11-tasarim.md`).
- `servisler/`: business rules. Does NOT import FastAPI, does not raise HTTPException.
  CSV/Excel import (`docs/adim-4b-tasarim.md`): `ice_aktarma` is the pure core (reading, mapping, converters;
  no database), `ice_aktarma_yaz` writes in a single transaction (UPSERT, package chain, renewal risk),
  `ice_aktar` is the command.
- `semalar/`: Pydantic request/response schemas.
- `models.py`: mirrors columns only. SQL is the single source of the schema.
- `faz1_sema.sql`: readable schema source. `alembic/sql/0001_faz1_sema.sql`: the same, without BEGIN/COMMIT.
- `sentetik/`: BG/NBD-based synthetic data generator. The loader writes only to a database whose name ends in `_demo`.
  `disa_aktar`: writes a business's member/package/check-in data to three CSVs in the import format (K41 round trip;
  _demo only).
  `demo_tazele`: shifts the dates of [DEMO] businesses to today (K11–K16, `docs/adim-9-tasarim.md`).
  `demo_kur`: rebuilds the demo database from scratch in one command, with fixed seeds and reference day 2026-10-01 (K24).
- `analitik/`: models (V1, BG/NBD, MBG/NBD, Gamma-Gamma, renewal probability), explanation (why risky); knows no database.
- `backtest/`: model comparison on synthetic scenarios (S0–S6); no database.
- `sablonlar/`: Jinja2 HTML templates (weekly report). `sablonlar/web/`: web panel templates.
- `statik/`: web panel static files (htmx.min.js 2.0.4, panel.css); served under `/statik`.
- `Dockerfile`, `.dockerignore`: production image (python:3.14-slim, non-root user; Render builds the image, K28).
- `requirements-uretim.txt`: runtime dependencies (with the `requirements.txt` versions); updated on a new runtime
  import.
- `.github/workflows/`: `demo-tazele.yml` (nightly refresh of the live demo, K23) and `demo-kur.yml` (manual, full
  rebuild with the confirm word "KUR", K24).

## Databases
| Name | Purpose | Rule |
|---|---|---|
| `panosu` | Live; real business data only | Read-only queries only. Every write needs explicit approval. `alembic upgrade` is never run (approved `stamp` only). |
| `panosu_test` | pytest | Can be dropped and rebuilt with `alembic upgrade head` |
| `panosu_demo` | Synthetic data, demo, backtest | Set up; 5 [DEMO] businesses (+ local only: [DEMO] Butik Kopya, the import copy of Butik Reformer, manual trial of step 4b-1, owner kopya@panosu.local, no expenses; demo_kur does not rebuild it), synthetic data; [DEMO] Denge Pilates has membership packages, renewal risks and a 330,000 TL demo expense every month from 2026-03 (the month it switched to Panosu) (visit amounts within package periods are 0); [DEMO] Butik Reformer: Faz 0 demo (p ~ Beta(1, 290), 5 new members per month; ~75 active members, 18 months of package/visit history, expenses every month). The loader writes only to _demo names. Shifted to today at every demo server start and every night at 03:00 (K11). |
| Neon `panosu_demo` (live) | Live demo | Only Render (panosu_app) and GitHub Actions connect; never connect from local; setup via demo-kur.yml, refresh via demo-tazele.yml; URLs start with postgresql+psycopg2:// |

Synthetic data is NEVER written to `panosu`.

## Commands
```powershell
.\.venv\Scripts\python.exe -m pytest -v          # full test suite (panosu_test)
.\.venv\Scripts\python.exe -c "import main"      # import check
uvicorn main:app --reload                        # development server, /docs

.\.venv\Scripts\python.exe -m sentetik --sadece-uret                    # generate without touching any database + V1 ROC AUC
.\.venv\Scripts\python.exe -m sentetik --veritabani panosu_demo          # generate and load into panosu_demo
.\.venv\Scripts\python.exe -m sentetik --veritabani panosu_demo --temizle  # delete old [DEMO] data and reload

.\.venv\Scripts\python.exe -m backtest                  # 6 scenarios × 20 seeds; docs/backtest-sonuclari.md + raporlar/backtest/*.csv
.\.venv\Scripts\python.exe -m backtest --tohum-sayisi 2 # quick trial

.\.venv\Scripts\python.exe -m sentetik.paket_uretici --veritabani panosu_demo    # packages for the demo studio (once)
.\.venv\Scripts\python.exe -m sentetik.paket_uretici --veritabani panosu_demo --giderler 2026-10   # demo expenses
.\.venv\Scripts\python.exe -m sentetik.paket_uretici --veritabani panosu_demo --gecmis-giderler   # missing months from 2026-03 (or from the first visit month) to today
.\.venv\Scripts\python.exe -m sentetik.paket_uretici --veritabani panosu_demo --gecmis-giderler --guncelle   # also update demo expenses, delete those before 2026-03
# WARNING: paket_uretici --gecmis-giderler uses the calendar start (2026-03); do not run it after a refresh, it breaks the expense window.
.\.venv\Scripts\python.exe -m sentetik.butik_reformer --veritabani panosu_demo    # second Faz 0 demo (once)
.\.venv\Scripts\python.exe -m sentetik.butik_reformer --veritabani panosu_demo --yeniden   # delete and reload Butik Reformer only
.\.venv\Scripts\python.exe -m sentetik.demo_kullanici --veritabani panosu_demo    # demo@panosu.local (password via getpass)
.\.venv\Scripts\python.exe -m servisler.isletme_ac --veritabani <ad> --eposta <e> --ad-soyad <a> --isletme <ad>  # pilot business (_demo/_test; live: --canli-onay, with separate approval)
.\.venv\Scripts\python.exe -m servisler.rapor_uret --veritabani panosu_demo --isletme <uuid> --cikti raporlar/haftalik.html
.\.venv\Scripts\python.exe -m servisler.yenileme_calistir --veritabani panosu_demo --isletme <uuid>  # renewal risk (_demo/_test)
.\.venv\Scripts\python.exe -m sentetik.demo_sunucu                 # web panel with panosu_demo, 127.0.0.1:8000 (--port); demo refresh at startup and every night at 03:00
.\.venv\Scripts\python.exe -m sentetik.demo_sunucu --tazeleme-yok  # without refresh
.\.venv\Scripts\python.exe -m sentetik.demo_tazele --veritabani panosu_demo --kuru   # demo refresh report, no writes
.\.venv\Scripts\python.exe -m sentetik.demo_tazele --veritabani panosu_demo          # shift [DEMO] data to today + recompute risks
.\.venv\Scripts\python.exe -m sentetik.demo_kur --veritabani <ad>_demo   # delete all [DEMO] data and rebuild from scratch (PANOSU_DEMO_PAROLA in the environment; --uygulama-parolasi-ayarla only on the live deployment)
.\.venv\Scripts\python.exe -m servisler.ice_aktar --veritabani <ad> --isletme <uuid> --kaynak <ad> --uyeler u.csv --paketler p.csv --girisler g.csv   # import PREVIEW (no writes; suggested mapping in raporlar/ice_aktarma_esleme.json); _demo/_test only
.\.venv\Scripts\python.exe -m servisler.ice_aktar ... --esleme raporlar/ice_aktarma_esleme.json --onayla   # write in a single transaction + renewal risk; --anonim: name "Üye xxxxxx", phone/e-mail not read
.\.venv\Scripts\python.exe -m sentetik.disa_aktar --veritabani <ad>_demo --isletme <uuid> --cikti raporlar/disa_aktarma/   # member/package/check-in CSVs (cp1254, ";")
```
Placeholders: `<ad>` = name, `<e>` = e-mail, `<a>` = full name, `<uuid>` = business id.

Test URLs: if `PANOSU_TEST_APP_URL` / `PANOSU_TEST_ADMIN_URL` are set in the environment, they are used; otherwise
`tests/conftest.py` derives them from `PANOSU_VERITABANI_URL` / `PANOSU_MIGRASYON_URL` in `.env`, changing only the
database name to `panosu_test`. In both cases tests do not run on a database whose name does not end in `_test`.

Synthetic data loader: the target must be given with `--veritabani` (not needed only with `--sadece-uret`);
connection URLs are derived from the two URLs in `.env` by changing only the database name. If the name does not end
in `_demo`, it fails before connecting. Ground-truth values are written to `veri/gercek_degerler.csv` (not committed).

Setting up the schema on an empty database: `alembic upgrade head` with `PANOSU_MIGRASYON_URL` pointing to the
target database for that command only.
