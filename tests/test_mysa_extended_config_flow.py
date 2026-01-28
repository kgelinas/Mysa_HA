"""Tests for the Mysa Extended config flow."""

from unittest.mock import MagicMock, patch

from homeassistant.data_entry_flow import FlowResultType

from custom_components.mysa_extended import config_flow


async def test_options_flow(hass):
    """Test options flow."""
    # Test getting options flow
    entry = MagicMock()
    entry.options = {}

    # Directly test the static method to ensure coverage of the @callback
    flow = config_flow.ConfigFlow.async_get_options_flow(entry)
    assert isinstance(flow, config_flow.MysaExtendedOptionsFlowHandler)

    # Test init step of options flow
    result = await flow.async_step_init()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    # Test init step with user input
    result = await flow.async_step_init(user_input={"custom_erate": 0.15})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {"custom_erate": 0.15}


async def test_is_matching():
    """Test is_matching method."""
    flow = config_flow.ConfigFlow()
    assert flow.is_matching({}) is False


async def test_config_flow(hass):
    """Test user config flow."""
    flow = config_flow.ConfigFlow()
    flow.hass = hass

    # Test user step - show form
    result = await flow.async_step_user()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Test user step - create entry
    result = await flow.async_step_user(user_input={})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Mysa Extended"
    assert result["data"] == {}

    # Test abort if already configured
    with patch(
        "homeassistant.config_entries.ConfigFlow._async_current_entries",
        return_value=[MagicMock()],
    ):
        result = await flow.async_step_user()
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"
