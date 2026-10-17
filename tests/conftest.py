"""Fixtures for E.ON EnergieMonitor tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eon_energiemonitor.const import (
    API_BASE_URL,
    CONF_REGION_CODE,
    CONF_TENANT_ID,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

REGION_CODE = "09772147"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:  # noqa: ARG001
    """Enable custom integrations in all tests."""
    return


def fixture_text(name: str) -> str:
    """Load a fixture file."""
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for Gersthofen."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Gersthofen",
        unique_id=REGION_CODE,
        data={CONF_REGION_CODE: REGION_CODE, CONF_TENANT_ID: "LEW"},
    )


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Mock all API endpoints with fixture data."""
    headers = {"Content-Type": "application/json"}
    aioclient_mock.get(
        f"{API_BASE_URL}/tenants", text=fixture_text("tenants.json"), headers=headers
    )
    aioclient_mock.get(
        f"{API_BASE_URL}/region-data?tenantId=LEW",
        text=fixture_text("regions_lew.json"),
        headers=headers,
    )
    aioclient_mock.get(
        f"{API_BASE_URL}/region-data?tenantId=3190",
        text=fixture_text("regions_bayernwerk.json"),
        headers=headers,
    )
    aioclient_mock.get(
        f"{API_BASE_URL}/region-data?tenantId=2700",
        json={"regions": []},
    )
    aioclient_mock.get(
        f"{API_BASE_URL}/region-data?regionCode={REGION_CODE}",
        text=fixture_text("region.json"),
        headers=headers,
    )
    aioclient_mock.get(
        f"{API_BASE_URL}/meter-data",
        text=fixture_text("meter_data.json"),
        headers=headers,
    )
    return aioclient_mock


@pytest.fixture
def mock_setup_entry() -> Generator[None]:
    """Prevent setting up the integration during config flow tests."""
    with patch(
        "custom_components.eon_energiemonitor.async_setup_entry", return_value=True
    ):
        yield
