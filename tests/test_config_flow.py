"""Tests for the E.ON EnergieMonitor config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.eon_energiemonitor.const import (
    ALL_TENANTS,
    API_BASE_URL,
    CONF_REGION_CODE,
    CONF_TENANT_ID,
    DOMAIN,
)

from .conftest import REGION_CODE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


def _option_values(result: dict, key: str) -> list[str]:
    schema = result["data_schema"].schema
    selector = next(value for k, value in schema.items() if k == key)
    return [option["value"] for option in selector.config["options"]]


@pytest.mark.usefixtures("mock_api")
async def test_full_flow(hass: HomeAssistant) -> None:
    """Test selecting a tenant and a region and creating an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # Tenants without regions are not offered.
    assert _option_values(result, CONF_TENANT_ID) == [ALL_TENANTS, "3190", "LEW"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TENANT_ID: "LEW"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "region"
    assert REGION_CODE in _option_values(result, CONF_REGION_CODE)
    assert result["description_placeholders"] == {"count": "8"}
    assert result["data_schema"].schema[CONF_REGION_CODE].config["custom_value"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION_CODE: REGION_CODE}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Gersthofen"
    assert result["data"] == {CONF_REGION_CODE: REGION_CODE, CONF_TENANT_ID: "LEW"}
    assert result["result"].unique_id == REGION_CODE


@pytest.mark.usefixtures("mock_api")
async def test_all_tenants_labels(hass: HomeAssistant) -> None:
    """Test region labels include the tenant when all tenants are selected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TENANT_ID: ALL_TENANTS}
    )
    assert result["step_id"] == "region"
    labels = [
        option["label"]
        for option in result["data_schema"].schema[CONF_REGION_CODE].config["options"]
    ]
    assert "Gersthofen (09772147) - Lechwerke AG" in labels


@pytest.mark.usefixtures("mock_api")
async def test_free_text_region(hass: HomeAssistant) -> None:
    """Test a unique free-text value is resolved to a region."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TENANT_ID: "LEW"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION_CODE: " gersthofen "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REGION_CODE] == REGION_CODE


@pytest.mark.usefixtures("mock_api")
async def test_without_search_lists_all_visible_regions(hass: HomeAssistant) -> None:
    """Test that an empty search lists all regions except hidden ones."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TENANT_ID: "LEW"}
    )
    values = _option_values(result, CONF_REGION_CODE)
    assert len(values) == 8
    assert "09772999" not in values


@pytest.mark.usefixtures("mock_api")
async def test_no_results(hass: HomeAssistant) -> None:
    """Test an unknown free-text region shows an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TENANT_ID: "3190"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION_CODE: "Memmingen"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "region"
    assert result["errors"] == {CONF_REGION_CODE: "no_results"}


async def test_cannot_connect_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the flow aborts when the API is unreachable."""
    aioclient_mock.get(f"{API_BASE_URL}/tenants", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.parametrize(
    ("status", "error"), [(404, "no_data"), (500, "cannot_connect")]
)
async def test_meter_data_errors_and_recovery(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    status: int,
    error: str,
) -> None:
    """Test errors while validating the selected region and recovering."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TENANT_ID: "LEW"}
    )

    mocks = list(mock_api._mocks)  # noqa: SLF001
    mock_api.clear_requests()
    mock_api.get(f"{API_BASE_URL}/meter-data", status=status, text="error")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION_CODE: REGION_CODE}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_api.clear_requests()
    mock_api._mocks.extend(mocks)  # noqa: SLF001
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION_CODE: REGION_CODE}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_api")
async def test_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test a region can only be configured once."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TENANT_ID: "LEW"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_REGION_CODE: REGION_CODE}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
