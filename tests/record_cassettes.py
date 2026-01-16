#!/usr/bin/env python3
"""
VCR Cassette Recorder for Mysa E2E Tests

This script records real API responses for VCR-style testing.
Run this OUTSIDE of pytest to capture cassettes.

Usage:
    python tests/record_cassettes.py

Credentials are loaded from ~/.mysa_debug_auth.json (same as mysa_debug.py)
"""
import json
import os
import sys
from pathlib import Path

# Add custom_components to path
ROOT_DIR = Path(__file__).parent.parent
MYSA_DIR = ROOT_DIR / "custom_components" / "mysa"
sys.path.insert(0, str(MYSA_DIR))

from mysa_auth import login, auther, CLIENT_HEADERS, BASE_URL, REGION

CASSETTE_DIR = Path(__file__).parent / "cassettes"
AUTH_FILE = Path.home() / ".mysa_debug_auth.json"


def filter_sensitive(data: dict) -> dict:
    """Filter sensitive data from cassette recordings."""
    if not isinstance(data, dict):
        return data

    filtered = {}
    sensitive_keys = {"password", "accesstoken", "idtoken", "refreshtoken", "authorization"}

    for key, value in data.items():
        if isinstance(value, dict):
            filtered[key] = filter_sensitive(value)
        elif isinstance(value, list):
            filtered[key] = [filter_sensitive(v) if isinstance(v, dict) else v for v in value]
        elif key.lower() in sensitive_keys:
            filtered[key] = "FILTERED"
        else:
            filtered[key] = value
    return filtered


def main():
    print("=" * 60)
    print("     VCR CASSETTE RECORDER FOR MYSA TESTS")
    print("=" * 60)

    # Load credentials
    if not AUTH_FILE.exists():
        print(f"\n❌ Credentials file not found: {AUTH_FILE}")
        print("   Run mysa_debug.py first to create credentials.")
        return 1

    with open(AUTH_FILE) as f:
        creds = json.load(f)
    username = creds.get("username")
    password = creds.get("password")

    if not username or not password:
        print("\n❌ Invalid credentials file")
        return 1

    print(f"\n✓ Loaded credentials for: {username}")

    # Authenticate
    print("\nAuthenticating with Mysa...")
    try:
        import boto3
        import requests

        bsess = boto3.session.Session(region_name=REGION)
        user_obj = login(username, password, bsess=bsess)
        session = requests.Session()
        session.auth = auther(user_obj)
        session.headers.update(CLIENT_HEADERS)
        print("✓ Authenticated successfully")
    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")
        return 1

    # Record API responses
    cassette_data = {}

    endpoints = [
        ("users", f"{BASE_URL}/users"),
        ("devices", f"{BASE_URL}/devices"),
        ("devices_state", f"{BASE_URL}/devices/state"),
        ("homes", f"{BASE_URL}/homes"),
    ]

    print("\nRecording API responses...")
    for name, url in endpoints:
        try:
            r = session.get(url)
            r.raise_for_status()
            cassette_data[name] = r.json()
            print(f"  ✓ {name}: {url}")
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            cassette_data[name] = {"error": str(e)}

    # Filter and save
    CASSETTE_DIR.mkdir(exist_ok=True)

    filtered_data = filter_sensitive(cassette_data)
    cassette_path = CASSETTE_DIR / "device_discovery.json"

    with open(cassette_path, "w") as f:
        json.dump(filtered_data, f, indent=2)

    print(f"\n✓ Saved cassette: {cassette_path}")

    # Summary
    devices = cassette_data.get("devices", {})
    device_list = devices.get("Devices", devices.get("DevicesObj", []))
    if isinstance(device_list, dict):
        device_list = list(device_list.values())

    print(f"\n--- Recording Summary ---")
    print(f"  Devices recorded: {len(device_list)}")
    for d in device_list:
        print(f"    • {d.get('Name', 'Unknown')} ({d.get('Model', 'Unknown')})")

    print("\n✓ Done! You can now run VCR tests with:")
    print("  pytest tests/test_vcr_e2e.py -v --no-cov")

    return 0


if __name__ == "__main__":
    sys.exit(main())
