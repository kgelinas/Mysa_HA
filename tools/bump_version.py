#!/usr/bin/env python3
"""
Bump version number in all relevant files.
Usage: python3 tools/bump_version.py <new_version>
"""
import argparse
import json
import re
import sys

MANIFEST_PATH = "custom_components/mysa/manifest.json"
README_PATH = "README.md"
CHANGELOG_PATH = "CHANGELOG.md"

def update_manifest(new_version):
    """Update version in manifest.json."""
    print(f"Updating {MANIFEST_PATH}...")
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    old_version = data.get("version")
    if old_version == new_version:
        print(f"  Version already set to {new_version} in manifest.json")
        return

    data["version"] = new_version
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n") # Add trailing newline
    print(f"  Updated from {old_version} to {new_version}")

def update_readme(new_version):
    """Update version badge in README.md."""
    print(f"Updating {README_PATH}...")
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Regex for badge: version-0.8.9-blue.svg
    pattern = r"version-(\d+\.\d+\.\d+)-blue\.svg"

    match = re.search(pattern, content)
    if not match:
        print("  Could not find version badge in README.md")
        return

    old_version = match.group(1)
    if old_version == new_version:
        print(f"  Version already set to {new_version} in README.md")
        return

    new_content = content.replace(
        f"version-{old_version}-blue.svg",
        f"version-{new_version}-blue.svg"
    )
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  Updated from {old_version} to {new_version}")

def check_changelog(new_version):
    """Check if CHANGELOG.md has an entry for the new version."""
    print(f"Checking {CHANGELOG_PATH}...")
    with open(CHANGELOG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Check for [new_version]
    if f"[{new_version}]" in content:
        print(f"  Found entry for [{new_version}]")
    else:
        print(f"  WARNING: No entry found for [{new_version}] in CHANGELOG.md")
        print("  Please add it manually.")

def main():
    parser = argparse.ArgumentParser(description="Bump version number")
    parser.add_argument("version", help="New version number (e.g., 0.9.0)")
    args = parser.parse_args()

    # Basic format validation
    if not re.match(r"^\d+\.\d+\.\d+$", args.version):
        print("Error: Version must be in format X.Y.Z")
        sys.exit(1)

    update_manifest(args.version)
    update_readme(args.version)
    check_changelog(args.version)

    print("\nDone! Don't forget to commit and tag.")
    print(f"git commit -am \"Bump version to {args.version}\"")
    print(f"git tag v{args.version}")

if __name__ == "__main__":
    main()
