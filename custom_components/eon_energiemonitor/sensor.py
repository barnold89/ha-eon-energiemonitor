"""Sensor platform for the E.ON EnergieMonitor integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfMass,
    UnitOfPower,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN, LOGGER

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .api import MeterData, MeterValue
    from .coordinator import EnergieMonitorConfigEntry, EnergieMonitorCoordinator

# Coordinator based, no polling per entity.
PARALLEL_UPDATES = 0

FEED_IN_SOURCES = ("solar", "wind", "bio", "water", "others")
CONSUMERS = ("domestic", "industrial", "public")

# The EnergieMonitor resets its daily values at local midnight in Germany.
API_TIME_ZONE = dt_util.get_time_zone("Europe/Berlin")


def _interval_start(data: MeterData) -> datetime:
    return data.start


def _day_start(data: MeterData) -> datetime:
    local_midnight = data.start.astimezone(API_TIME_ZONE).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return dt_util.as_utc(local_midnight)


@dataclass(frozen=True, kw_only=True)
class EnergieMonitorSensorEntityDescription(SensorEntityDescription):
    """Describes an EnergieMonitor sensor."""

    value_fn: Callable[[MeterData], float | int | datetime | None]
    last_reset_fn: Callable[[MeterData], datetime] | None = None


SENSORS: tuple[EnergieMonitorSensorEntityDescription, ...] = (
    EnergieMonitorSensorEntityDescription(
        key="autarky",
        translation_key="autarky",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.autarky,
    ),
    EnergieMonitorSensorEntityDescription(
        key="energy_mix",
        translation_key="energy_mix",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.energy_mix,
    ),
    EnergieMonitorSensorEntityDescription(
        key="consumption",
        translation_key="consumption",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.consumption_total,
        last_reset_fn=_interval_start,
    ),
    EnergieMonitorSensorEntityDescription(
        key="generation",
        translation_key="generation",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.feed_in_total,
        last_reset_fn=_interval_start,
    ),
    EnergieMonitorSensorEntityDescription(
        key="renewable_generation",
        translation_key="renewable_generation",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.feed_in_renewables,
        last_reset_fn=_interval_start,
    ),
    EnergieMonitorSensorEntityDescription(
        key="grid_supply",
        translation_key="grid_supply",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.grid_supply,
        last_reset_fn=_interval_start,
    ),
    EnergieMonitorSensorEntityDescription(
        key="co2_savings_today",
        translation_key="co2_savings_today",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        # Fossil generation lowers the value, so it is not strictly increasing.
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.daily_co2_savings,
        last_reset_fn=_day_start,
    ),
    EnergieMonitorSensorEntityDescription(
        key="measurement_start",
        translation_key="measurement_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.start,
    ),
)


def _value_descriptions(
    group: str,
    name: str,
    getter: Callable[[MeterData], dict[str, MeterValue]],
    *,
    with_capacity: bool,
) -> list[EnergieMonitorSensorEntityDescription]:
    """Build the sensor descriptions for a generation source or consumer group."""

    def _value(data: MeterData) -> MeterValue | None:
        return getter(data).get(name)

    descriptions = [
        EnergieMonitorSensorEntityDescription(
            key=f"{group}_{name}",
            translation_key=f"{group}_{name}",
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.TOTAL,
            suggested_display_precision=0,
            value_fn=lambda data: value.energy if (value := _value(data)) else None,
            last_reset_fn=_interval_start,
        ),
        EnergieMonitorSensorEntityDescription(
            key=f"{group}_{name}_installations",
            translation_key=f"{group}_{name}_installations",
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
            value_fn=lambda data: (
                value.installations if (value := _value(data)) else None
            ),
        ),
    ]
    if with_capacity:
        # The web UI labels solar capacity as kWp, all others as kW.
        descriptions.append(
            EnergieMonitorSensorEntityDescription(
                key=f"{group}_{name}_installed_capacity",
                translation_key=f"{group}_{name}_installed_capacity",
                device_class=SensorDeviceClass.POWER,
                native_unit_of_measurement=UnitOfPower.KILO_WATT,
                suggested_display_precision=0,
                entity_registry_enabled_default=False,
                value_fn=lambda data: (
                    value.installed_capacity if (value := _value(data)) else None
                ),
            )
        )
    return descriptions


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: EnergieMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up EnergieMonitor sensors based on a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    descriptions = list(SENSORS)
    # Only create per-cluster sensors for clusters the region actually reports.
    for source in FEED_IN_SOURCES:
        if source in data.feed_in:
            descriptions.extend(
                _value_descriptions(
                    "generation", source, lambda d: d.feed_in, with_capacity=True
                )
            )
    for consumer in CONSUMERS:
        if consumer in data.consumptions:
            descriptions.extend(
                _value_descriptions(
                    "consumption",
                    consumer,
                    lambda d: d.consumptions,
                    with_capacity=False,
                )
            )

    unknown = (set(data.feed_in) - set(FEED_IN_SOURCES)) | (
        set(data.consumptions) - set(CONSUMERS)
    )
    if unknown:
        LOGGER.debug("Ignoring unknown clusters: %s", ", ".join(sorted(unknown)))

    async_add_entities(
        EnergieMonitorSensor(coordinator, description) for description in descriptions
    )


class EnergieMonitorSensor(
    CoordinatorEntity["EnergieMonitorCoordinator"], SensorEntity
):
    """Representation of an EnergieMonitor sensor."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    entity_description: EnergieMonitorSensorEntityDescription

    def __init__(
        self,
        coordinator: EnergieMonitorCoordinator,
        description: EnergieMonitorSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        region = coordinator.region
        tenant = coordinator.tenant
        self._attr_unique_id = f"{region.region_code}_{description.key}"
        configuration_url = None
        if tenant and tenant.website and region.url_key:
            configuration_url = f"{tenant.website}/{region.url_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, region.region_code)},
            name=region.name,
            manufacturer=tenant.name if tenant else None,
            model="EnergieMonitor",
            model_id=region.region_code,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=configuration_url,
        )

    @property
    def native_value(self) -> float | int | datetime | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def last_reset(self) -> datetime | None:
        """Return the start of the period the value is accumulated over."""
        if (last_reset_fn := self.entity_description.last_reset_fn) is None:
            return None
        return last_reset_fn(self.coordinator.data)
