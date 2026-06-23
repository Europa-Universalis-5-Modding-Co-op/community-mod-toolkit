# EU5 Mod Bug-Report Intake

A self-hosted, anonymous bug-report intake for Europa Universalis V mods. A
reporter opens a per-mod link, fills in structured fields, and uploads their
save. The save is the quality filter: a required save means lazy "doesn't work"
reports mostly do not get sent, and what arrives is reproducible.

The intake files a GitHub issue (as a bot, so the reporter needs no account) and
posts a Discord notification, scoped per mod. It runs entirely on Cloudflare and
is yours to own.

This folder is dev-only. It is stripped from the toolkit release branch and is
never merged into other mods. To use it, deploy your own instance with the wizard
below.

## How it works

EU5 saves are large (measured 22-435 MB), so the save never streams through the
backend. The flow is two phases:

1. The browser asks the Worker for a presigned upload URL (after passing
   Turnstile and a per-IP rate limit).
2. The browser PUTs the save straight to R2 using that URL. The bytes bypass the
   Worker entirely.
3. The browser tells the Worker it is done. The Worker confirms the object exists,
   matches the declared size, and starts with the EU5 `SAV` magic, then files the
   GitHub issue and posts to Discord.

Saves are intentionally public: the bucket is exposed read-only on a custom
domain, and the issue links directly to the save. Only the write path is gated.

## What you need

- A Cloudflare account (free tier is fine).
- A domain already added to Cloudflare. Two subdomains are used: one for the page
  and API (for example `report.yourdomain.com`), one for public saves (for
  example `saves.yourdomain.com`).
- Node.js 18+ and npm.
- A GitHub repo per mod where issues should land.
- A Discord webhook per mod (optional but recommended).

## Quick deploy (wizard)

From this `bug-reporter/` folder:

```bash
npm install
npx wrangler login
python deploy.py
```

The wizard prompts for your domains, limits, Turnstile keys, R2 API token,
GitHub credentials, and mod list, then:

- creates the R2 bucket, sets CORS, adds the 60-day deletion rule, and connects
  the public saves domain;
- creates a KV namespace and writes its id into `wrangler.toml`;
- renders `wrangler.toml` and `config/mods.toml` from your answers;
- deploys the Worker and the static page;
- pushes every secret with `wrangler secret put`.

Run `python deploy.py --dry-run` first to see exactly what it will do without
changing anything.

You still do these by hand (the wizard tells you when):

- Create the Turnstile widget and the R2 API token in the Cloudflare dashboard,
  and paste the keys when asked.
- Create the GitHub App (or a fine-grained PAT) and install it on each mod repo.
- Create the Discord webhooks and paste the URLs.
- Add the page domain as a custom domain on the Pages project.

## Local development

```bash
npm install
cp .dev.vars.template .dev.vars   # fill in the test values
# Render wrangler.toml: run `python deploy.py --dry-run` (no Cloudflare changes),
# or copy wrangler.toml.template to wrangler.toml and fill in the placeholders.
npm run dev                       # serves the page and /api together on :8787
```

`npm run dev` runs `wrangler dev --assets public`, so the static page and the
`/api/*` endpoints share one origin at `http://localhost:8787`. Open
`http://localhost:8787/?mod=<id>` where `<id>` is a mod from `config/mods.toml`.

For local testing, use Cloudflare's Turnstile test keys: site key
`1x00000000000000000000AA` (always passes) in `config/mods.toml`, and secret
`1x0000000000000000000000000000000AA` in `.dev.vars`. Add `http://localhost:8787`
to the R2 bucket CORS origins so uploads work locally.

## Configuration

`config/mods.toml` holds everything that is not a secret. See
`config/mods.template.toml` for the annotated field reference. The wizard
rewrites this file from your answers; you can also edit it by hand and re-run the
wizard to re-render `wrangler.toml`.

Per-mod blocks set the `?mod=` id, the display name, the GitHub repo, the issue
labels, and the name of the Discord webhook secret.

## Secrets

These are set in Cloudflare with `wrangler secret put` (the wizard does this) and
never live in the repo:

- `TURNSTILE_SECRET`
- `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
- GitHub App: `GH_APP_ID`, `GH_APP_PRIVATE_KEY`; or a PAT: `GH_PAT`
- `DISCORD_WEBHOOK_<MODID>`, one per mod, named by each mod's `webhook_env`

The account id and bucket name are not secret and live in `wrangler.toml`.

## Routing

The page is served by Cloudflare Pages on `report.yourdomain.com`, and the Worker
takes `report.yourdomain.com/api/*` via a route in `wrangler.toml`. The page calls
the API with same-origin relative paths. After the first deploy, confirm in the
dashboard that the Worker route is active over the Pages domain (Workers > your
worker > Triggers). If the route does not take precedence over Pages on your
zone, the fallback is to serve the page from the Worker too: deploy with an
`[assets]` binding pointing at `public/` and drop the separate Pages deploy.

## Save validation and size

A real `.eu5` save begins with the ASCII bytes `SAV`. The browser checks the
extension, size, and magic before uploading; the Worker re-checks the size and
magic on the stored object before filing. The default size cap is 500 MB, set by
`max_upload_bytes`.

## Compression

`compress_in_browser` is a reserved flag and is off. The `SAV` container may be
uncompressed, so gzip could shrink uploads. Before enabling it, gzip a real
`.eu5` and confirm a meaningful reduction; turning the flag on without wiring the
client and finalize paths to gzip does nothing yet.

## Retention

An R2 lifecycle rule deletes objects under `saves/` after 60 days. Issues keep
the link, which stops resolving once the save is deleted.

## Troubleshooting

- Upload fails with a CORS error: the bucket CORS origins must include your page
  origin (and `http://localhost:8787` for local dev).
- Turnstile always fails: the site key in `config/mods.toml` and the
  `TURNSTILE_SECRET` must be from the same widget.
- Issue is not created (GitHub 401/403): the App must be installed on that repo,
  or the PAT must have Issues write on it. The upload is kept and the reporter is
  told to retry, so reports are not lost.
- `/api/*` returns the page HTML instead of JSON: the Worker route is not active
  over the Pages domain. See Routing above.
