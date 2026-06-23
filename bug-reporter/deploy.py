#!/usr/bin/env python3
"""Guided deploy wizard for the EU5 bug-report intake (Cloudflare Worker + R2)."""

import json
import re
import subprocess
import sys
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WRANGLER_JS = ROOT / "node_modules" / "wrangler" / "bin" / "wrangler.js"
WRANGLER_TEMPLATE = ROOT / "wrangler.toml.template"
WRANGLER_TOML = ROOT / "wrangler.toml"
MODS_TOML = ROOT / "config" / "mods.toml"
PUBLIC_DIR = ROOT / "public"

DRY_RUN = "--dry-run" in sys.argv

DEFAULTS = {
	"worker_name": "eu5-bug-reporter",
	"r2_bucket": "eu5-bug-reporter-saves",
	"max_upload_bytes": 524288000,
	"presign_expiry_seconds": 2400,
	"rate_limit_max": 5,
	"rate_limit_window_seconds": 3600,
}


# --- console helpers -------------------------------------------------------

def hr():
	print("-" * 64)


def section(title):
	print()
	hr()
	print(title)
	hr()


def info(msg):
	print("  " + msg)


def ok(msg):
	print("  [ok] " + msg)


def warn(msg):
	print("  [!] " + msg)


def steps(items):
	for item in items:
		print("    " + item)


def ask(prompt, default=None):
	suffix = " [" + str(default) + "]" if default not in (None, "") else ""
	while True:
		value = input("  " + prompt + suffix + ": ").strip()
		if value:
			return value
		if default is not None:
			return str(default)


def ask_int(prompt, default):
	while True:
		value = ask(prompt, default)
		try:
			return int(value)
		except ValueError:
			warn("Enter a whole number.")


def ask_secret(prompt):
	while True:
		if sys.stdin.isatty():
			value = getpass("  " + prompt + ": ").strip()
		else:
			value = input("  " + prompt + ": ").strip()
		if value:
			info("(captured, " + str(len(value)) + " chars)")
			return value
		warn("This value is required.")


def ask_yes(prompt, default=True):
	hint = "Y/n" if default else "y/N"
	value = input("  " + prompt + " [" + hint + "]: ").strip().lower()
	if not value:
		return default
	return value.startswith("y")


# --- wrangler --------------------------------------------------------------

def wrangler(args, *, capture=False, stdin_text=None, mutating=True):
	printable = "wrangler " + " ".join(args)
	if DRY_RUN and mutating:
		info("DRY-RUN $ " + printable)
		return ""
	cmd = ["node", str(WRANGLER_JS), *args]
	result = subprocess.run(
		cmd,
		cwd=str(ROOT),
		input=stdin_text,
		text=True,
		capture_output=capture,
	)
	if result.returncode != 0:
		if capture and result.stderr:
			print(result.stderr)
		raise SystemExit("  Failed: " + printable + " (exit " + str(result.returncode) + ")")
	return result.stdout or ""


# --- prerequisites ---------------------------------------------------------

def check_prereqs():
	section("Prerequisites")
	if not WRANGLER_JS.exists():
		warn("Node dependencies are not installed.")
		info("Run this first, from the bug-reporter folder:")
		steps(["npm install"])
		raise SystemExit(1)
	ok("wrangler is installed")
	if DRY_RUN:
		info("Dry run: skipping the Cloudflare login check.")
		return
	out = wrangler(["whoami"], capture=True, mutating=False)
	if "You are logged in" not in out and "@" not in out:
		warn("You do not appear to be logged in to Cloudflare.")
		info("Run this, then re-run the wizard:")
		steps(["npx wrangler login"])
		raise SystemExit(1)
	ok("logged in to Cloudflare")


# --- prompts ---------------------------------------------------------------

def collect_answers():
	section("Domain and account")
	info("Your domain must already be on Cloudflare. Both subdomains live under it.")
	answers = {}
	answers["worker_name"] = ask("Worker name", DEFAULTS["worker_name"])
	answers["zone_name"] = ask("Root domain on Cloudflare (e.g. example.com)")
	info("Zone ID is on the domain's Overview page in the Cloudflare dashboard.")
	answers["zone_id"] = ask("Cloudflare Zone ID")
	info("Account ID is on the R2 overview, or in the dashboard URL.")
	answers["account_id"] = ask("Cloudflare Account ID")
	answers["site_domain"] = ask("Reporter page domain", "report." + answers["zone_name"])
	answers["saves_domain"] = ask("Public saves domain", "saves." + answers["zone_name"])
	answers["r2_bucket"] = ask("R2 bucket name", DEFAULTS["r2_bucket"])

	section("Limits")
	answers["max_upload_bytes"] = ask_int("Max upload size (bytes)", DEFAULTS["max_upload_bytes"])
	answers["presign_expiry_seconds"] = ask_int("Presigned-URL lifetime (seconds)", DEFAULTS["presign_expiry_seconds"])
	answers["rate_limit_max"] = ask_int("Presigns allowed per IP per window", DEFAULTS["rate_limit_max"])
	answers["rate_limit_window_seconds"] = ask_int("Rate-limit window (seconds)", DEFAULTS["rate_limit_window_seconds"])

	section("Turnstile (bot protection)")
	info("Cloudflare dashboard > Turnstile > Add widget. Add " + answers["site_domain"] + " as a hostname.")
	answers["turnstile_sitekey"] = ask("Turnstile site key (public)")
	answers["turnstile_secret"] = ask_secret("Turnstile secret key")

	section("R2 API token (for presigned uploads)")
	info("Cloudflare dashboard > R2 > Manage R2 API Tokens > Create (Object Read & Write).")
	answers["r2_access_key_id"] = ask("R2 Access Key ID")
	answers["r2_secret_access_key"] = ask_secret("R2 Secret Access Key")

	section("GitHub (where issues are filed)")
	info("A GitHub App (recommended) files issues as a bot. A fine-grained PAT is the quick path.")
	answers["gh_mode"] = "app" if ask_yes("Use a GitHub App?", True) else "pat"
	if answers["gh_mode"] == "app":
		info("Create the App at github.com/settings/apps/new (or your org's settings).")
		info("Give it only: Repository permissions > Issues: Read and write.")
		answers["gh_app_id"] = ask("GitHub App ID")
		answers["gh_app_key"] = read_private_key()
	else:
		info("Create a fine-grained PAT with Issues: Read and write on the target repos.")
		answers["gh_pat"] = ask_secret("GitHub PAT")

	section("Mods")
	info("Add one entry per mod. The id is the ?mod= value in the report link.")
	answers["mods"] = collect_mods()
	return answers


def read_private_key():
	while True:
		path = Path(ask("Path to the App private key (.pem)")).expanduser()
		if path.is_file():
			return path.read_text(encoding="utf-8")
		if DRY_RUN:
			warn("File not found; using a placeholder for the dry run.")
			return "DRYRUN_PLACEHOLDER_KEY"
		warn("No file at that path.")


def collect_mods():
	mods = []
	while True:
		index = len(mods) + 1
		print()
		info("Mod #" + str(index))
		mod_id = ask("  id (kebab-case, matches the report link)")
		display_name = ask("  display name")
		repo = ask("  GitHub repo (owner/name)")
		webhook = ask_secret("  Discord webhook URL (blank to skip)") if ask_yes("  Add a Discord webhook?", True) else ""
		env_name = "DISCORD_WEBHOOK_" + re.sub(r"[^A-Za-z0-9]", "_", mod_id).upper()
		mods.append({
			"id": mod_id,
			"display_name": display_name,
			"repo": repo,
			"labels": ["bug"],
			"webhook_env": env_name,
			"webhook_url": webhook,
		})
		if not ask_yes("Add another mod?", False):
			return mods


# --- rendering -------------------------------------------------------------

def toml_str(value):
	return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def toml_str_list(values):
	return "[" + ", ".join(toml_str(v) for v in values) + "]"


def render_mods_inline(mods):
	rows = []
	for mod in mods:
		rows.append("  { id = %s, display_name = %s, repo = %s, labels = %s, webhook_env = %s }" % (
			toml_str(mod["id"]),
			toml_str(mod["display_name"]),
			toml_str(mod["repo"]),
			toml_str_list(mod["labels"]),
			toml_str(mod["webhook_env"]),
		))
	return "[\n" + ",\n".join(rows) + "\n]"


def write_mods_toml(answers):
	lines = [
		"# Live bug-reporter configuration, written by deploy.py. No secrets here.",
		"# See config/mods.template.toml for the field reference.",
		"",
		"site_domain = " + toml_str(answers["site_domain"]),
		"saves_domain = " + toml_str(answers["saves_domain"]),
		"turnstile_sitekey = " + toml_str(answers["turnstile_sitekey"]),
		"max_upload_bytes = " + str(answers["max_upload_bytes"]),
		"presign_expiry_seconds = " + str(answers["presign_expiry_seconds"]),
		"rate_limit_max = " + str(answers["rate_limit_max"]),
		"rate_limit_window_seconds = " + str(answers["rate_limit_window_seconds"]),
		"default_labels = " + toml_str_list(["bug"]),
		"compress_in_browser = false",
	]
	for mod in answers["mods"]:
		lines += [
			"",
			"[[mods]]",
			"id = " + toml_str(mod["id"]),
			"display_name = " + toml_str(mod["display_name"]),
			"repo = " + toml_str(mod["repo"]),
			"labels = " + toml_str_list(mod["labels"]),
			"webhook_env = " + toml_str(mod["webhook_env"]),
		]
	MODS_TOML.write_text("\n".join(lines) + "\n", encoding="utf-8")
	ok("wrote config/mods.toml")


def write_wrangler_toml(answers, kv_id):
	template = WRANGLER_TEMPLATE.read_text(encoding="utf-8")
	replacements = {
		"__WORKER_NAME__": answers["worker_name"],
		"__SITE_DOMAIN__": answers["site_domain"],
		"__SAVES_DOMAIN__": answers["saves_domain"],
		"__ZONE_NAME__": answers["zone_name"],
		"__R2_BUCKET__": answers["r2_bucket"],
		"__R2_ACCOUNT_ID__": answers["account_id"],
		"__KV_ID__": kv_id,
		"__TURNSTILE_SITEKEY__": answers["turnstile_sitekey"],
		"__MAX_UPLOAD_BYTES__": str(answers["max_upload_bytes"]),
		"__PRESIGN_EXPIRY_SECONDS__": str(answers["presign_expiry_seconds"]),
		"__RATE_LIMIT_MAX__": str(answers["rate_limit_max"]),
		"__RATE_LIMIT_WINDOW_SECONDS__": str(answers["rate_limit_window_seconds"]),
		"__DEFAULT_LABELS__": toml_str_list(["bug"]),
		"__COMPRESS_IN_BROWSER__": "false",
		"__MODS__": render_mods_inline(answers["mods"]),
	}
	for token, value in replacements.items():
		template = template.replace(token, value)
	WRANGLER_TOML.write_text(template, encoding="utf-8")
	ok("wrote wrangler.toml")


# --- provisioning ----------------------------------------------------------

def provision(answers):
	section("Provisioning Cloudflare resources")

	info("Creating R2 bucket: " + answers["r2_bucket"])
	wrangler(["r2", "bucket", "create", answers["r2_bucket"]])

	info("Setting R2 CORS (uploads from " + answers["site_domain"] + ")")
	cors_file = ROOT / ".cors.tmp.json"
	cors_file.write_text(json.dumps([{
		"AllowedOrigins": ["https://" + answers["site_domain"], "http://localhost:8787"],
		"AllowedMethods": ["PUT"],
		"AllowedHeaders": ["content-type"],
		"ExposeHeaders": ["ETag"],
		"MaxAgeSeconds": 3600,
	}], indent=2), encoding="utf-8")
	try:
		wrangler(["r2", "bucket", "cors", "set", answers["r2_bucket"], "--file", str(cors_file)])
	finally:
		cors_file.unlink(missing_ok=True)

	info("Adding 60-day deletion rule for saves/")
	wrangler(["r2", "bucket", "lifecycle", "add", answers["r2_bucket"], "expire-saves", "saves/", "--expire-days", "60"])

	info("Connecting public saves domain: " + answers["saves_domain"])
	wrangler(["r2", "bucket", "domain", "add", answers["r2_bucket"],
			  "--domain", answers["saves_domain"], "--zone-id", answers["zone_id"]])

	info("Creating KV namespace")
	kv_id = create_kv_namespace(answers["worker_name"] + "-kv")
	ok("KV namespace id: " + kv_id)
	return kv_id


def create_kv_namespace(title):
	if DRY_RUN:
		info("DRY-RUN $ wrangler kv namespace create " + title)
		return "DRYRUN_KV_ID"
	out = wrangler(["kv", "namespace", "create", title], capture=True, mutating=False)
	print(out.strip())
	match = re.search(r'"?id"?\s*[:=]\s*"([0-9a-f]{32})"', out) or re.search(r"([0-9a-f]{32})", out)
	if not match:
		raise SystemExit("  Could not read the KV namespace id from wrangler output.")
	return match.group(1)


# --- secrets and deploy ----------------------------------------------------

def push_secret(name, value):
	info("Setting secret: " + name)
	wrangler(["secret", "put", name], stdin_text=value)


def push_secrets(answers):
	section("Pushing secrets")
	push_secret("TURNSTILE_SECRET", answers["turnstile_secret"])
	push_secret("R2_ACCESS_KEY_ID", answers["r2_access_key_id"])
	push_secret("R2_SECRET_ACCESS_KEY", answers["r2_secret_access_key"])
	if answers["gh_mode"] == "app":
		push_secret("GH_APP_ID", answers["gh_app_id"])
		push_secret("GH_APP_PRIVATE_KEY", answers["gh_app_key"])
	else:
		push_secret("GH_PAT", answers["gh_pat"])
	for mod in answers["mods"]:
		if mod["webhook_url"]:
			push_secret(mod["webhook_env"], mod["webhook_url"])


def deploy(answers):
	section("Deploying")
	info("Deploying the Worker (API)")
	wrangler(["deploy"])
	info("Deploying the static page to Pages")
	wrangler(["pages", "deploy", str(PUBLIC_DIR), "--project-name", answers["worker_name"]])


# --- manual checklist ------------------------------------------------------

def print_checklist(answers):
	section("Done. Remaining manual steps")
	items = []
	if answers["gh_mode"] == "app":
		items.append("1. Install the GitHub App on each mod repo (App settings > Install App).")
	else:
		items.append("1. Make sure the PAT has Issues: write on each mod repo.")
	items += [
		"2. In the Pages project, add the custom domain " + answers["site_domain"] + ".",
		"3. Confirm the Worker route " + answers["site_domain"] + "/api/* is active (Workers > your worker > Triggers).",
		"4. Test with a small file whose first 3 bytes are SAV: open",
		"     https://" + answers["site_domain"] + "/?mod=" + answers["mods"][0]["id"],
		"   fill the form, upload, and confirm the issue and Discord post appear.",
	]
	steps(items)
	print()
	info("Per-mod report links:")
	for mod in answers["mods"]:
		info("  " + mod["display_name"] + ": https://" + answers["site_domain"] + "/?mod=" + mod["id"])


# --- main ------------------------------------------------------------------

def main():
	section("EU5 bug-report intake - deploy wizard")
	if DRY_RUN:
		info("Dry run: prompts and file rendering only, no Cloudflare changes.")
	check_prereqs()
	answers = collect_answers()
	write_mods_toml(answers)
	kv_id = provision(answers)
	write_wrangler_toml(answers, kv_id)
	deploy(answers)
	push_secrets(answers)
	print_checklist(answers)


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		print()
		warn("Cancelled.")
		sys.exit(1)
