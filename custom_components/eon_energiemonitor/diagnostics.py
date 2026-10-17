"""Diagnostics support for the E.ON EnergieMonitor integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import EnergieMonitorConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: EnergieMonitorConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry (all data is public)."""
    coordinator = entry.runtime_data
    return {
        "entry_data": dict(entry.data),
        "region": asdict(coordinator.region),
        "tenant": asdict(coordinator.tenant) if coordinator.tenant else None,
        "last_update_success": coordinator.last_update_success,
        "data": asdict(coordinator.data) if coordinator.data else None,
    }
