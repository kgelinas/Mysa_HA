"""Regression coverage for frozen BB/INF measurements and HTTP polling."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.mysa import async_setup_entry
from custom_components.mysa.client import MysaClient
from custom_components.mysa.device import MysaDeviceLogic


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("humidity", [0, 57])
def test_legacy_measurements(nested, humidity):
    """Long-form measurements normalize without changing floor control fields."""
    state = {
        "CorrectedTemp": 23.25,
        "Humidity": humidity,
        "SensorMode": 1,
        "Infloor": 26.5,
        "SetPoint": 18,
        "Mode": 1,
    }
    if nested:
        for key in ("CorrectedTemp", "Humidity"):
            state[key] = {"v": state[key], "t": 200}
    MysaDeviceLogic.normalize_state(state)
    assert state["current_temp"] == 23.25
    assert state["current_humidity"] == humidity
    assert (
        state["SensorMode"],
        state["Infloor"],
        state["SetPoint"],
        state["Mode"],
    ) == (1, 26.5, 18, 1)


def test_existing_measurement_aliases_keep_precedence():
    """Adding legacy fallbacks does not change existing short-form behavior."""
    state = {
        "ambTemp": {"v": 2150},
        "hum": 0,
        "CorrectedTemp": 19,
        "Humidity": 57,
    }
    MysaDeviceLogic.normalize_state(state)
    assert state["current_temp"] == 21.5
    assert state["current_humidity"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mixed", [False, True])
async def test_http_keeps_live_legacy_readings(hass, mixed):
    """Stale batch data cannot mask BB/INF values, including in mixed accounts."""
    devices = {
        "bb1": {"Model": "BB-V1-0"},
        "bb2": {"Model": "BB-V2-0"},
        "floor": {"Model": "INF-V1-0"},
    }
    if mixed:
        devices.update({"st": {"Model": "ST-V1-0"}, "ac": {"Model": "AC-V1-0"}})
    live = {
        key: {"CorrectedTemp": {"v": 23.25, "t": 200}, "Humidity": {"v": 57, "t": 200}}
        for key in devices
    }
    stale_batch = {
        key: {
            "data": {
                "latestTelemetry": {
                    "timestamp": 100,
                    "reading": {"roomTemperature": 19, "humidity": 40},
                }
            }
        }
        for key in devices
    }

    def response(url, **_kwargs):
        payload = (
            {"DeviceStatesObj": deepcopy(live)}
            if url.endswith("/devices/state")
            else {"DevicesObj": devices}
        )
        result = MagicMock()
        result.raise_for_status.return_value = None
        result.json = AsyncMock(return_value=payload)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=result)
        context.__aexit__ = AsyncMock(return_value=False)
        return context

    session = MagicMock()
    session.get.side_effect = response
    client = MysaClient(hass, "test@example.com", "test-password", websession=session)
    client._user_obj = MagicMock()
    with (
        patch.object(client, "_get_auth_headers", AsyncMock(return_value={})),
        patch.object(client, "fetch_homes", AsyncMock()),
        # Include unsolicited BB/INF entries to exercise the merge safeguard too.
        patch.object(
            client, "get_st1_state", AsyncMock(return_value=stale_batch)
        ) as batch,
    ):
        result = await client.get_state()
    for key in ("bb1", "bb2", "floor"):
        assert result[key]["current_temp"] == 23.25
        assert result[key]["current_humidity"] == 57
        assert "roomTemperature" not in result[key]
    if mixed:
        batch.assert_awaited_once_with(["st", "ac"])
        for key in ("st", "ac"):
            assert result[key]["roomTemperature"] == 19
            assert result[key]["current_humidity"] == 40
    else:
        batch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_first", [False, True])
async def test_poll_survives_pushes_and_stops_on_unload(hass, timeout_first, caplog):
    """MQTT pushes cannot postpone HTTP polling; timeout and unload are handled."""
    entry = MagicMock()
    entry.entry_id = "legacy_refresh_test"
    entry.data = {"username": "test@example.com", "password": "test-password"}
    entry.options = {}
    entry.state = ConfigEntryState.SETUP_IN_PROGRESS
    api = MagicMock()
    api.states = {"bb1": {"current_temp": 23.25}}
    api.authenticate = AsyncMock()
    api.get_devices = AsyncMock()
    api.get_state = AsyncMock(return_value=api.states)
    api.start_mqtt_listener = AsyncMock()
    sleeps = asyncio.Queue()
    ticks = asyncio.Semaphore(0)
    tasks = []
    create_task = hass.async_create_background_task

    async def controlled_sleep(delay):
        await sleeps.put(delay)
        await ticks.acquire()

    def capture_task(coro, **kwargs):
        task = create_task(coro, **kwargs)
        tasks.append(task)
        return task

    # Replace only the integration's clock, leaving HA and pytest's loop intact.
    clock = SimpleNamespace(
        sleep=controlled_sleep, timeout=asyncio.timeout, create_task=asyncio.create_task
    )
    with (
        patch("custom_components.mysa.MysaApi", return_value=api),
        patch(
            "custom_components.mysa.async_get_clientsession", return_value=MagicMock()
        ),
        patch("custom_components.mysa.asyncio", clock),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(hass, "async_create_background_task", side_effect=capture_task),
    ):
        try:
            assert await async_setup_entry(hass, entry)
            assert await asyncio.wait_for(sleeps.get(), 1) == 120
            coordinator = entry.runtime_data.coordinator
            side_effect = [TimeoutError(), None] if timeout_first else [None, None]
            with patch.object(
                coordinator, "async_refresh", AsyncMock(side_effect=side_effect)
            ) as refresh:
                for poll in range(2):
                    for push in range(12):
                        with patch(
                            "custom_components.mysa.time.time",
                            return_value=1000 + poll * 120 + push,
                        ):
                            await api.coordinator_callback()
                    assert refresh.await_count == poll
                    ticks.release()
                    assert await asyncio.wait_for(sleeps.get(), 1) == 120
                    assert refresh.await_count == poll + 1
            if timeout_first:
                assert "Periodic Mysa HTTP refresh exceeded 90 seconds" in caplog.text
            # Exercise the cancellation hook registered with the config entry.
            entry.async_on_unload.assert_any_call(tasks[0].cancel)
            tasks[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await tasks[0]
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
