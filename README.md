# Meteo-Volt Home Assistant Integration

This custom integration fetches prediction data from the Meteo-Volt API and provides three sensor entities for the quantiles:
- Q10
- Q50
- Q90

The state of the sensor represents the predicted value for the current 15-minute slot. The full prediction timeseries (672 slots) is available as an attribute on each sensor.

## Installation via HACS

1. Go to HACS -> Integrations.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add the URL of this repository and select **Integration** as category.
4. Click **Add**.
5. Once added, you can find **Meteo-Volt** in HACS and click **Download**.
6. Restart Home Assistant.

## Configuration

1. Go to **Settings** -> **Devices & Services**.
2. Click **Add Integration** in the bottom right corner.
3. Search for **Meteo-Volt**.
4. Enter your API token.
5. Click **Submit**.

The integration will automatically update the data every hour.
