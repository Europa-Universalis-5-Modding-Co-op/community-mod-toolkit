#!/bin/bash
Commented out to prevent accidental execution.
set -e # Stop the script if any command fails

# --- Configuration ---
VERSION="Devkit v1.0"

# --- Script ---
# 1. Navigate to repo root
cd "$(dirname "$0")/.."

# 2. Switch to main
git checkout main

# 3. Delete release branch everywhere
git branch -D toolkit-release
git push origin --delete toolkit-release

# 4. Create fresh Orphan branch
git checkout --orphan toolkit-release

# 5. Wipe directory
git rm -rf .

# 6. Overwrite everything with the current version from main
git checkout main -- .

# 7. Remove dev-only files
git rm -f README.md
git rm -f tools/create-release.sh
git rm -f tools/reset-release.sh
git rm -f assets/images/mod-id-location.png
git mv -f README-TEMPLATE.md README.md

# 8. Reset Workshop item ID for release branch
config_path="tools/config.toml"
if [[ ! -f "$config_path" ]]; then
  echo "Error: Missing $config_path"
  exit 1
fi

tmp_path="${config_path}.tmp"
awk '
BEGIN { updated = 0 }
/^[[:space:]]*workshop_upload_item_id[[:space:]]*=/ {
  match($0, /^[[:space:]]*workshop_upload_item_id[[:space:]]*=[[:space:]]*/)
  prefix = substr($0, RSTART, RLENGTH)
  rest = substr($0, RSTART + RLENGTH)
  sub(/^[^#[:space:]]+/, "", rest)
  print prefix "0" rest
  updated = 1
  next
}
{ print }
END {
  if (!updated) {
    print "workshop_upload_item_id = 0"
  }
}
' "$config_path" > "$tmp_path"
mv "$tmp_path" "$config_path"
git add "$config_path"

# 9. Commit and Push
git commit -m "$VERSION"
git push origin toolkit-release

# 10. Return to main
git checkout main

# 11. Discard local config changes on main
git checkout -- tools/config.toml
