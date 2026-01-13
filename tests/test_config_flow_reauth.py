"""Tests for Reauthentication Flow."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from custom_components.mysa.const import DOMAIN


class TestConfigFlowReauth:
    """Test Reauthentication Flow."""

    @pytest.mark.asyncio
    async def test_reauth_successful(self, hass):
        """Test successful reauthentication."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        # Mock existing entry
        mock_entry = MagicMock()
        mock_entry.data = {CONF_USERNAME: "test@example.com"}
        mock_entry.entry_id = "test_entry_id"

        flow.context = {"entry_id": "test_entry_id"}

        with (
            patch.object(
                hass.config_entries, "async_get_entry", return_value=mock_entry
            ),
            patch.object(hass.config_entries, "async_update_entry") as mock_update,
            patch.object(
                hass.config_entries, "async_reload", new_callable=AsyncMock
            ) as mock_reload,
            patch.object(
                flow, "_validate_credentials", new_callable=AsyncMock
            ) as mock_validate,
        ):
            # Start reauth
            await flow.async_step_reauth({})

            # Submit valid credentials for same account
            result = await flow.async_step_reauth_confirm(
                {
                    "username": "test@example.com",
                    "password": "new_password_123",
                }
            )

            assert result["type"] == "abort"
            assert result["reason"] == "reauth_successful"
            mock_validate.assert_called_once()
            mock_update.assert_called_once_with(
                mock_entry,
                data={
                    CONF_USERNAME: "test@example.com",
                    CONF_PASSWORD: "new_password_123",
                },
            )
            mock_reload.assert_called_once_with("test_entry_id")

    @pytest.mark.asyncio
    async def test_reauth_account_mismatch(self, hass):
        """Test reauth fails if trying to use different account."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        mock_entry = MagicMock()
        mock_entry.data = {CONF_USERNAME: "original@example.com"}

        flow.entry = mock_entry  # Already set by async_step_reauth

        with patch.object(flow, "_validate_credentials", new_callable=AsyncMock):
            result = await flow.async_step_reauth_confirm(
                {
                    "username": "different@example.com",
                    "password": "password",
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "reauth_account_mismatch"

    @pytest.mark.asyncio
    async def test_reauth_entry_not_found(self, hass):
        """Test reauth fails when entry is missing (edge case)."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        
        # entry is None (default state if async_step_reauth wasn't called or failed)
        flow.entry = None

        with patch.object(flow, "_validate_credentials", new_callable=AsyncMock):
            result = await flow.async_step_reauth_confirm(
                {
                    "username": "test@example.com",
                    "password": "password",
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "unknown"

    @pytest.mark.asyncio
    async def test_reauth_validation_exception(self, hass):
        """Test reauth handles validation exceptions."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow.entry = MagicMock()

        # Simulate exception during validation
        with patch.object(
            flow, 
            "_validate_credentials", 
            side_effect=Exception("API Error")
        ):
            result = await flow.async_step_reauth_confirm(
                {
                    "username": "test@example.com",
                    "password": "password",
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_auth"
