# Mysa Integration Test Suite

This directory contains the comprehensive test suite for the Mysa Home Assistant integration.

## Test Count: 785 tests

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific category
pytest tests/test_climate.py -v

# Run with markers
pytest tests/ -m "unit" -v
pytest tests/ -m "integration" -v
```

## Test Categories

| Category | Files | Description |
|----------|-------|-------------|
| **Core** | `test_api.py`, `test_auth.py`, `test_mqtt.py`, `test_config_flow.py`, `test_config_flow_reauth.py`, `test_diagnostics.py` | API, Auth, MQTT, Setup, Reauth, Diagnostics |
| **Entities** | `test_climate.py`, `test_sensor.py`, `test_number.py`, `test_switch.py`, `test_select.py`, `test_update.py`, `test_entities.py` | Entity logic & Base classes |
| **Integration** | `test_integration.py`, `test_init_coverage.py` | Full flow & Component setup |
| **Utilities** | `test_utilities.py` | Helpers, constants, capability getters |
| **Edge Cases** | `test_edge_cases.py` | Error handling, race conditions, limits |

## Markers

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Tests requiring Home Assistant fixtures
- `@pytest.mark.asyncio` - Async tests

## Key Fixtures (conftest.py)

- `hass` - Home Assistant instance
- `aioclient_mock` - HTTP request mocking
- `caplog` - Log capture
- `mock_api` - Mocked MysaApi
- `mock_config_entry` - MockConfigEntry

## Requirements

- `pytest`
- `pytest-asyncio`
- `pytest-homeassistant-custom-component`
