# Community Mod Toolkit

A community-driven toolkit for Europa Universalis V (EU5) modding. It provides a mod template and a set of integrated tools for automating common tasks like Steam Workshop uploads and localization translation.

The tools are designed to work together, sharing a common configuration (`tools/config.toml`) and project structure, so you can set up once and use any combination of them.

## Requirements

- **Python 3.x**: Required for running the setup and release scripts.
- **Git**: Required for version control and using the toolkit.
- **Europa Universalis V**: The game this toolkit is designed for.

## Project Structure

```text
community-mod-toolkit/
├── .metadata/                  # Mod metadata and thumbnails
│   ├── metadata.json            # Mod configuration (name, id, tags, etc.)
│   ├── thumbnail.png            # Default/Dev thumbnail template
│   └── thumbnail-release.png    # Release thumbnail template
├── assets/                     # Source assets (images, etc.)
│   └── images/                  # Images used in the mod
│       ├── thumbnail.psd          # Photoshop template for the thumbnail
│       └── thumbnail-alt.psd      # Alternative Photoshop template for the thumbnail
├── tools/                    # Automation scripts
│   ├── dependencies/           # SteamworksPy DLLs, steam_appid.txt, requirements.txt, and steamworks module
│   ├── setup.py                 # Initial project setup script
│   ├── upload.py            # Build a minimal release folder and upload it to Steam Workshop
│   ├── translate.py             # Auto-translate localization files with DeepL or Gemini
│   ├── create-release.sh        # (Internal) Toolkit release management
│   └── reset-release.sh         # (Internal) Toolkit release management
├── in_game/common/dummy.txt    # stub file to create the folder
├── main_menu/
│   └── localization
│       └── english
│          └── tmp_l_english.yml    # localization template file
├── .editorconfig               # Standardizes editor settings for EU5
├── .gitattributes              # Makes all text files use crlf line endings
├── .gitignore                  # Standard gitignore
├── .env-template               # For setting the DeepL & Gemini api keys
├── LICENSE                     # (Internal) Project license
├── README.md                   # (Internal) This file
└── README-TEMPLATE.md          # GitHub repo readme template, will be copied to README.md in the toolkit-release branch.
```
* Files marked as `(internal)` are not included in the release version, and are just for the toolkit's own use. You do not need to copy them, and they will not be included if you run the setup script.

## Setup

### setup.py
This will copy all files from the `toolkit-release` branch into your mod folder, and add the toolkit repository as a remote.
By having the toolkit as a remote, you can easily update the toolkit by merging from the remote `toolkit-release` branch.

1. **Push your mod to a Git repository**:
   * **Existing Mods**: If you haven't already, push your mod to a Git repository.
   * **New Mods**: Create, initialize, and push, a new empty Git repo in the Europa Universalis V/mod folder.
2. a) From the root of your mod folder, run:
   ```bash
   curl -sL https://raw.githubusercontent.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit/toolkit-release/tools/setup.py -o setup.py && python setup.py
   ```
   *Note: The script will not overwrite any existing files and can be run on existing repositories safely.*

After running, the setup script will delete itself and should not need to be used again.

Once the toolkit files are in place, install the Python dependencies:

### Manual Setup
1. Copy any files you want to use from the `toolkit-release` branch into your mod folder.
2. Install the Python dependencies:
```bash
pip install -r tools/dependencies/requirements.txt
```

Note that without the toolkit remote, you will have to manually check and copy over updates to the toolkit.

If you are familiar with Git, you can also manually add the remote for ease of updating.

## Provided Tools

### upload.py
Builds a minimal release folder and uploads to Steam Workshop, and can also upload Workshop page titles/descriptions.
* Tooling, git files, and anything else you don't want on the workshop will get omitted from the release version.
* Separate IDs, names, and (optionally) thumbnails allow you to easily swap between your dev, and workshop versions through the in-game mod manager.
* Makes it easy to swap between for joining multiplayer sessions.
* Can more easily swap to the released version to verify reported issues.
* Pushes the release version straight to Steam Workshop using the item id from `tools/config.toml`.
* By default, uploads are controlled by `upload_mod_by_default`, `upload_workshop_pages_by_default`, and `upload_submods_by_default` in `tools/config.toml`.
* Use `--mod`, `--workshop-pages`, and/or `--submods` to override config defaults for that run.
* Use `--dev` to target the dev Workshop item with the dev thumbnail and name.
* If the configured Workshop item id is `0`, the script will create a new item and write the id back to `tools/config.toml`.
* Use `--submods` to upload submods from `submods/` using the `[[submods]]` mapping in `tools/config.toml`.
* Optional version gating (`upload_only_on_version_change`) only uploads mod/submods when `metadata.json` `version` changed since the last successful upload.

To use the script:
1. **Modify Metadata**: Edit `.metadata/metadata.json` adding ` Dev` and `.dev` to the name and id respectively.
2. **(optionally) Add Separate Release/Dev Thumbnails**: If you want to use a different thumbnail for the release version:
   * The dev thumbnail will use `.metadata/thumbnail.png`.
   * Make the release thumbnail `.metadata/thumbnail-release.png` (if it does not exist, the `.metadata/thumbnail.png` will be used for both).
3. **(optionally) Configure Included Files**: By default, the release version only includes the `.metadata/`, `in_game/` and `main_menu/` folders.
   * If you want to include more files (i.e., LICENSE), you can add them to the `SOURCES` list in `tools/upload.py`.
4. **Set the Workshop item ID**: Update `workshop_upload_item_id` in `tools/config.toml`, or set it to `0` to create a new item on first upload.
5. **Set default upload targets**: Configure `upload_mod_by_default`, `upload_workshop_pages_by_default`, and `upload_submods_by_default` in `tools/config.toml`.
6. **(optional) Enable version-gated uploads**: Set `upload_only_on_version_change = true` in `tools/config.toml`.
   * The last successful uploaded versions are stored in `tools/dependencies/.upload_versions.json` (created automatically on first use).
   * Main mod uses `.metadata/metadata.json` `version`; each submod uses `submods/<name>/.metadata/metadata.json` `version`.
7. **(optional) Configure dev uploads**: Set `workshop_upload_item_id_dev` (or `0` for first-time creation) and `workshop_dev_name` in `tools/config.toml` for `--dev`.
8. **(optional) Configure submods**: Add `[[submods]]` entries to `tools/config.toml` for `--submods`:
   ```toml
   [[submods]]
   mod_id = "my_submod_1"
   workshop_id = 1234567890

   [[submods]]
   mod_id = "my_submod_2"
   workshop_id = 0
   ```
   Any submod found in `submods/` without a matching `mod_id` entry will be uploaded as a new Workshop item and written back to the config.
9. **Run `upload.py`**: When ready to run uploads using your configured default targets (Steam must be running):
   ```bash
   python tools/upload.py
   ```
   If mod upload is enabled, this will create a new folder `../mod-name-release` with:
   * The metadata.json file from `.metadata/` with " Dev" and ".dev" removed from the name and id respectively.
   * The thumbnail from `.metadata/thumbnail-release.png` or the default thumbnail if it doesn't exist.
   * The `in_game/`, `main_menu/` and any other files specified in the `SOURCES` list of `tools/upload.py`.
   * Uploads that release folder to the Workshop item specified in `tools/config.toml`.
   If workshop-page upload is enabled, it also uploads title/description updates from workshop source/translation files.
10. **(optional) Run a dev upload**:
   ```bash
   python tools/upload.py --dev
   ```
   This will create a new folder `../mod-name-dev` and upload it using the dev Workshop item id, keeping the dev mod id and dev thumbnail.
11. **(optional) Upload only mod files**:
   ```bash
   python tools/upload.py --mod
   ```
12. **(optional) Upload only workshop pages**:
   ```bash
   python tools/upload.py --workshop-pages
   ```
13. **(optional) Upload both explicitly (ignoring config defaults)**:
   ```bash
   python tools/upload.py --mod --workshop-pages
   ```
14. **(optional) Upload submods**:
   ```bash
   python tools/upload.py --submods
   ```
   This uploads every submod in `submods/` using its metadata `id` and `name`, creating Workshop items as needed.
15. **(optional) Enable submod uploads by default**:
   * Set `upload_submods_by_default = true` in `tools/config.toml`.
   * Then `python tools/upload.py` will include submod uploads without needing `--submods`.

### translate.py
Auto-translates localization files using DeepL or Gemini-3-Flash, and can optionally translate Steam Workshop titles/descriptions using DeepL or Gemini-3-Flash.
It reads from `main_menu/localization/<source_language>` and writes translated `.yml` files for every EU5 supported language.
Localization translation and workshop translation are independent, so either side can be missing and the script will continue with what is available.

#### Setup
1. Copy `.env-template` to `.env`.
2. Add your DeepL API key as `DEEPL_API_KEY=your_key_here`.
3. If you plan to use Gemini for localization or workshop translations, add `GEMINI_API_KEY=your_key_here` to `.env`.
4. Review and change any settings you want in `tools/config.toml`
   * `source_language` (english, french, german, spanish, polish, russian, simp_chinese, turkish, braz_por, japanese, korean)
   * `localization_translator` (deepl or gemini-3-flash)
   * `gemini_localization_system_prompt`
   * `translate_workshop` (true/false)
   * `translate_submods_by_default` (true/false; default false)
   * `workshop_description_translator` (deepl or gemini-3-flash)
   * `gemini_description_system_prompt`
   * `workshop_title_translator` (deepl or gemini-3-flash)
   * `gemini_title_system_prompt`
5. If using workshop translations:
   * Put your workshop description in `assets/workshop/workshop-description.bbcode`.
   * Your workshop title is pulled from `.metadata/metadata.json` (`name`), with a trailing ` Dev` removed if present.
   * `$item-id$` in the description is replaced with `workshop_upload_item_id` before translating and uploading.
6. Install the dependencies using `pip install -r tools/dependencies/requirements.txt` (if you ran the setup script, this is already done)

#### Usage
```bash
python tools/translate.py
```

To translate the main mod and every submod in `submods/`:
```bash
python tools/translate.py --submods
```

To include submods by default without passing `--submods`:
* Set `translate_submods_by_default = true` in `tools/config.toml`.
* Then `python tools/translate.py` will process the main mod and all submods.

#### Optional Inputs
Every input part is optional (localization files, workshop metadata, workshop description, and workshop template), and the script processes whatever exists.
Example: if a submod has only `workshop/workshop-description.bbcode` and no localization folder, `python tools/translate.py --submods` still translates that workshop description and skips localization for that submod.

#### --submods Path Layout
When `--submods` is used, `translate.py` processes the main mod and each folder under `submods/`.

For each submod `submods/<submod_name>`:
* Localization source is read from `submods/<submod_name>/main_menu/localization/<source_language>/`.
* Translated localization files are written to `submods/<submod_name>/main_menu/localization/<target_language>/`.
* Workshop title is read from `submods/<submod_name>/.metadata/metadata.json` (`name`, with trailing ` Dev` removed).
* Workshop description is read from `submods/<submod_name>/workshop/workshop-description.bbcode`.
* Workshop translation outputs are written to `submods/<submod_name>/workshop/translations/`.
* Workshop template path is `submods/<submod_name>/workshop/translations/translation_template.txt` (fallback order: submod template, then main template, then default format).

#### Behavior
* Preserves EU5 localization tags like `[...], $...$, @...!, #...#!`.
* Automatically skips lines that consist purely of tags or formatting characters.

#### Caching and Updates
* Hashes are stored in `tools/dependencies/.translate_hashes.json`; delete this file to force re-translation.
* Localization keys that have not changed since the last translation are skipped.
* Workshop descriptions are re-translated only when the corresponding `workshop-description.bbcode` changes (main mod or submod), or when the selected provider changes.
* Workshop titles are generated once and never overwritten (delete the translated title files to force re-translation).
* To disable an output language, remove its entry from `TARGET_LANGUAGES` in `tools/translate.py`.

#### Localization Tags
* `# NO-TRANSLATE` skips a single line.
* `# NO-TRANSLATE BELOW` skips the current line and everything below until the end marker.
* `# NO-TRANSLATE END` ends a `# NO-TRANSLATE BELOW` block (optional; the block can run to EOF).
* `# LOCK` prevents overwriting a translated output line.

#### Workshop Tags and Tokens
* `--NO-TRANSLATE-BELOW--` skips that line and anything below it for workshop translations.
* `$item-id$` is replaced with `workshop_upload_item_id` before translation or upload.
* `===WORKSHOP_TITLE===` marks the title block in translation outputs/templates.
* `===WORKSHOP_DESCRIPTION===` marks the description block in translation outputs/templates.
* `$Translated-Title$`, `$Original-Title$`, `$Translated-Language$`, `$Original-Language$`, `$Translated-Description$`, `$Original-Description$` are optional tokens for `assets/workshop/translations/translation_template.txt`.

#### Workshop Output
* Translated workshop titles/descriptions are written to `assets/workshop/translations/`.
* When using `--submods`, workshop outputs are written per submod to `submods/<submod_name>/workshop/translations/`.
* You can customize the output format by editing `assets/workshop/translations/translation_template.txt` (or each submod template path when using `--submods`).
* Template resolution order for submods is: submod template -> main mod template -> built-in default format.
* Keep the `===WORKSHOP_TITLE===` and `===WORKSHOP_DESCRIPTION===` markers in the template.
* If the template is missing or invalid, the script falls back to the default output format.

#### Limitations
* DeepL's free tier allows 500k characters per month.
* Gemini's free tier allows 20 requests per day, which allows 2x workshop descriptions, or 1x title+description per day. Localization translation uses far more requests and will exceed the free tier quickly.
* Machine translation is imperfect; expect occasional mistakes.
* Gemini generally seems to perform better than DeepL for the workshop page translations but has lower limits.

## Contributing

Contributions are welcome! This is a community toolkit and anyone can add new tools, improve existing ones, or fix bugs.

### Adding a New Tool
1. Add your script to the `tools/` folder.
2. Document it in this README under **Provided Tools** following the existing format.
3. If your tool has additional Python dependencies, add them to `tools/dependencies/requirements.txt`.
4. Submit a pull request with a clear description of what your tool does and how to use it.

### General Guidelines
* Follow the existing code style and patterns (e.g., using `tools/config.toml` for user configuration).
* Ensure your tool works from the mod root directory.
* Test with both new and existing mod setups before submitting.

## Credits

`upload.py` uses [SteamworksPy](https://github.com/philippj/SteamworksPy) by Philipp J for Steam Workshop uploads and page updates.

## License

This project is licensed under the GNU General Public License v3.0; use and modification are allowed with or without attribution.

See the [LICENSE](LICENSE) file for details.
