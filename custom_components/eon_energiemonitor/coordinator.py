"""Data update coordinator for the E.ON EnergieMonitor integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    EnergieMonitorClient,
    EnergieMonitorError,
    EnergieMonitorNotFoundError,
    MeterData,
    Region,
    Tenant,
)
from .const import CONF_REGION_CODE, DOMAIN, LOGGER, UPDATE_INTERVAL

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

type EnergieMonitorConfigEntry = ConfigEntry[EnergieMonitorCoordinator]


class EnergieMonitorCoordinator(DataUpdateCoordinator[MeterData]):
    """Fetch meter data of a single EnergieMonitor region."""

    config_entry: EnergieMonitorConfigEntry
    region: Region
    tenant: Tenant | None

    def __init__(self, hass: HomeAssistant, entry: EnergieMonitorConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.data[CONF_REGION_CODE]}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = EnergieMonitorClient(async_get_clientsession(hass))
        self.region_code: str = entry.data[CONF_REGION_CODE]

    async def _async_setup(self) -> None:
        """Fetch static region and tenant information once."""
        try:
            self.region = await self.client.async_get_region(self.region_code)
            tenants = await self.client.async_get_tenants()
        except EnergieMonitorNotFoundError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="region_not_found",
                translation_placeholders={"region_code": self.region_code},
            ) from err
        except EnergieMonitorError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        self.tenant = next(
            (t for t in tenants if t.tenant_id == self.region.tenant_id), None
        )

    async def _async_update_data(self) -> MeterData:
        """Fetch the latest meter data."""
        try:
            return await self.client.async_get_meter_data(self.region_code)
        except EnergieMonitorError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
