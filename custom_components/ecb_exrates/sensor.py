import logging
import xml.etree.ElementTree as ET
from datetime import timedelta
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
import aiohttp
from homeassistant.helpers.typing import HomeAssistantType

_LOGGER = logging.getLogger(__name__)

# ECB exchange rate XML feed URL
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"

async def async_setup_platform(hass: HomeAssistantType, config: dict, async_add_entities, discovery_info=None):
    """Set up the ECB exchange rate sensors."""
    currency_pairs = config.get("currency_pairs", [])
    update_interval_raw = config.get("update_interval", 1)  # in hours
    precision = config.get("precision", 4)

    try:
        update_interval = timedelta(hours=int(update_interval_raw))
    except Exception as e:
        _LOGGER.warning("Invalid update_interval '%s'. Defaulting to 1 hour. Error: %s", update_interval_raw, e)
        update_interval = timedelta(hours=1)

    _LOGGER.info("Setting up ECB Exchange Rates.")
    _LOGGER.info("Configured currency pairs: %s", currency_pairs)
    _LOGGER.info("Update interval set to: %s", update_interval)

    if not currency_pairs:
        _LOGGER.error("No currency pairs configured.")
        return

    sensors = []
    for pair in currency_pairs:
        sensor = ECBExchangeRateSensor(pair, update_interval, precision, hass)
        sensors.append(sensor)
        # Schedule regular updates
        async_track_time_interval(hass, sensor.async_update, update_interval)

    async_add_entities(sensors, update_before_add=True)


class ECBExchangeRateSensor(Entity):
    """Representation of an ECB exchange rate sensor."""

    def __init__(self, currency_pair, update_interval, precision, hass):
        self._currency_pair = currency_pair
        self._update_interval = update_interval
        self._precision = precision
        self._hass = hass
        self._rate = 1.0
        self._name = f"Exchange Rate {currency_pair}"
        self._unique_id = f"ecb_{currency_pair.replace('/', '_')}"
        self._state = None
        self._available = True

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return round(self._rate, self._precision)

    @property
    def device_class(self):
        return "monetary"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def available(self):
        return self._available

    @property
    def should_poll(self):
        """Disable polling, updates are done via async_track_time_interval."""
        return False

    async def async_update(self, now=None):
        """Fetch and update the exchange rate."""
        try:
            _LOGGER.info("Fetching ECB data from URL: %s", ECB_URL)
            async with aiohttp.ClientSession() as session:
                async with session.get(ECB_URL) as response:
                    if response.status != 200:
                        _LOGGER.error("Failed to fetch ECB data. Status: %d", response.status)
                        self._available = False
                        return

                    content = await response.text()
                    root = ET.fromstring(content)

                    ns = {'gesmes': 'http://www.gesmes.org/xml/2002-08-01',
                          'e': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'}

                    rates = {"EUR": 1.0}
                    available_currencies = []

                    # Find rates in the nested Cube elements
                    for cube in root.findall('.//e:Cube/e:Cube/e:Cube', ns):
                        currency = cube.attrib.get("currency")
                        rate = cube.attrib.get("rate")
                        if currency and rate:
                            try:
                                rate_val = float(rate)
                                rates[currency] = rate_val
                                available_currencies.append(currency)
                            except ValueError:
                                _LOGGER.warning("Invalid rate format for currency %s: %s", currency, rate)

                    # Split currency pair like "USD/CZK"
                    base, quote = self._currency_pair.split("/")
                    if base in rates and quote in rates:
                        self._rate = rates[base] / rates[quote]
                        self._available = True
                        _LOGGER.info("ECB exchange rate updated: %s = %s", self._currency_pair, self._rate)
                        _LOGGER.info("Currencies found in ECB data: %s", available_currencies)
                    else:
                        self._rate = 1.0
                        self._available = False
                        _LOGGER.warning("Currency pair %s not found in ECB data.", self._currency_pair)

        except Exception as e:
            self._available = False
            _LOGGER.error("Error updating ECB exchange rate: %s", e)

