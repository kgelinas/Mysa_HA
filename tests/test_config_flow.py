"""
Config Flow Coverage Tests.

Tests for config_flow.py: ConfigFlow and MysaOptionsFlowHandler
"""

import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
import pytest
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant import config_entries

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

# Module-level imports after path setup
from custom_components.mysa.const import DOMAIN
from tests.conftest import MockConfigEntry

# ...

# --- Gap Fill Tests (Merged) ---

class TestConfigFlowReauth:
    """Test config_flow.py reauth."""

    @pytest.mark.asyncio
    async def test_reauth_flow(self, hass):
        """Test reauth flow success."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "old_password"},
            unique_id="test@example.com"
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
                "unique_id": entry.unique_id,
            },
            data=entry.data,
        )
        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"

        with patch("custom_components.mysa.config_flow.MysaApi") as mock_api_cls:
            mock_api = AsyncMock()
            mock_api_cls.return_value = mock_api

            # Match user
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "new_password"},
            )
            assert result["type"] == "abort"
            assert result["reason"] == "reauth_successful"
            assert entry.data[CONF_PASSWORD] == "new_password"

    @pytest.mark.asyncio
    async def test_reauth_account_mismatch(self, hass):
        """Test reauth account mismatch."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "old"},
            unique_id="test@example.com"
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )

        with patch("custom_components.mysa.config_flow.MysaApi") as mock_api_cls:
            mock_api = AsyncMock()
            mock_api_cls.return_value = mock_api

            # Mismatch user
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_USERNAME: "other@example.com", CONF_PASSWORD: "new"},
            )
            assert result["type"] == "form"
            assert result["errors"]["base"] == "reauth_account_mismatch"


    @pytest.mark.asyncio
    async def test_reauth_entry_missing(self, hass):
        """Test reauth when entry is missing (line 99)."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow.entry = None

        # Mock validate to succeed
        with patch.object(flow, "_validate_credentials"):
            result = await flow.async_step_reauth_confirm({CONF_USERNAME: "u", CONF_PASSWORD: "p"})
            assert result["type"] == "form"
            assert result["errors"]["base"] == "unknown"

    @pytest.mark.asyncio
    async def test_reauth_exception(self, hass):
        """Test reauth exception handling (lines 113-114)."""
        from custom_components.mysa.config_flow import ConfigFlow

        entry = MockConfigEntry(domain=DOMAIN, data={CONF_USERNAME: "u", CONF_PASSWORD: "p"})
        entry.add_to_hass(hass)

        flow = ConfigFlow()
        flow.hass = hass
        flow.entry = entry

        # Mock validate to raise
        with patch.object(flow, "_validate_credentials", side_effect=Exception("Auth Fail")):
            result = await flow.async_step_reauth_confirm({CONF_USERNAME: "u", CONF_PASSWORD: "p"})
            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_auth"

class TestConfigFlowOptionsCoverage:
    """Test options flow coverage."""

    @pytest.mark.asyncio
    async def test_options_flow_init_static(self, hass):
        """Test getting options flow."""
        from custom_components.mysa.config_flow import ConfigFlow, MysaOptionsFlowHandler

        entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
        entry.add_to_hass(hass)

        # Test ConfigFlow.async_get_options_flow
        flow = ConfigFlow.async_get_options_flow(entry)
        assert isinstance(flow, MysaOptionsFlowHandler)

    @pytest.mark.asyncio
    async def test_options_flow_with_zones(self, hass):
        """Test options flow with zones (lines 189-193)."""
        from custom_components.mysa.config_flow import ConfigFlow

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={},
            options={"zone_name_z1": "Renamed Zone"}
        )
        entry.add_to_hass(hass)

        # Setup flow
        flow = ConfigFlow.async_get_options_flow(entry)
        flow.hass = hass

        # Mock API to return zones
        mock_api = MagicMock()
        mock_api.zones = {"z1": "Zone 1"}
        mock_api.devices = {} # Empty devices to avoid attribute error

        # Inject API into runtime_data (new way)
        entry.runtime_data = MagicMock()
        entry.runtime_data.api = mock_api

        # Run init step
        result = await flow.async_step_init()

        assert result["type"] == "form"
        # Verify zone field is NOT present
        schema = result["data_schema"]
        assert not any("zone_name_z1" in str(k) for k in schema.schema.keys())


# ===========================================================================
# ConfigFlow Tests
# ===========================================================================


class TestConfigFlow:
    """Test ConfigFlow."""

    @pytest.mark.asyncio
    async def test_show_form(self, hass):
        """Test showing the initial form."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow._async_current_entries = MagicMock(return_value=[])

        result = await flow.async_step_user()

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_single_instance_abort(self, hass):
        """Test aborting when instance already exists."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        # Simulate existing entry
        mock_entry = MagicMock()
        flow._async_current_entries = MagicMock(return_value=[mock_entry])

        result = await flow.async_step_user()

        assert result["type"] == "abort"
        assert result["reason"] == "single_instance_allowed"

    @pytest.mark.asyncio
    async def test_successful_auth(self, hass):
        """Test successful authentication."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow._async_current_entries = MagicMock(return_value=[])

        with patch.object(
            flow, "_validate_credentials", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = MagicMock()

            result = await flow.async_step_user(
                {
                    "username": "test@example.com",
                    "password": "password123",
                }
            )

            assert result["type"] == "create_entry"
            assert result["title"] == "test@example.com"
            assert result["data"]["username"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_auth_failure_old(self, hass):
        """Test authentication failure shows error (legacy test)."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow._async_current_entries = MagicMock(return_value=[])

        with patch.object(
            flow, "_validate_credentials", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.side_effect = Exception("Auth failed")

            result = await flow.async_step_user(
                {
                    "username": "bad@example.com",
                    "password": "wrongpass",
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_validate_credentials(self, hass):
        """Test _validate_credentials calls API."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        with patch("custom_components.mysa.config_flow.MysaApi") as MockApi, \
             patch("custom_components.mysa.config_flow.async_get_clientsession") as mock_get_session:
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock()
            MockApi.return_value = mock_api

            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            result = await flow._validate_credentials("test@example.com", "pass123")

            MockApi.assert_called_once_with(
                "test@example.com", "pass123", hass, websession=mock_session
            )
            mock_api.authenticate.assert_called_once_with(use_cache=False)


# ===========================================================================
# Options Flow Tests
# ===========================================================================


class TestOptionsFlow:
    """Test MysaOptionsFlowHandler."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.options = {
            "upgraded_lite_devices": [],
            "estimated_max_current": 0,
        }
        return entry

    @pytest.mark.asyncio
    async def test_options_flow_init(self, hass, mock_config_entry):
        """Test options flow initialization."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)

        assert handler._config_entry == mock_config_entry

    @pytest.mark.asyncio
    async def test_options_flow_show_form(self, hass, mock_config_entry):
        """Test options flow shows form with devices."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # Setup mock API with devices
        mock_api = MagicMock()
        mock_api.devices = {
            "device1": {"Name": "Living Room"},
            "device2": {"Name": "Bedroom"},
        }

        hass.data[DOMAIN] = {"test_entry_123": {"api": mock_api}}
        # Inject into runtime_data
        mock_config_entry.runtime_data = MagicMock()
        mock_config_entry.runtime_data.api = mock_api

        result = await handler.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_show_form_heating_devices(self, hass, mock_config_entry):
        """Test options flow shows form with heating devices (wattage input)."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # Setup mock API with heating devices
        mock_api = MagicMock()
        devices = {
            "device1": {"Name": "Living Room", "Model": "BB-V2"},
        }
        mock_api.devices = devices
        mock_api.get_devices = AsyncMock(return_value=devices)

        # Mock is_ac_device to return False
        mock_api.is_ac_device = MagicMock(return_value=False)

        # Inject API into runtime_data
        mock_config_entry.runtime_data = MagicMock()
        mock_config_entry.runtime_data.api = mock_api

        result = await handler.async_step_init()

        assert result["type"] == "form"
        # Verify schema contains wattage_device1
        schema = result["data_schema"]

        # Voluptuous schema keys are wrapped, check string representation
        keys = list(schema.schema.keys())
        found = any("wattage_device1" in str(k) for k in keys)
        assert found is True

    @pytest.mark.asyncio
    async def test_options_flow_submit(self, hass, mock_config_entry):
        """Test options flow submission creates entry."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        result = await handler.async_step_init(
            {
                "upgraded_lite_devices": ["device1"],
                "estimated_max_current": 15.0,
            }
        )

        assert result["type"] == "create_entry"
        assert result["data"]["upgraded_lite_devices"] == ["device1"]
        assert result["data"]["estimated_max_current"] == 15.0

    @pytest.mark.asyncio
    async def test_options_flow_no_api_attribute_error(self, hass, mock_config_entry):
        """Test options flow handles AttributeError (missing runtime_data or API)."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # Simulate missing runtime_data (None has no attributes)
        mock_config_entry.runtime_data = None

        result = await handler.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_key_error(self, hass, mock_config_entry):
        """Test options flow handles KeyError."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # Simulate runtime_data present but accessing it fails with KeyError (mock dictionary-like behavior if it were a dict)
        # But runtime_data is an object.
        # Let's mock a property that raises KeyError
        mock_config_entry.runtime_data = MagicMock()
        type(mock_config_entry.runtime_data).api = PropertyMock(side_effect=KeyError("Boom"))

        result = await handler.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "init"

class TestConfigFlowReconfigure:
    """Test config_flow.py reconfigure."""

    @pytest.mark.asyncio
    async def test_reconfigure_flow_success(self, hass):
        """Test reconfigure flow success."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "old_password"},
            unique_id="test@example.com"
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)

        # Start reconfigure flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure_confirm"

        with patch("custom_components.mysa.config_flow.MysaApi") as mock_api_cls:
            mock_api = AsyncMock()
            mock_api_cls.return_value = mock_api

            # Submit new credentials
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_USERNAME: "new@example.com", CONF_PASSWORD: "new_password"},
            )
            assert result["type"] == "abort"
            assert result["reason"] == "reconfigure_successful"
            assert entry.data[CONF_USERNAME] == "new@example.com"
            assert entry.data[CONF_PASSWORD] == "new_password"

    @pytest.mark.asyncio
    async def test_reconfigure_flow_auth_failure(self, hass):
        """Test reconfigure flow with authentication failure."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "old_password"},
            unique_id="test@example.com"
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )

        # We must use proper patching for the flow instance created inside hass
        # Since we can't easily access the flow instance from here, we rely on patching MysaApi
        # But we also need to trigger the exception.
        # validating uses _validate_credentials which calls MysaApi.authenticate

        with patch("custom_components.mysa.config_flow.MysaApi") as mock_api_cls:
            mock_api = AsyncMock()
            mock_api.authenticate.side_effect = Exception("Auth fail")
            mock_api_cls.return_value = mock_api

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "wrong_password"},
            )
            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_reconfigure_flow_unexpected_exception(self, hass):
        """Test reconfigure flow with unexpected exception."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USERNAME: "u", CONF_PASSWORD: "p"},
            unique_id="u"
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
            data=entry.data,
        )

        # Patch _validate_credentials to raise generic Exception
        # We need to patch it on the class because the flow object is deep inside HA
        with patch("custom_components.mysa.config_flow.ConfigFlow._validate_credentials", side_effect=Exception("Boom")):
             result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_USERNAME: "u", CONF_PASSWORD: "p"},
            )
             assert result["type"] == "form"
             assert result["errors"]["base"] == "invalid_auth"
