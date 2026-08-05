#!/usr/bin/env bash
# release.sh — vollständige Prüfung vor Release-Tag
# Aufruf: ./release.sh v2.x.y
set -euo pipefail

VERSION=${1:-}
if [[ -z "$VERSION" ]]; then
    echo "Fehler: Versionsnummer fehlt."
    echo "Aufruf: ./release.sh v2.x.y"
    exit 1
fi

if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+ ]]; then
    echo "Fehler: Ungültiges Versionsformat '$VERSION' (erwartet: vX.Y.Z)"
    exit 1
fi

echo "=== Release $VERSION ==="
echo ""

# Sicherstellen, dass wir auf main sind und alles gepusht ist
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
    echo "Fehler: Nicht auf Branch 'main' (aktuell: $BRANCH)"
    echo "Bitte zuerst auf main mergen."
    exit 1
fi

UNPUSHED=$(git log origin/main..HEAD --oneline 2>/dev/null | wc -l)
if [[ "$UNPUSHED" -gt 0 ]]; then
    echo "Fehler: $UNPUSHED Commit(s) noch nicht gepusht:"
    git log origin/main..HEAD --oneline
    exit 1
fi

# Tag darf noch nicht existieren
if git rev-parse "$VERSION" &>/dev/null; then
    echo "Fehler: Tag '$VERSION' existiert bereits."
    exit 1
fi

echo "--- Ruff ---"
uv run ruff check custom_components/jackery/
echo "OK"

echo ""
echo "--- mypy ---"
uv run mypy custom_components/jackery/ --no-error-summary 2>&1 | tail -3
echo "OK"

echo ""
echo "--- Translations ---"
python tools/check_translations.py
echo "OK"

echo ""
echo "--- Tests ---"
uv run pytest tests/ -q --tb=short
echo "OK"

echo ""
echo "--- CI-Status (letzte 5 Runs) ---"
gh run list --repo csoscd/ha-solarvault --limit 5
echo ""

read -rp "CI grün für diesen Stand? [j/N] " ci_ok
if [[ "${ci_ok,,}" != "j" ]]; then
    echo "Abgebrochen."
    exit 1
fi

echo ""
echo "--- Tag erstellen und pushen ---"
git tag -a "$VERSION" -m "Release $VERSION"
git push origin "$VERSION"
echo "Tag $VERSION gepusht."

echo ""
echo "--- GitHub Release erstellen ---"
gh release create "$VERSION" \
    --title "$VERSION" \
    --generate-notes \
    --repo csoscd/ha-solarvault

echo ""
echo "Release $VERSION erfolgreich erstellt."
