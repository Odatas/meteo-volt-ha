"""Constants for the Meteo-Volt integration."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "meteo_volt"

# Configuration constants
CONF_API_TOKEN = "api_token"
CONF_GRID_FEES = "grid_fees"

# API Endpoint
API_URL = "https://meteo-volt-main-ca19f82.zuplo.app/v1/prediction"

# Polling interval (in seconds)
UPDATE_INTERVAL_SECONDS = 3600

# Spec C5 Abschnitt 5: die Hausanschlussgrenze im Haupteintrag. Nicht
# max_power_kw -- das ist schon ein Feld des Ladepunkts.
CONF_SITE_MAX_POWER = "site_max_power_kw"

# Spec C5 Abschnitt 8: das Repair-Issue nach 12 h ohne neuen Plan.
ISSUE_PLAN_VERALTET = "plan_veraltet"

# Spec C6 Abschnitt 6: das Issue, wenn die Ladegeschwindigkeit mehr als 5 % vom
# Plan abweicht. Die Kennung traegt dahinter die Fahrzeug-ID, die Uebersetzung
# haengt an der Richtung.
ISSUE_ABWEICHUNG = "ladung_abweichung"
ISSUE_SCHNELLER = "ladung_schneller"
ISSUE_LANGSAMER = "ladung_langsamer"

# C3-Spec Abschnitt 7: C5 meldet Beginn und Ende jedes Laufs, je Eintrag. Nutzlast
# ist True oder False. format(entry_id).
SIGNAL_PLANUNG = "meteo_volt_planung_{}"
