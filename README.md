# E.ON EnergieMonitor for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)

Custom integration that brings the regional energy data of the
[E.ON EnergieMonitor](https://energiemonitor.bayernwerk.de/) into Home Assistant.
The EnergieMonitor is operated by E.ON network operators (Bayernwerk, Avacon,
E.DIS, Lechwerke, Schleswig-Holstein Netz, Westenergie, VSE, ...) and shows the
current generation and consumption of a municipality or district.

## Features

- Config flow with autocomplete: pick your network operator, then search for your
  region by name or official municipality key (AGS).
- One device per region with sensors for:
  - Self-sufficiency (Eigenversorgung) and renewable energy share
  - Total consumption, generation and grid supply (Netzbezug) in kWh of the latest 15-minute interval
  - Generation per source (solar, wind, biomass, hydro, others)
  - Consumption per group (households, commercial, municipal facilities)
  - CO2 savings of the current day (resets at midnight)
  - Number of installations and installed capacity per source (disabled by default)
- Diagnostics download, German and English translations.

The data is updated every 5 minutes; the EnergieMonitor publishes values in
15-minute intervals. Energy sensors show the kWh of the latest interval, like the
website, and use `last_reset` so long-term statistics sum them up correctly.

## Installation

### HACS

1. Open HACS, go to the menu in the top right and choose **Custom repositories**.
1. Add `https://github.com/barnold89/ha-eon-energiemonitor` with the category **Integration**.
1. Search for **E.ON EnergieMonitor** and install it.
1. Restart Home Assistant.

### Manual

Copy `custom_components/eon_energiemonitor` into the `custom_components`
folder of your Home Assistant configuration and restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & services → Add integration** and select **E.ON EnergieMonitor**.
1. Select your network operator or keep **All network operators**.
1. Start typing the region name or AGS (e.g. `Gersthofen` or `09772147`) and
   pick your region from the suggestions.

Add the integration multiple times to monitor several regions.

## Removal

Remove the integration via **Settings → Devices & services → E.ON EnergieMonitor → Delete**,
then uninstall it in HACS.

## Development

```bash
scripts/setup     # install dependencies
scripts/develop   # run Home Assistant with the integration on port 8123
scripts/lint      # ruff format + lint
python3 -m pytest # run tests
```

## Disclaimer

This project is not affiliated with E.ON or any of its network operators. It uses
the public API of the EnergieMonitor web application.
