# Ritmeva: public landing page and visible rename

Status: decided 2026-10-03 (owner approved the prototype v5; technical choices delegated to the designer).
Scope: make the approved landing page the live home page and rename user-visible "Panosu" text to "Ritmeva".
Out of scope: the CSV upload screen (step 4b-3, needs database writes; built when the first firm agrees to a pilot),
a custom domain, renaming the repository, the Render service, Python modules, databases or cookies.

## Decisions

**K53 Home page.** `GET /` always renders `sablonlar/web/tanitim.html`. It reads no session, opens no database
connection and sets no cookie, so it stays fast and works while Neon sleeps. The demo starts at `/giris` (which already
redirects a signed-in user to `/pano`). Before this step `/` redirected to `/giris` or `/pano`; the test for that is
split: `/pano` without a session still redirects to `/giris`, `/` now returns the landing page.

**K54 Files.** The page is a standalone template (it does not extend `taban.html`; the landing layout shares nothing
with the panel shell). New files: `sablonlar/web/tanitim.html`, `statik/tanitim.css`, `statik/tanitim.js`.
`statik/panel.css` is unchanged (the uptime monitor and the Render health check request it).

**K55 No third-party requests.** three.js r128 (MIT) is vendored as `statik/vendor/three.min.js`; the fonts
(Bricolage Grotesque 500/700/800, IBM Plex Sans 400/500/600, IBM Plex Mono 400/500; SIL OFL 1.1; latin and latin-ext
subsets, woff2) live in `statik/yazitipi/`. License texts sit next to the files. Reason: the page promises "member
data never leaves your server"; a CDN or Google Fonts request would send every visitor's IP address to a third party
(KVKK/GDPR exposure) and adds an outage point. Cost: about 0.9 MB of static files in the repo, served once and cached.
If WebGL or the script is unavailable, the static SVG mark in `.stage` stays visible; `prefers-reduced-motion`
stops the animations.

**K56 Pilot calendar link.** New optional setting `PANOSU_PILOT_TAKVIM_ADRESI` (must start with `https://`).
Set: the CTA button "Takvimden saat seç" opens it in a new tab. Unset: the button opens the demo and a short
"coming soon" line is shown. The link is added later in Render's environment, without a code change. No form, so
the site collects no personal data.

**K57 Visible rename.** Page titles and the panel header brand say "Ritmeva"; the header brand links to `/` when
signed out and to `/pano` when signed in. FastAPI title becomes "Ritmeva API". README heading names Ritmeva and
points the demo link to `/giris`. Unchanged on purpose: repository name, Render URL `panosu.onrender.com`, module,
database, role and cookie names, the Docker user, and the demo login `demo@panosu.local` (changing it touches the
demo database, a GitHub secret and Render variables; separate small task if wanted).

**K58 Copy rules.** No "AI / yapay zeka" claim (the FAQ says plainly it is a statistical model, MBG/NBD). No prices.
Every example number is labeled synthetic. Founder line: "matematik okuyan ve olasılık modelleri üzerine çalışan" (2026-10-10; was "matematikçi").

**K59 Tests (`tests/test_tanitim.py`).** `/` returns 200 with no `Set-Cookie`, also with a stale session cookie;
the page has no `src`/`href` to another host except the GitHub repository link; every `/statik/...` reference in the
page and every `url(...)` in `tanitim.css` returns 200; calendar setting set and unset; the setting rejects non-https
values; `/giris` title says Ritmeva.

## Additions 2026-10-04 (K72-K75)

K64-K71 are used by the pilot kit (`docs/adim-pilot-tasarim.md`).

**K72 Founder name and contact on the landing page.** The FAQ answer "Arkasında kim var?" names Hüseyin Aytekin (the
K58 founder line stays) and ends with the e-mail `ritmeva.iletisim@gmail.com` and the LinkedIn profile. The footer
shows the name, a mailto link and LinkedIn; "Canlı demo" and "GitHub" stay. Pilot box: with a calendar address, the
calendar button plus "Takvim uymuyorsa: <e-mail>"; without one, the demo button plus "Görüşme için bize yazın:
<e-mail>", which replaces the K56 "coming soon" line. `.cta .soon` is now 14 px (`.cta p` used to override it). No
phone number. LinkedIn and mailto are links opened on click, not requests the page makes, so K55 holds. Tests: the
allowed absolute addresses are the GitHub repository and the LinkedIn profile; every `target="_blank"` link carries
`rel="noopener"`; name and mailto are present with and without the calendar; no "öğrenci", no "yapay zekâ destekli".

**K73 Share card (Open Graph / Twitter).** `og:type`, `og:site_name`, `og:locale` (tr_TR), `og:title` and
`og:description` (same text as `<title>` and the meta description), `og:image` with width, height and alt, and
`twitter:card=summary_large_image`. `og:url` and `og:image` are absolute (`url_for`), because link previews ignore
relative URLs. The image is self-hosted: `statik/medya/ritmeva-paylasim.jpg`, 1200x630. On Render uvicorn runs with
`--proxy-headers`, so the URLs come out as https; the owner checks this after deploy, not a test. Tests: both values
start with `http`, the image path is `/statik/medya/ritmeva-paylasim.jpg` and it is served as `image/jpeg`.

**K74 Self-hosted promo video.** New section "90 saniye" (`id="video"`, not in the nav) between the three answers and
`#kanit`: `statik/medya/ritmeva-tanitim.mp4` (H.264/AAC, 88.5 s, 1920x1080, 6.8 MB, moov box first) with the poster
`statik/medya/ritmeva-afis.jpg` (1280x720), caption "all members and amounts are synthetic demo data". The video is
`preload="none"`, has no autoplay and has `playsinline`, so it downloads nothing until the visitor presses play.
Not a YouTube/Vimeo embed: that would be a third-party request on page load (K55). Starlette `StaticFiles` answers
Range requests with 206, which Safari on iPhone requires. Cost: 6.8 MB in git history and in the Docker image; a new
cut adds about as much again. No Git LFS (owner decision). Tests: exactly one `<video>`, `preload="none"`, no
`autoplay`, poster and source under `/statik/medya/` and served, `Range: bytes=0-99` returns 206 with 100 bytes;
every `src` and `poster` on the page is same-origin or `data:`.

**K75 Source-available license.** `LICENSE` at the repository root: the code may be read, run on one's own computer
to evaluate or learn, and quoted briefly with attribution; commercial use (in a product, for customers, inside a
business), offering it as a hosted service, and copying or redistributing it need prior written permission from the
copyright holder. This is not an open-source license. README ends with a short "Lisans" section pointing to it and
to the contact e-mail.
