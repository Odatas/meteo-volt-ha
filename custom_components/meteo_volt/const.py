"""Constants for the Meteo-Volt integration."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "meteo_volt"

# Configuration constants
CONF_API_TOKEN = "api_token"
CONF_GRID_FEES = "grid_fees"

# API Endpoint
API_URL = "https://meteo-volt-main-55a1407.d2.zuplo.dev/v1/prediction"

# Polling interval (in seconds)
UPDATE_INTERVAL_SECONDS = 3600

# Spec C5 Abschnitt 5: die Hausanschlussgrenze im Haupteintrag. Nicht
# max_power_kw -- das ist schon ein Feld des Ladepunkts.
CONF_SITE_MAX_POWER = "site_max_power_kw"
