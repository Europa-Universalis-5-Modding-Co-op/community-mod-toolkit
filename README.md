# Community Mod Toolkit

A community-driven toolkit for [Europa Universalis V](https://store.steampowered.com/app/3450310/Europa_Universalis_V/) modding. It provides a mod template and a set of integrated tools for automating common tasks like Steam Workshop uploads, localization translation, and a mod menu creator tool.

This is a companion to the [Community Mod Framework](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework) ([wiki](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki)), which provides shared in-game features like the [Community Mod Menu](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki/Community-Mod-Menu), Custom Alerts, and more. You will need this a dependency if you are using the CMM Visual Editor for creating your mod menu.

**[Full Documentation (Wiki)](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit/wiki)**

## Tools

| Tool | Description |
|------|-------------|
| [Upload Tool](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit/wiki/Upload-Tool) | Build a minimal release folder and upload to Steam Workshop. Supports dev/release separation, workshop page updates, submods, and version-gated uploads. |
| [Translation Tool](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit/wiki/Translation-Tool) | Auto-translate localization files and Workshop titles/descriptions using DeepL or Gemini. |
| [CMM Visual Editor](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit/wiki/CMM-Visual-Editor) | Browser-based visual editor for creating [Community Mod Menu](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-framework/wiki/Community-Mod-Menu) settings without writing code. |

## Quick Start

1. From the root of your mod folder:
   ```bash
   curl.exe -sL https://raw.githubusercontent.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit/toolkit-release/tools/setup.py -o setup.py
   python setup.py
   ```
2. See the [Setup](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit/wiki/Setup) and [Configuration](https://github.com/Europa-Universalis-5-Modding-Co-op/community-mod-toolkit/wiki/Configuration) wiki pages for details.

## Requirements

- **Python 3.x**
- **Git**
- **Europa Universalis V**

## Credits

`upload.py` uses [SteamworksPy](https://github.com/philippj/SteamworksPy) by Philipp J for Steam Workshop uploads and page updates.

## License

GNU General Public License v3.0 &mdash; see [LICENSE](LICENSE) for details.
