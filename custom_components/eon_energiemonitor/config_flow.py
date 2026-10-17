"""Config flow for the E.ON EnergieMonitor integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import (
    EnergieMonitorClient,
    EnergieMonitorError,
    EnergieMonitorNotFoundError,
    Region,
    Tenant,
)
from .const import (
    ALL_TENANTS,
    CONF_REGION_CODE,
    CONF_TENANT_ID,
    DOMAIN,
    LOGGER,
)


def _matches(region: Region, search: str) -> bool:
    """Return whether a region matches the search term (name or AGS)."""
    search = search.casefold()
    return (
        search in region.name.casefold()
        or region.region_code.casefold().startswith(search)
        or search in (region.url_key or "").casefold()
    )


class EnergieMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for E.ON EnergieMonitor."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._tenants: dict[str, Tenant] = {}
        self._regions: list[Region] = []
        self._candidates: list[Region] = []
        self._show_tenant = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the network operator."""
        if not self._regions:
            client = EnergieMonitorClient(async_get_clientsession(self.hass))
            try:
                tenants = await client.async_get_tenants()
                self._regions = await client.async_get_all_regions(tenants)
            except EnergieMonitorError as err:
                LOGGER.debug("Unable to load tenants and regions: %s", err)
                return self.async_abort(reason="cannot_connect")
            tenant_ids = {region.tenant_id for region in self._regions}
            self._tenants = {
                tenant.tenant_id: tenant
                for tenant in tenants
                if tenant.tenant_id in tenant_ids
            }
            if not self._regions:
                return self.async_abort(reason="no_regions")

        if user_input is not None:
            tenant_id = user_input.get(CONF_TENANT_ID, ALL_TENANTS)
            self._candidates = sorted(
                (
                    region
                    for region in self._regions
                    if tenant_id in (ALL_TENANTS, region.tenant_id)
                ),
                key=lambda r: (r.name.casefold(), r.region_code),
            )
            self._show_tenant = tenant_id == ALL_TENANTS
            return await self.async_step_region()

        tenant_options = [SelectOptionDict(value=ALL_TENANTS, label=ALL_TENANTS)]
        tenant_options.extend(
            SelectOptionDict(value=tenant.tenant_id, label=tenant.name)
            for tenant in sorted(self._tenants.values(), key=lambda t: t.name)
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_TENANT_ID, default=ALL_TENANTS): SelectSelector(
                    SelectSelectorConfig(
                        options=tenant_options,
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key=CONF_TENANT_ID,
                        sort=False,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_region(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the region of the chosen network operator."""
        errors: dict[str, str] = {}
        if user_input is not None and (
            region := self._resolve_region(user_input[CONF_REGION_CODE])
        ):
            await self.async_set_unique_id(region.region_code)
            self._abort_if_unique_id_configured()
            client = EnergieMonitorClient(async_get_clientsession(self.hass))
            try:
                await client.async_get_meter_data(region.region_code)
            except EnergieMonitorNotFoundError:
                errors["base"] = "no_data"
            except EnergieMonitorError as err:
                LOGGER.debug("Unable to load meter data: %s", err)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=region.name,
                    data={
                        CONF_REGION_CODE: region.region_code,
                        CONF_TENANT_ID: region.tenant_id,
                    },
                )
        elif user_input is not None:
            errors[CONF_REGION_CODE] = "no_results"

        options = [
            SelectOptionDict(value=region.region_code, label=self._label(region))
            for region in self._candidates
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_REGION_CODE): SelectSelector(
                    # custom_value renders a searchable picker in the frontend.
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                )
            }
        )
        if user_input is None and len(self._candidates) == 1:
            user_input = {CONF_REGION_CODE: self._candidates[0].region_code}
        return self.async_show_form(
            step_id="region",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
            description_placeholders={"count": str(len(self._candidates))},
        )

    def _resolve_region(self, value: str) -> Region | None:
        """Return the selected region, also accepting a unique free-text match."""
        value = value.strip()
        for region in self._candidates:
            if region.region_code == value:
                return region
        matches = [r for r in self._candidates if value and _matches(r, value)]
        return matches[0] if len(matches) == 1 else None

    def _label(self, region: Region) -> str:
        label = f"{region.name} ({region.region_code})"
        if self._show_tenant and (tenant := self._tenants.get(region.tenant_id)):
            label = f"{label} - {tenant.name}"
        return label
