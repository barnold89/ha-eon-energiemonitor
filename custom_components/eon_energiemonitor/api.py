"""Client for the public E.ON EnergieMonitor API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

import aiohttp

from .const import API_BASE_URL

REQUEST_TIMEOUT = 15

# Municipal installations are merged into their source, like the website does.
PUBLIC_FEED_IN_SOURCES = {
    "pubbio": "bio",
    "pubsol": "solar",
    "pubwat": "water",
    "pubwin": "wind",
    "pubchp": "others",
    "pubgeo": "others",
    "pubmis": "others",
}


class EnergieMonitorError(Exception):
    """Base exception for the EnergieMonitor API."""


class EnergieMonitorConnectionError(EnergieMonitorError):
    """Raised when the API cannot be reached or returns an invalid response."""


class EnergieMonitorNotFoundError(EnergieMonitorError):
    """Raised when the requested region does not exist."""


@dataclass(frozen=True, slots=True)
class Tenant:
    """A network operator (Netzbetreiber) hosting EnergieMonitor regions."""

    tenant_id: str
    name: str
    hostnames: tuple[str, ...] = ()

    @property
    def website(self) -> str | None:
        """Return the production website of the tenant."""
        # Hostnames are ordered DEV, QA, PROD, (aliases) like in the web frontend.
        if len(self.hostnames) > 2:  # noqa: PLR2004
            return f"https://{self.hostnames[2]}"
        if self.hostnames:
            return f"https://{self.hostnames[-1]}"
        return None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tenant:
        """Create a tenant from an API response item."""
        return cls(
            tenant_id=str(data["tenantId"]),
            name=data.get("tenantFull") or data.get("name") or str(data["tenantId"]),
            hostnames=tuple(data.get("hostnames") or ()),
        )


@dataclass(frozen=True, slots=True)
class Region:
    """A region (municipality, district, ...) of the EnergieMonitor."""

    region_code: str
    name: str
    tenant_id: str
    url_key: str | None = None
    hidden: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Region:
        """Create a region from an API response item."""
        return cls(
            region_code=str(data["regionCode"]),
            name=data.get("regionName") or str(data["regionCode"]),
            tenant_id=str(data.get("tenantId", "")),
            url_key=data.get("regionUrlKey"),
            hidden=bool(data.get("hidden", False)),
        )


@dataclass(frozen=True, slots=True)
class MeterValue:
    """Energy of a single generation or consumption cluster in one interval."""

    name: str
    energy: float
    installations: int | None
    installed_capacity: float | None


@dataclass(frozen=True, slots=True)
class MeterData:
    """Meter data of a region for the latest 15-minute interval (energies in kWh)."""

    region_code: str
    start: datetime
    end: datetime
    autarky: float | None
    energy_mix: float | None
    consumption_total: float | None
    feed_in_total: float | None
    feed_in_renewables: float | None
    # API field "secondaryInFeed": max(0, consumption - generation), "Netzbezug".
    grid_supply: float | None
    daily_co2_savings: float | None
    consumptions: dict[str, MeterValue] = field(default_factory=dict)
    feed_in: dict[str, MeterValue] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MeterData:
        """Create meter data from an API response."""
        timestamp = data.get("timestamp") or {}
        start = _to_datetime(timestamp.get("start"))
        end = _to_datetime(timestamp.get("end"))
        if start is None or end is None:
            msg = "Meter data does not contain a valid timestamp"
            raise EnergieMonitorConnectionError(msg)
        consumptions = data.get("consumptions") or {}
        feed_in = data.get("feedIn") or {}
        return cls(
            region_code=str(data.get("regionCode", "")),
            start=start,
            end=end,
            autarky=_to_float(data.get("autarky")),
            energy_mix=_to_float(data.get("energyMix")),
            consumption_total=_to_float(consumptions.get("total")),
            feed_in_total=_to_float(feed_in.get("total")),
            feed_in_renewables=_to_float(data.get("feedInRenewables")),
            grid_supply=_to_float(data.get("secondaryInFeed")),
            daily_co2_savings=_to_float(data.get("dailyCo2Savings")),
            consumptions=_parse_values(consumptions.get("list")),
            feed_in=_merge_public(_parse_values(feed_in.get("list"))),
        )


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except TypeError, ValueError:
        return None


def _to_datetime(value: Any) -> datetime | None:
    seconds = _to_int(value)
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC)


def _parse_values(items: Any) -> dict[str, MeterValue]:
    values: dict[str, MeterValue] = {}
    for item in items or ():
        name = item.get("name")
        energy = _to_float(item.get("usage"))
        if not name or energy is None:
            continue
        values[name] = MeterValue(
            name=name,
            energy=energy,
            installations=_to_int(item.get("numberOfInstallations")),
            installed_capacity=_to_float(item.get("installedCapacity")),
        )
    return values


def _add[T: (int, float)](first: T | None, second: T | None) -> T | None:
    if first is None or second is None:
        return first if second is None else second
    return first + second


def _merge_public(values: dict[str, MeterValue]) -> dict[str, MeterValue]:
    merged: dict[str, MeterValue] = {}
    for name, value in values.items():
        target = PUBLIC_FEED_IN_SOURCES.get(name, name)
        if (existing := merged.get(target)) is None:
            merged[target] = MeterValue(
                name=target,
                energy=value.energy,
                installations=value.installations,
                installed_capacity=value.installed_capacity,
            )
            continue
        merged[target] = MeterValue(
            name=target,
            energy=existing.energy + value.energy,
            installations=_add(existing.installations, value.installations),
            installed_capacity=_add(
                existing.installed_capacity, value.installed_capacity
            ),
        )
    return merged


class EnergieMonitorClient:
    """Client for the EnergieMonitor API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str = API_BASE_URL,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._base_url = base_url

    async def async_get_tenants(self) -> list[Tenant]:
        """Return all tenants (network operators)."""
        data = await self._request("tenants")
        return [Tenant.from_dict(item) for item in data or ()]

    async def async_get_regions(self, tenant_id: str) -> list[Region]:
        """Return all visible regions of a tenant."""
        data = await self._request(
            "region-data", {"regionCode": "", "tenantId": tenant_id}
        )
        regions = [Region.from_dict(item) for item in (data or {}).get("regions", ())]
        return [region for region in regions if not region.hidden]

    async def async_get_all_regions(self, tenants: list[Tenant]) -> list[Region]:
        """Return all visible regions of the given tenants."""
        results = await asyncio.gather(
            *(self.async_get_regions(tenant.tenant_id) for tenant in tenants)
        )
        return [region for regions in results for region in regions]

    async def async_get_region(self, region_code: str) -> Region:
        """Return a single region."""
        data = await self._request("region-data", {"regionCode": region_code})
        if not data:
            msg = f"Region {region_code} not found"
            raise EnergieMonitorNotFoundError(msg)
        return Region.from_dict(data)

    async def async_get_meter_data(self, region_code: str) -> MeterData:
        """Return the latest meter data of a region."""
        data = await self._request("meter-data", {"regionCode": region_code})
        if not data:
            msg = f"No meter data available for region {region_code}"
            raise EnergieMonitorNotFoundError(msg)
        return MeterData.from_dict(data)

    async def _request(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = f"{self._base_url}/{path}"
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.get(url, params=params) as response,
            ):
                if response.status == HTTPStatus.NOT_FOUND:
                    msg = f"Resource not found: {path}"
                    raise EnergieMonitorNotFoundError(msg)
                response.raise_for_status()
                if response.status == HTTPStatus.NO_CONTENT:
                    return None
                return await response.json()
        except TimeoutError as err:
            msg = f"Timeout while requesting {path}"
            raise EnergieMonitorConnectionError(msg) from err
        except (aiohttp.ClientError, ValueError) as err:
            msg = f"Error while requesting {path}: {err}"
            raise EnergieMonitorConnectionError(msg) from err
