"""
MQTT E2E tests for Mysa integration.

Tests real-time updates using a mock MQTT broker.
"""
# pylint: disable=redefined-outer-name
import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD


from custom_components.mysa.const import DOMAIN
from custom_components.mysa.mysa_auth import BASE_URL

from .mqtt_broker import (
    MockMqttBroker,
    MockMqttClient,
    create_mysa_state_update,
    create_mysa_command,
)


# ===========================================================================
# Test Data
# ===========================================================================

MOCK_DEVICE = {
    "Id": "test-device-001",
    "Name": "Test Thermostat",
    "Model": "BB-V2",
    "Room": "Living Room",
}

MOCK_STATE = {
    "Id": "test-device-001",
    "ambTemp": 20.0,
    "stpt": 21.0,
    "sp": 21.0,
    "md": 3,  # Heat
    "hum": 45,
}


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
async def mock_mqtt_broker():
    """Create and start a mock MQTT broker."""
    broker = MockMqttBroker()
    await broker.start()
    yield broker
    await broker.stop()


@pytest.fixture
def mock_auth():
    """Mock authentication."""
    async def side_effect(self):
        self._user_obj = MagicMock()
        self._user_obj.id_claims = {"exp": 9999999999}
        self._user_obj.id_token = "mock_token"
        return True

    with patch("custom_components.mysa.client.MysaClient.authenticate", autospec=True) as mock_method:
        mock_method.side_effect = side_effect
        yield mock_method


@pytest.fixture
def mock_realtime_with_broker(mock_mqtt_broker):
    """
    Mock MysaRealtime to use the mock broker.

    This allows us to inject messages and verify commands.
    """
    with patch("custom_components.mysa.mysa_api.MysaRealtime") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.start = AsyncMock()
        mock_instance.stop = AsyncMock()
        mock_instance.send_command = AsyncMock()
        mock_instance._broker = mock_mqtt_broker  # Attach broker for test access
        mock_cls.return_value = mock_instance
        yield mock_instance


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.mqtt
@pytest.mark.asyncio
async def test_mqtt_broker_basic(mock_mqtt_broker):
    """Test basic broker functionality."""
    # Create two clients
    client1 = mock_mqtt_broker.create_client("client1")
    client2 = mock_mqtt_broker.create_client("client2")

    await client1.connect()
    await client2.connect()

    # Client 2 subscribes
    await client2.subscribe("/test/topic")

    # Client 1 publishes
    await client1.publish("/test/topic", b"hello")

    # Client 2 should receive
    msg = await client2.receive(timeout=1.0)
    assert msg is not None
    assert msg.topic == "/test/topic"
    assert msg.payload == b"hello"

    await client1.disconnect()
    await client2.disconnect()


@pytest.mark.mqtt
@pytest.mark.asyncio
async def test_mqtt_wildcard_subscription(mock_mqtt_broker):
    """Test wildcard topic subscriptions."""
    client = mock_mqtt_broker.create_client("test-client")
    await client.connect()

    # Subscribe with wildcard
    await client.subscribe("/v1/dev/+/out")

    # Inject message matching wildcard
    await mock_mqtt_broker.inject_message(
        topic="/v1/dev/device123/out",
        payload={"msg": 44, "body": {"state": {"sp": 22.0}}}
    )

    msg = await client.receive(timeout=1.0)
    assert msg is not None
    assert "/v1/dev/device123/out" in msg.topic

    await client.disconnect()


@pytest.mark.mqtt
@pytest.mark.asyncio
async def test_mqtt_state_update_injection(
    hass: HomeAssistant,
    mock_auth,
    mock_realtime_with_broker,
    mock_mqtt_broker,
    aioclient_mock
):
    """
    Test injecting MQTT state updates and verifying entity state changes.
    """
    # Setup HTTP mocks
    aioclient_mock.get(f"{BASE_URL}/devices", json={"Devices": [MOCK_DEVICE]})
    aioclient_mock.get(f"{BASE_URL}/devices/state", json={"DeviceStates": [MOCK_STATE]})
    aioclient_mock.get(f"{BASE_URL}/users", json={"User": {"Id": "test-user"}})
    aioclient_mock.get(f"{BASE_URL}/homes", json={"Homes": []})

    # Setup integration
    config_entry = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        config_entry["flow_id"],
        {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "password"},
    )

    entry = result["result"]
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Verify initial state
    state = hass.states.get("climate.test_thermostat")
    assert state is not None
    initial_temp = state.attributes.get("temperature")

    # Inject MQTT state update
    new_setpoint = 24.0
    state_update = create_mysa_state_update(
        MOCK_DEVICE["Id"],
        sp=new_setpoint,
        stpt=new_setpoint,
        ambTemp=21.5,
        hum=50
    )

    # Simulate the MQTT update through the API
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Disable coordinator callback to prevent HTTP refresh from overwriting MQTT update
    # In production, coordinator_callback triggers async_request_refresh which fetches
    # fresh HTTP data that would overwrite the MQTT state update
    original_callback = api.coordinator_callback
    api.coordinator_callback = None

    # Update the API state cache with MQTT data
    await api._on_mqtt_update(MOCK_DEVICE["Id"], state_update["body"]["state"])

    # Restore callback
    api.coordinator_callback = original_callback

    # Manually set coordinator data from api.states
    # (since we disabled the callback, we need to do this explicitly)
    coordinator.async_set_updated_data(api.states)
    await hass.async_block_till_done()

    # Force time forward to clear sticky state
    import time
    with patch("time.time", return_value=time.time() + 40):
        # Re-set data to trigger entity update with cleared sticky state
        coordinator.async_set_updated_data(api.states)
        await hass.async_block_till_done()

        # Verify state updated
        state = hass.states.get("climate.test_thermostat")
        assert state is not None
        assert state.attributes.get("temperature") == new_setpoint


@pytest.mark.mqtt
@pytest.mark.asyncio
async def test_mqtt_command_sent(
    hass: HomeAssistant,
    mock_auth,
    mock_realtime_with_broker,
    aioclient_mock
):
    """
    Test that HA service calls result in correct MQTT commands.
    """
    aioclient_mock.get(f"{BASE_URL}/devices", json={"Devices": [MOCK_DEVICE]})
    aioclient_mock.get(f"{BASE_URL}/devices/state", json={"DeviceStates": [MOCK_STATE]})
    aioclient_mock.get(f"{BASE_URL}/users", json={"User": {"Id": "test-user"}})
    aioclient_mock.get(f"{BASE_URL}/homes", json={"Homes": []})

    # Setup integration
    config_entry = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        config_entry["flow_id"],
        {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "password"},
    )
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    # Call set_temperature service
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.test_thermostat", "temperature": 23.0},
        blocking=True,
    )

    # Verify MQTT command was sent
    assert mock_realtime_with_broker.send_command.called

    # Check command payload
    call_args = mock_realtime_with_broker.send_command.call_args_list
    found_temp_cmd = False
    for call in call_args:
        args = call[0]
        if len(args) >= 2:
            payload = args[1]
            if "cmd" in payload:
                cmd = payload["cmd"][0]
                if cmd.get("sp") == 23.0 or cmd.get("stpt") == 23.0:
                    found_temp_cmd = True
                    break

    assert found_temp_cmd, f"Temperature command not found in: {call_args}"


@pytest.mark.mqtt
@pytest.mark.asyncio
async def test_mqtt_message_helpers():
    """Test Mysa message helper functions."""
    # Test state update creation
    state_update = create_mysa_state_update(
        "device123",
        sp=22.0,
        stpt=22.0,
        ambTemp=20.0,
        hum=45
    )

    assert state_update["msg"] == 44
    assert state_update["body"]["state"]["sp"] == 22.0
    assert state_update["body"]["state"]["hum"] == 45

    # Test command creation
    command = create_mysa_command(
        "device123",
        "user456",
        sp=23.0,
        stpt=23.0
    )

    assert command["msg"] == 44
    assert command["dest"]["ref"] == "device123"
    assert command["src"]["ref"] == "user456"
    assert command["body"]["cmd"][0]["sp"] == 23.0
