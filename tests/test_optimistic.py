"""Tests for sticky optimistic UI updates."""
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.components.climate import HVACMode, HVACAction
from homeassistant.exceptions import HomeAssistantError
from custom_components.mysa.const import DOMAIN
from custom_components.mysa.switch import MysaLockSwitch
from custom_components.mysa.climate import MysaClimate
from custom_components.mysa.select import MysaHorizontalSwingSelect
from custom_components.mysa.number import MysaMinBrightnessNumber

@pytest.fixture
def mock_coordinator():
    """Mock decorator."""
    coordinator = MagicMock()
    coordinator.data = {}
    return coordinator

@pytest.fixture
def mock_api():
    """Mock API."""
    api = MagicMock()
    api.set_lock = AsyncMock()
    api.set_target_temperature = AsyncMock()
    api.set_hvac_mode = AsyncMock()
    api.set_ac_horizontal_swing = AsyncMock()
    api.set_min_brightness = AsyncMock()
    return api

@pytest.fixture
def mock_entry():
    """Mock ConfigEntry."""
    entry = MagicMock(entry_id="test_entry")
    entry.options = {}
    return entry

class TestOptimisticSwitch:
    """Test switch optimistic updates."""

    @pytest.mark.asyncio
    async def test_sticky_behavior(self, mock_coordinator, mock_api, mock_entry):
        """Test sticky state persistence, expiration, and convergence."""
        entity = MysaLockSwitch(
            mock_coordinator, "device1", {}, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        # 1. Initial State (Cloud = False)
        mock_coordinator.data = {"device1": {"Lock": {"v": False}}}
        assert entity.is_on is False

        # 2. Turn On (Optimistic)
        await entity.async_turn_on()
        assert entity.is_on is True
        assert entity._pending_state is True

        # 3. Persistence (Cloud still False)
        # mocked coordinator still says False
        assert entity.is_on is True

        # 4. Convergence (Cloud becomes True)
        mock_coordinator.data = {"device1": {"Lock": {"v": True}}}
        assert entity.is_on is True
        # Logic should clear pending state if it matches
        # Note: In current implementation, _pending_state clears on access if matches
        # Let's verify internal state
        assert entity._pending_state is None

    @pytest.mark.asyncio
    async def test_expiration(self, mock_coordinator, mock_api, mock_entry):
        """Test sticky state expiration."""
        entity = MysaLockSwitch(
            mock_coordinator, "device1", {}, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        # Cloud = False
        mock_coordinator.data = {"device1": {"Lock": {"v": False}}}

        # Turn On
        await entity.async_turn_on()
        assert entity.is_on is True

        # Fast forward time > 30s
        with patch("time.time", return_value=time.time() + 31):
            # Should revert to Cloud (False)
            assert entity.is_on is False


class TestOptimisticClimate:
    """Test climate optimistic updates."""

    @pytest.mark.asyncio
    async def test_sticky_temperature(self, mock_coordinator, mock_api, mock_entry):
        """Test sticky temperature."""
        entity = MysaClimate(
            mock_coordinator, "device1", {}, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        # Cloud = 20
        mock_coordinator.data = {"device1": {"stpt": 20.0}}
        assert entity.target_temperature == 20.0

        # Set to 22.5
        await entity.async_set_temperature(temperature=22.5)
        assert entity.target_temperature == 22.5
        mock_api.set_target_temperature.assert_called_with("device1", 22.5)

        # Cloud update (22.5) -> Convergence
        mock_coordinator.data = {"device1": {"stpt": 22.5}}
        assert entity.target_temperature == 22.5
        assert "target_temperature" not in entity._pending_updates

    @pytest.mark.asyncio
    async def test_sticky_hvac_mode(self, mock_coordinator, mock_api, mock_entry):
        """Test sticky HVAC mode."""
        entity = MysaClimate(
            mock_coordinator, "device1", {}, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        # Cloud = OFF (1)
        mock_coordinator.data = {"device1": {"md": 1}}
        assert entity.hvac_mode == HVACMode.OFF

        # Set to HEAT
        await entity.async_set_hvac_mode(HVACMode.HEAT)
        assert entity.hvac_mode == HVACMode.HEAT

        # Expiration
        with patch("time.time", return_value=time.time() + 31):
            assert entity.hvac_mode == HVACMode.OFF  # Reverts to Cloud (OFF)

class TestCoverageEdgeCases:
    """Test edge cases for 100% coverage."""

    @pytest.mark.asyncio
    async def test_switch_none_data(self, mock_coordinator, mock_api, mock_entry):
        """Test switch with None coordinator data."""
        entity = MysaLockSwitch(mock_coordinator, "device1", {}, mock_api, mock_entry)

        mock_coordinator.data = None
        assert entity.is_on is False

        entity._pending_state = True
        assert entity.is_on is True

    @pytest.mark.asyncio
    async def test_select_expiration_convergence(self, mock_coordinator, mock_api, mock_entry):
        """Test select expiration and convergence branches."""
        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "device1", {}, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        # 1. Expiration
        mock_coordinator.data = {"device1": {"SwingStateHorizontal": 6}} # Center (6)
        await entity.async_select_option("left")
        assert entity.current_option == "left"

        with patch("time.time", return_value=time.time() + 31):
            assert entity.current_option == "center" # Reverts to cloud

        # 2. Convergence
        entity._pending_option = "left"
        entity._pending_timestamp = time.time()

        # Cloud updates to 'left' (4)
        mock_coordinator.data = {"device1": {"SwingStateHorizontal": 4}}
        assert entity.current_option == "left"
        assert entity._pending_option is None # Should clear on convergence

    @pytest.mark.asyncio
    async def test_number_convergence(self, mock_coordinator, mock_api, mock_entry):
        """Test number convergence."""
        entity = MysaMinBrightnessNumber(
            mock_coordinator, "device1", {}, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        entity._pending_value = 50.0
        entity._pending_time = time.time()

        # Cloud updates to 50
        mock_coordinator.data = {"device1": {"MinBrightness": 50}}
        assert entity.native_value == 50.0
        assert entity._pending_value is None

    @pytest.mark.asyncio
    async def test_climate_edge_cases(self, mock_coordinator, mock_api, mock_entry):
        """Test climate None data and exceptions."""
        entity = MysaClimate(
            mock_coordinator, "device1", {}, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        # 1. None Data
        mock_coordinator.data = None
        assert entity.target_temperature is None
        assert entity.current_temperature is None
        assert entity.current_humidity is None
        assert entity.hvac_mode == HVACMode.HEAT # Default fallback
        # Wait, if data is None, hvac_mode returns HEAT (line 214).
        # And hvac_action calls hvac_mode. So it gets HEAT.
        # Then it checks data again (line 239). Returns IDLE.
        assert entity.hvac_action == HVACAction.IDLE

        # 2. Extract Value Edge Cases (Nested 'v' is None)
        mock_coordinator.data = {"device1": {"test_key": {"v": None, "Id": 999}}}
        val = entity._extract_value(mock_coordinator.data["device1"], ["test_key"])
        assert val == 999

        # 3. Exception Handling
        mock_api.set_target_temperature.side_effect = Exception("API Error")
        # Should raise HomeAssistantError
        with pytest.raises(HomeAssistantError) as exc:
            await entity.async_set_temperature(temperature=20.0)
        assert exc.value.translation_key == "set_temperature_failed"

        mock_api.set_hvac_mode.side_effect = Exception("API Error")
        # Should raise HomeAssistantError
        with pytest.raises(HomeAssistantError) as exc:
                await entity.async_set_hvac_mode(HVACMode.OFF)
        assert exc.value.translation_key == "set_hvac_mode_failed"

    @pytest.mark.asyncio
    async def test_climate_convergence_exact(self, mock_coordinator, mock_api, mock_entry):
        """Test climate convergence with exact match logic."""
        entity = MysaClimate(
            mock_coordinator, "device1", {}, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        # Test int/float match logic in _get_sticky_value
        entity._set_sticky_value("target_temperature", 20.0)

        mock_coordinator.data = {"device1": {"stpt": 20}}
        # This triggers the isinstance(val, (int, float)) check
        assert entity.target_temperature == 20.0
        assert "target_temperature" not in entity._pending_updates

        # Test non-numeric match
        entity._set_sticky_value("test_attr", "foo")
        # Manually inject into pending for testing generic get
        entity._pending_updates["test_attr"] = {'value': "foo", 'ts': time.time()}

        # We can't easily test generic attr via public property without adding one
        # But we can test hvac_mode enum match
        entity._set_sticky_value("hvac_mode", HVACMode.HEAT)
        mock_coordinator.data = {"device1": {"md": 3}} # Heat
        assert entity.hvac_mode == HVACMode.HEAT
        assert "hvac_mode" not in entity._pending_updates
