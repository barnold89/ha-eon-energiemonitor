"""Constants for the E.ON EnergieMonitor integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Final

DOMAIN: Final = "eon_energiemonitor"
LOGGER = logging.getLogger(__package__)

API_BASE_URL: Final = "https://api-energiemonitor.eon.com"
ATTRIBUTION: Final = "Data provided by E.ON EnergieMonitor"

CONF_REGION_CODE: Final = "region_code"
CONF_TENANT_ID: Final = "tenant_id"

ALL_TENANTS: Final = "all"

# The web frontend refreshes meter data every 5 minutes; values are 15-minute intervals.
UPDATE_INTERVAL: Final = timedelta(minutes=5)
