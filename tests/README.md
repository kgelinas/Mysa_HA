# Mysa Integration Test Suite

This directory contains the comprehensive test suite for the Mysa Home Assistant integration.

## Test Count: 456+ tests

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
| **Core** | `test_api.py`, `test_integration.py`, `test_config_flow.py` | API, setup, config flow |
| **Entities** | `test_climate.py`, `test_sensor.py`, `test_number.py`, `test_switch.py`, `test_select.py` | Entity behavior |
| **MQTT** | `test_mqtt.py`, `test_mqtt_protocol.py`, `test_websocket_mqtt.py` | MQTT communication |
| **HA Patterns** | `test_ha_*.py`, `test_device_entity.py`, `test_flows_events.py` | Home Assistant fixtures |
| **Utilities** | `test_constants.py`, `test_capabilities.py`, `test_zone_lookup.py` | Constants and helpers |
| **Error Handling** | `test_error_recovery.py`, `test_edge_cases.py` | Error scenarios |

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
