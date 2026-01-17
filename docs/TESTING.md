# Testing Guide

This document provides information for developers and contributors on testing the Mysa Home Assistant integration.

## Running Tests

### Full Test Suite
```bash
pytest tests/ -v
```

### With Coverage
```bash
pytest tests/ --cov=custom_components.mysa --cov-report=term-missing
```

### Specific Test File
```bash
pytest tests/test_auth.py -v
```

## VCR Testing (HTTP Recording/Replay)

VCR tests allow us to record real API interactions once and replay them in CI without requiring actual Mysa credentials.

### What is VCR?

VCR (Video Cassette Recorder) is a testing pattern that:
- Records HTTP requests/responses to "cassettes" (JSON files)
- Replays them in future test runs
- Ensures consistent, fast tests without external dependencies

### Running VCR Tests

**Playback Mode (Default):**
```bash
pytest tests/test_vcr_e2e.py -v
```
Uses pre-recorded cassettes from `tests/cassettes/`.

**Recording Mode (requires real credentials):**
```bash
MYSA_RECORD=1 pytest tests/test_vcr_e2e.py -v
```

### Setting Up Credentials for Recording

Create `~/.mysa_debug_auth.json`:
```json
{
  "username": "your-email@example.com",
  "password": "your-password"
}
```

> **Security:** This file is in `.gitignore` and never committed. Cassettes automatically filter sensitive data.

### Available VCR Tests

| Test | Description |
|------|-------------|
| `test_vcr_device_discovery` | Tests full device discovery flow |
| `test_vcr_state_sync` | Verifies state parsing from API |
| `test_cassette_no_sensitive_data` | Ensures no credentials leaked |

### Cassette Files

Located in `tests/cassettes/*.json`:
- `device_discovery.json` - Full device setup flow

**Sensitive data filtering:**
- Passwords → `"FILTERED"`
- Access tokens → `"FILTERED"`
- ID tokens → `"FILTERED"`
- Refresh tokens → `"FILTERED"`

## Pre-commit Hooks

Run code quality checks:
```bash
pre-commit run --all-files
```

Checks include:
- Pylint
- Trailing whitespace
- JSON/YAML validation
- Test coverage enforcement

## Test Structure

```
tests/
├── cassettes/           # VCR recordings
├── conftest.py          # Shared fixtures
├── test_auth.py         # Authentication tests
├── test_client.py       # HTTP client tests
├── test_mqtt.py         # MQTT protocol tests
├── test_vcr_e2e.py      # End-to-end VCR tests
└── ...                  # Platform-specific tests
```

## Writing New Tests

### Unit Test Example
```python
@pytest.mark.asyncio
async def test_my_feature():
    """Test description."""
    # Arrange
    api = MysaApi("user", "pass", hass)

    # Act
    result = await api.my_method()

    # Assert
    assert result == expected
```

### VCR Test Example
```python
@pytest.mark.vcr
@pytest.mark.asyncio
async def test_vcr_my_feature(vcr_credentials, aioclient_mock):
    """Test using VCR cassettes."""
    if RECORD_MODE:
        # Recording logic
        pass

    # Playback logic
    cassette = load_cassette("my_feature")
    aioclient_mock.get(url, json=cassette["response"])
    # ... test code
```

## Continuous Integration

Tests run automatically on:
- Pull requests
- Pushes to main
- Pre-commit hooks (local)

Coverage requirement: **100%** for modified files.

## Troubleshooting

### "Cassette not found" Error
Run with `MYSA_RECORD=1` to create the cassette, or skip VCR tests:
```bash
pytest tests/ -v -m "not vcr"
```

### Import Errors
Ensure custom components path is correct:
```bash
export PYTHONPATH="${PYTHONPATH}:${PWD}"
```

### Coverage Below 100%
Check which lines are missing:
```bash
pytest --cov=custom_components.mysa --cov-report=html
open htmlcov/index.html
```
