#!/usr/bin/env python3
"""Check that all translation files are complete relative to strings.json.

Usage: python tools/check_translations.py
Exit code 0 = all translations complete, 1 = missing keys found.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def flatten(obj: object, prefix: str = "") -> dict[str, object]:
    """Recursively flatten a nested dict into dot-separated keys (skip 'state' sub-dicts)."""
    result: dict[str, object] = {}
    if not isinstance(obj, dict):
        result[prefix] = obj
        return result
    for key, val in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            result.update(flatten(val, full_key))
        else:
            result[full_key] = val
    return result


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def check(base: dict, target: dict, target_name: str) -> list[str]:
    """Return list of keys present in base but missing from target."""
    base_flat = set(flatten(base))
    target_flat = set(flatten(target))
    missing = sorted(base_flat - target_flat)
    extra = sorted(target_flat - base_flat)
    issues: list[str] = []
    for key in missing:
        issues.append(f"  MISSING in {target_name}: {key}")
    for key in extra:
        issues.append(f"  EXTRA   in {target_name}: {key}")
    return issues


def main() -> int:
    repo_root = Path(__file__).parent.parent
    strings_path = repo_root / "custom_components" / "jackery" / "strings.json"
    translations_dir = repo_root / "custom_components" / "jackery" / "translations"

    if not strings_path.exists():
        print(f"ERROR: strings.json not found at {strings_path}", file=sys.stderr)
        return 1

    base = load_json(strings_path)
    print(f"Base: {strings_path.relative_to(repo_root)}")

    all_ok = True
    for lang_file in sorted(translations_dir.glob("*.json")):
        lang = lang_file.stem
        target = load_json(lang_file)
        issues = check(base, target, lang)
        if issues:
            print(f"\n[{lang}] {len(issues)} issue(s):")
            for issue in issues:
                print(issue)
            if any("MISSING" in i for i in issues):
                all_ok = False
        else:
            print(f"[{lang}] OK")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
