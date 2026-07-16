#!/usr/bin/env bash
# Regenerate profile SVG assets and commit them if they changed.
# Run by .github/workflows/update-profile.yml.
set -euo pipefail

python3 scripts/generate_profile.py

if git diff --quiet -- assets; then
	echo "No asset changes."
	exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add assets
git commit -m "chore: refresh profile SVG assets"
git push
