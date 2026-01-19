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

## Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_auth.py         # Authentication tests
├── test_client.py       # HTTP client tests
├── test_mqtt.py         # MQTT protocol tests
├── test_climate.py      # Climate platform tests
├── test_sensor.py       # Sensor platform tests
└── ...                  # Other platform-specific tests
```

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

### Mocking API Responses

Use `aioclient_mock` to mock HTTP responses. See [API_REFERENCE.md](API_REFERENCE.md) for the expected response structures.

```python
@pytest.mark.asyncio
async def test_with_mocked_api(aioclient_mock):
    """Test with mocked HTTP responses."""
    aioclient_mock.get(
        "https://app-prod.mysa.cloud/users",
        json={
            "User": {
                "Id": "test-user-id",
                "AllowedDevices": ["device-1"],
                "ERate": "0.10"
            }
        }
    )

    # Your test code here
```

## Continuous Integration

Tests run automatically on:
- Pull requests
- Pushes to main
- Pre-commit hooks (local)

Coverage requirement: **100%** for all source files.

## Troubleshooting

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

### Authentication Issues
If tests are failing due to authentication:
1. Check that mock fixtures are being used correctly
2. Verify that `aioclient_mock` is mocking the correct endpoints
3. Check the test's fixture dependencies

## Test Categories

Tests are organized by component and marked with pytest markers:

| Marker | Description |
|--------|-------------|
| `@pytest.mark.asyncio` | Async tests |
| `@pytest.mark.unit` | Fast, isolated unit tests |
| `@pytest.mark.integration` | Tests requiring Home Assistant fixtures |
| `@pytest.mark.slow` | Tests that take longer to run |
| `@pytest.mark.mqtt` | Tests requiring mock MQTT broker |

## Related Documentation

- [API_REFERENCE.md](API_REFERENCE.md) - HTTP API response structures
- [MYSA_PROTOCOL.md](MYSA_PROTOCOL.md) - MQTT protocol and commands
