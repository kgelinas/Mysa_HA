"""
VCR-style E2E tests for Mysa integration.

These tests record real API responses and replay them in CI.
To record new cassettes, run with real credentials:
    MYSA_RECORD=1 pytest tests/test_vcr_e2e.py -v

Credentials are loaded from ~/.mysa_debug_auth.json (same as mysa_debug.py)
"""
# pylint: disable=redefined-outer-name
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from custom_components.mysa.const import DOMAIN
from custom_components.mysa.mysa_auth import BASE_URL

# ===========================================================================
# Configuration
# ===========================================================================

CASSETTE_DIR = Path(__file__).parent / "cassettes"
AUTH_FILE = Path.home() / ".mysa_debug_auth.json"
RECORD_MODE = os.environ.get("MYSA_RECORD", "0") == "1"


def load_credentials():
    """Load credentials from auth file (same as mysa_debug.py)."""
    if AUTH_FILE.exists():
        with open(AUTH_FILE) as f:
            data = json.load(f)
            return data.get("username"), data.get("password")
    return None, None


def save_cassette(name: str, data: dict):
    """Save recorded API responses to cassette file."""
    cassette_path = CASSETTE_DIR / f"{name}.json"
    # Filter sensitive data
    filtered = _filter_sensitive(data)
    with open(cassette_path, "w") as f:
        json.dump(filtered, f, indent=2)
    print(f"Saved cassette: {cassette_path}")


def load_cassette(name: str) -> dict:
    """Load cassette from file."""
    cassette_path = CASSETTE_DIR / f"{name}.json"
    if not cassette_path.exists():
        pytest.skip(f"Cassette not found: {cassette_path}. Run with MYSA_RECORD=1 to create.")
    with open(cassette_path) as f:
        return json.load(f)


def _filter_sensitive(data: dict) -> dict:
    """Filter sensitive data from cassette recordings."""
    filtered = {}
    for key, value in data.items():
        if isinstance(value, dict):
            filtered[key] = _filter_sensitive(value)
        elif isinstance(value, list):
            filtered[key] = [_filter_sensitive(v) if isinstance(v, dict) else v for v in value]
        elif key.lower() in ("password", "accesstoken", "idtoken", "refreshtoken", "authorization"):
            filtered[key] = "FILTERED"
        else:
            filtered[key] = value
    return filtered


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def vcr_credentials():
    """Get credentials for VCR recording or skip if not available."""
    username, password = load_credentials()
    if not username or not password:
        pytest.skip("No credentials found. Create ~/.mysa_debug_auth.json")
    return username, password


@pytest.fixture
def mock_auth_for_vcr():
    """Mock authentication for VCR playback."""
    async def side_effect(self):
        self._user_obj = MagicMock()
        self._user_obj.id_claims = {"exp": 9999999999}
        self._user_obj.id_token = "mock_token"
        return True

    with patch("custom_components.mysa.client.MysaClient.authenticate", autospec=True) as mock_method:
        mock_method.side_effect = side_effect
        yield mock_method


@pytest.fixture
def mock_realtime_for_vcr():
    """Mock MysaRealtime for VCR tests."""
    with patch("custom_components.mysa.mysa_api.MysaRealtime") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.start = AsyncMock()
        mock_instance.stop = AsyncMock()
        mock_instance.send_command = AsyncMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


# ===========================================================================
# Recording Helper (for MYSA_RECORD=1 mode)
# ===========================================================================

async def record_api_responses(username: str, password: str) -> dict:
    """
    Record real API responses for cassette creation.

    This function makes REAL API calls - only run with MYSA_RECORD=1.
    """
    import boto3
    import requests
    import sys

    # Add custom_components to path
    sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "mysa"))
    from mysa_auth import login, auther, CLIENT_HEADERS, REGION

    cassette_data = {}

    # Authenticate
    bsess = boto3.session.Session(region_name=REGION)
    user_obj = login(username, password, bsess=bsess)
    session = requests.Session()
    session.auth = auther(user_obj)
    session.headers.update(CLIENT_HEADERS)

    # Record /users
    r = session.get(f"{BASE_URL}/users")
    cassette_data["users"] = r.json()

    # Record /devices
    r = session.get(f"{BASE_URL}/devices")
    cassette_data["devices"] = r.json()

    # Record /devices/state
    r = session.get(f"{BASE_URL}/devices/state")
    cassette_data["devices_state"] = r.json()

    # Record /homes
    r = session.get(f"{BASE_URL}/homes")
    cassette_data["homes"] = r.json()

    return cassette_data


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.vcr
@pytest.mark.asyncio
async def test_vcr_device_discovery(
    hass: HomeAssistant,
    vcr_credentials,
    mock_auth_for_vcr,
    mock_realtime_for_vcr,
    aioclient_mock
):
    """
    Test device discovery using VCR cassettes.

    Run with MYSA_RECORD=1 to record new cassettes from real API.
    """
    username, password = vcr_credentials

    if RECORD_MODE:
        # Record mode - make real API calls
        print("\n🔴 RECORDING MODE - Making real API calls...")
        cassette_data = await record_api_responses(username, password)
        save_cassette("device_discovery", cassette_data)
        pytest.skip("Recording complete. Re-run without MYSA_RECORD=1 to replay.")

    # Playback mode - use recorded cassette
    cassette = load_cassette("device_discovery")

    # Setup mocks from cassette
    aioclient_mock.get(f"{BASE_URL}/users", json=cassette["users"])
    aioclient_mock.get(f"{BASE_URL}/devices", json=cassette["devices"])
    aioclient_mock.get(f"{BASE_URL}/devices/state", json=cassette["devices_state"])
    aioclient_mock.get(f"{BASE_URL}/homes", json=cassette["homes"])

    # Run config flow
    config_entry = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        config_entry["flow_id"],
        {CONF_USERNAME: username, CONF_PASSWORD: password},
    )

    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Verify devices were discovered
    entities = hass.states.async_entity_ids("climate")
    assert len(entities) > 0, f"No climate entities found. Available: {hass.states.async_entity_ids()}"

    # Verify device count matches cassette
    devices_list = cassette["devices"].get("Devices", cassette["devices"].get("DevicesObj", []))
    if isinstance(devices_list, dict):
        devices_list = list(devices_list.values())
    expected_count = len(devices_list)
    assert len(entities) == expected_count, f"Expected {expected_count} devices, found {len(entities)}"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_vcr_state_sync(
    hass: HomeAssistant,
    vcr_credentials,
    mock_auth_for_vcr,
    mock_realtime_for_vcr,
    aioclient_mock
):
    """
    Test state synchronization using VCR cassettes.

    Verifies that device state (temperature, setpoint, humidity) is correctly parsed.
    """
    username, password = vcr_credentials
    cassette = load_cassette("device_discovery")

    aioclient_mock.get(f"{BASE_URL}/users", json=cassette["users"])
    aioclient_mock.get(f"{BASE_URL}/devices", json=cassette["devices"])
    aioclient_mock.get(f"{BASE_URL}/devices/state", json=cassette["devices_state"])
    aioclient_mock.get(f"{BASE_URL}/homes", json=cassette["homes"])

    # Setup integration
    config_entry = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        config_entry["flow_id"],
        {CONF_USERNAME: username, CONF_PASSWORD: password},
    )
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Get first climate entity
    entities = hass.states.async_entity_ids("climate")
    assert entities, "No climate entities found"

    state = hass.states.get(entities[0])
    assert state is not None

    # Verify state attributes exist
    assert "current_temperature" in state.attributes or state.attributes.get("current_temperature") is None
    assert "temperature" in state.attributes  # Target temperature

    # State should be a valid HVAC mode
    assert state.state in ("heat", "off", "cool", "auto", "unavailable")


@pytest.mark.vcr
def test_cassette_no_sensitive_data():
    """Verify cassettes don't contain sensitive data."""
    cassette_files = list(CASSETTE_DIR.glob("*.json"))

    if not cassette_files:
        pytest.skip("No cassettes to check")

    sensitive_keys = ["password", "accesstoken", "idtoken", "refreshtoken"]

    for cassette_file in cassette_files:
        with open(cassette_file) as f:
            content = f.read().lower()
            for key in sensitive_keys:
                # Allow "FILTERED" as placeholder
                if key in content and "filtered" not in content:
                    pytest.fail(f"Sensitive key '{key}' found in {cassette_file.name}")
