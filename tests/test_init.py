"""Tests for the E.ON EnergieMonitor setup, sensors and diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.eon_energiemonitor.const import API_BASE_URL, DOMAIN

from .conftest import REGION_CODE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )
    from pytest_homeassistant_custom_component.typing import ClientSessionGenerator


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_api")
async def test_setup_and_unload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test setting up and unloading the integration."""
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.usefixtures("mock_api")
async def test_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test the sensor values and device."""
    await _setup(hass, mock_config_entry)

    state = hass.states.get("sensor.gersthofen_consumption")
    assert state is not None
    assert float(state.state) == pytest.approx(3640.27637866992)
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert state.attributes["state_class"] == "total"
    assert state.attributes["last_reset"] == "2026-10-16T21:30:00+00:00"

    assert float(hass.states.get("sensor.gersthofen_generation").state) == (
        pytest.approx(1942.6991004871402)
    )
    assert float(hass.states.get("sensor.gersthofen_grid_supply").state) == (
        pytest.approx(1697.57727818278)
    )
    assert float(hass.states.get("sensor.gersthofen_self_sufficiency").state) == (
        pytest.approx(53.366802363422785)
    )
    assert float(hass.states.get("sensor.gersthofen_hydro_generation").state) == (
        pytest.approx(1932.0013851453332)
    )
    # Municipal "pubsol" (1.5 kWh) is merged into solar like on the website.
    assert hass.states.get("sensor.gersthofen_solar_generation").state == "1.5"
    assert float(
        hass.states.get("sensor.gersthofen_household_consumption").state
    ) == pytest.approx(643.3919634447485)
    assert (
        hass.states.get("sensor.gersthofen_measurement_interval_start").state
        == "2026-10-16T21:30:00+00:00"
    )

    # Daily CO2 savings reset at midnight German time.
    state = hass.states.get("sensor.gersthofen_co2_savings_today")
    assert float(state.state) == pytest.approx(76958.33568980746)
    assert state.attributes["last_reset"] == "2026-10-15T22:00:00+00:00"

    # Sources not reported by the region and municipal clusters are not created.
    assert hass.states.get("sensor.gersthofen_wind_generation") is None
    assert not [
        entry.unique_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
        if "pubsol" in entry.unique_id
    ]

    # Detail sensors are disabled by default.
    entity = entity_registry.async_get("sensor.gersthofen_solar_installations")
    assert entity is not None
    assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entity.unique_id == f"{REGION_CODE}_generation_solar_installations"

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, REGION_CODE), mock_config_entry.entry_id
    )
    assert device is not None
    assert device.name == "Gersthofen"
    assert device.manufacturer == "Lechwerke AG"
    assert device.configuration_url == "https://lew.energiemonitor.de/gersthofen"


async def test_setup_retry_on_connection_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test setup is retried when the API is unreachable."""
    aioclient_mock.get(
        f"{API_BASE_URL}/region-data?regionCode={REGION_CODE}", exc=TimeoutError
    )
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_error_region_not_found(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test setup fails permanently when the region does not exist anymore."""
    aioclient_mock.get(
        f"{API_BASE_URL}/region-data?regionCode={REGION_CODE}",
        status=404,
        text="Region not found!",
    )
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,  # noqa: ARG001
) -> None:
    """Test diagnostics."""
    await _setup(hass, mock_config_entry)
    result = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )
    assert result["entry_data"] == {"region_code": REGION_CODE, "tenant_id": "LEW"}
    assert result["region"]["name"] == "Gersthofen"
    assert result["tenant"]["name"] == "Lechwerke AG"
    assert result["data"]["consumption_total"] == pytest.approx(3640.27637866992)
