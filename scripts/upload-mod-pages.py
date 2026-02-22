import json
import os
import re
import sys

import tomllib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEPENDENCIES_DIR = os.path.join(SCRIPT_DIR, "dependencies")
# Allow importing the bundled steamworks module from scripts/dependencies/steamworks.
sys.path.insert(0, DEPENDENCIES_DIR)

from steamworks import STEAMWORKS

ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# Paths & Configs
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.toml")
METADATA_PATH = os.path.join(ROOT_DIR, ".metadata", "metadata.json")
WORKSHOP_DESCRIPTION_PATH = os.path.join(ROOT_DIR, "assets", "workshop", "workshop-description.bbcode")
TRANSLATIONS_DIR = os.path.join(ROOT_DIR, "assets", "workshop", "translations")
APP_ID = 3450310
WORKSHOP_TRANSLATION_FILENAME_RE = re.compile(r"^workshop_(.+)\.txt$")
WORKSHOP_TITLE_MARKER = "===WORKSHOP_TITLE==="
WORKSHOP_DESCRIPTION_MARKER = "===WORKSHOP_DESCRIPTION==="
WORKSHOP_NO_TRANSLATE_BELOW = "--NO-TRANSLATE-BELOW--"
WORKSHOP_ITEM_ID_TOKEN = "$item-id$"
MAX_DESCRIPTION_LENGTH = 8000

# Steam language codes expected by Workshop updates.
LANGUAGE_TO_STEAM = {
	"english": "english",
	"french": "french",
	"german": "german",
	"spanish": "spanish",
	"polish": "polish",
	"russian": "russian",
	"simp_chinese": "schinese",
	"turkish": "turkish",
	"braz_por": "brazilian",
	"japanese": "japanese",
	"korean": "koreana"
}

def load_config(config_path):
	"""Load config.toml values needed for Workshop uploads."""
	try:
		with open(config_path, "rb") as f:
			data = tomllib.load(f)
	except FileNotFoundError:
		print(f"Error: Config file not found: {config_path}")
		return None, None, None
	except Exception as e:
		print(f"Error reading config file: {e}")
		return None, None, None

	source_language = data.get("source_language")
	if not source_language:
		print(f"Error: source_language not set in {config_path}")
		return None, None, None

	source_language = str(source_language).strip().lower()
	if source_language not in LANGUAGE_TO_STEAM:
		valid = ", ".join(sorted(LANGUAGE_TO_STEAM.keys()))
		print(f"Error: Unsupported source_language '{source_language}'.")
		print(f"Supported values: {valid}")
		return None, None, None

	upload_item_id = data.get("workshop_upload_item_id")

	if upload_item_id is None:
		print("Error: workshop_upload_item_id not set in config.toml.")
		return None, None, None

	# The workshop item ID must be a positive integer.
	item_id = _parse_int(upload_item_id, "item id")
	if item_id is None:
		return None, None, None

	return source_language, item_id

def read_text(path):
	"""Read a UTF-8 text file, returning None on missing/failed reads."""
	try:
		with open(path, "r", encoding="utf-8-sig") as f:
			return f.read()
	except FileNotFoundError:
		return None
	except Exception as e:
		print(f"Warning: Failed to read '{path}': {e}")
		return None

def load_mod_title(metadata_path):
	"""Load and sanitize the workshop title from metadata.json."""
	try:
		with open(metadata_path, "r", encoding="utf-8-sig") as f:
			data = json.load(f)
	except FileNotFoundError:
		print(f"Warning: Metadata file not found: {metadata_path}")
		return None
	except Exception as e:
		print(f"Warning: Failed to read metadata file '{metadata_path}': {e}")
		return None

	title = data.get("name")
	if not title:
		print(f"Warning: Metadata 'name' not found in {metadata_path}")
		return None

	title = str(title)
	if title.endswith(" Dev"):
		title = title[:-4].rstrip()
	return title.strip()

def _parse_int(value, label):
	"""Parse a positive integer with a friendly error message."""
	try:
		parsed = int(value)
	except (TypeError, ValueError):
		print(f"Error: Invalid {label} '{value}'. Expected an integer.")
		return None
	if parsed <= 0:
		print(f"Error: Invalid {label} '{value}'. Expected a positive integer.")
		return None
	return parsed

def parse_workshop_translation(text):
	"""Extract title/description sections from a combined workshop translation file."""
	title = None
	description = None
	current = None
	buffer = []

	def flush():
		nonlocal title, description, buffer, current
		content = "".join(buffer)
		if current == "title":
			cleaned = content.strip()
			title = cleaned if cleaned else None
		elif current == "description":
			description = content
		buffer = []

	for line in text.splitlines(keepends=True):
		stripped = line.strip()
		if stripped == WORKSHOP_TITLE_MARKER:
			flush()
			current = "title"
			continue
		if stripped == WORKSHOP_DESCRIPTION_MARKER:
			flush()
			current = "description"
			continue
		if current:
			buffer.append(line)

	flush()
	return title, description

def split_workshop_description(text):
	"""Remove the no-translate marker line while keeping the remainder for source uploads."""
	if text is None:
		return None
	lines = text.splitlines(keepends=True)
	for idx, line in enumerate(lines):
		if line.strip() == WORKSHOP_NO_TRANSLATE_BELOW:
			return "".join(lines[:idx] + lines[idx + 1:])
	return text

def apply_workshop_item_id(text, item_id):
	"""Replace the $item-id$ token when an item id is available."""
	if text is None or item_id is None:
		return text
	return text.replace(WORKSHOP_ITEM_ID_TOKEN, str(item_id))

def _trim_description(text, lang_label):
	"""Truncate the description to MAX_DESCRIPTION_LENGTH bytes (UTF-8) and warn if truncated."""
	if not text:
		return text

	encoded = text.encode('utf-8')
	if len(encoded) > MAX_DESCRIPTION_LENGTH:
		print(f"Warning: Description for '{lang_label}' exceeds {MAX_DESCRIPTION_LENGTH} bytes. Truncating.")
		# Truncate to MAX_DESCRIPTION_LENGTH bytes and decode, ignoring incomplete characters
		truncated = encoded[:MAX_DESCRIPTION_LENGTH].decode('utf-8', errors='ignore')
		return truncated
	return text

def build_language_updates(source_language, item_id):
	"""Collect base and translated workshop title/description payloads."""
	base_description = read_text(WORKSHOP_DESCRIPTION_PATH)
	if base_description is None:
		print(f"Error: Workshop description file not found: {WORKSHOP_DESCRIPTION_PATH}")
		return None

	base_description = split_workshop_description(base_description)
	base_description = apply_workshop_item_id(base_description, item_id)
	base_description = _trim_description(base_description, source_language)
	base_title = load_mod_title(METADATA_PATH)

	# Always include the source-language title/description.
	updates = [{
		"lang": source_language,
		"steam_lang": LANGUAGE_TO_STEAM[source_language],
		"title": base_title,
		"description": base_description
	}]

	if not os.path.exists(TRANSLATIONS_DIR):
		print(f"Warning: Translations folder not found: {TRANSLATIONS_DIR}")
		return updates

	# Collect any translated workshop files that exist on disk.
	translations = {}
	for filename in os.listdir(TRANSLATIONS_DIR):
		match = WORKSHOP_TRANSLATION_FILENAME_RE.match(filename)
		if not match:
			continue
		lang = match.group(1)
		path = os.path.join(TRANSLATIONS_DIR, filename)
		text = read_text(path)
		if text is None:
			continue
		title_text, desc_text = parse_workshop_translation(text)
		title_text = apply_workshop_item_id(title_text, item_id)
		desc_text = apply_workshop_item_id(desc_text, item_id)
		if title_text is None and desc_text is None:
			continue

		desc_text = _trim_description(desc_text, lang)
		translations[lang] = {"title": title_text, "description": desc_text}

	for lang, entry in translations.items():
		if lang == source_language:
			continue
		if lang not in LANGUAGE_TO_STEAM:
			print(f"Warning: No Steam language mapping for '{lang}', skipping.")
			continue
		updates.append({
			"lang": lang,
			"steam_lang": LANGUAGE_TO_STEAM[lang],
			"title": entry["title"],
			"description": entry["description"]
		})

	return updates

def main():
	"""Upload workshop titles/descriptions for all available languages."""
	(
		source_language,
		item_id
	) = load_config(CONFIG_PATH)

	if not source_language:
		return 1

	updates = build_language_updates(source_language, item_id)
	if updates is None:
		return 1

	print("Workshop language updates:")
	for update in updates:
		print(
			f"  - {update['lang']} ({update['steam_lang']}): "
			f"{'title' if update['title'] is not None else 'no-title'}, "
			f"{'description' if update['description'] is not None else 'no-description'}"
		)

	cwd_before = os.getcwd()
	try:
		# SteamworksPy resolves DLL/appid from the current working directory.
		os.chdir(DEPENDENCIES_DIR)
		# Load the native Steamworks wrapper.
		steam = STEAMWORKS()

		steam.initialize()

		# Use the Workshop interface for the update flow.
		workshop = steam.Workshop

		for update in updates:
			handle = workshop.StartItemUpdate(APP_ID, item_id)
			if not handle:
				print("Error: StartItemUpdate failed. Check app ID and item ID.")
				return 1

			# Set the Workshop update language.
			lang_label = f"{update['lang']} ({update['steam_lang']})"
			lang_result = steam.Workshop_SetItemUpdateLanguage(handle, update["steam_lang"].encode())
			if lang_result is False:
				print(f"Error: SetItemUpdateLanguage failed for {lang_label}.")
				return 1

			if update["title"] is not None:
				# Title is optional per language.
				title_result = workshop.SetItemTitle(handle, update["title"])
				if title_result is False:
					print(f"Error: SetItemTitle failed for {lang_label}.")
					return 1

			if update["description"] is not None:
				# Description is optional per language.
				desc_result = workshop.SetItemDescription(handle, update["description"])
				if desc_result is False:
					print(f"Error: SetItemDescription failed for {lang_label}.")
					return 1

			# Just using an empty change note.
			workshop.SubmitItemUpdate(handle, "")

		print("Workshop updates submitted. Check Steam client for upload progress.")
		return 0
	finally:
		# Always restore cwd.
		os.chdir(cwd_before)

if __name__ == "__main__":
	sys.exit(main())
