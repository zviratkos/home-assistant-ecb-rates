import logging
import xml.etree.ElementTree as ET
from datetime import timedelta
from homeassistant.helpers.entity import Entity
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

_LOGGER = logging.getLogger(__name__)

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
NAMESPACE = {"ns": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}

async def async_setup_platform(hass: HomeAssistantType, config: dict, async_add_entities, discovery_info=None):
    """Set up the ECB exchange rate sensors."""
    currency_pairs = config.get("currency_pairs", [])
    update_interval = config.get("update_interval", timedelta(hours=1))
    precision = config.get("precision", 4)

    _LOGGER.info("Setting up ECB Exchange Rates from configuration.")
    _LOGGER.info("Configured currency pairs: %s", currency_pairs)

    if not currency_pairs:
        _LOGGER.error("No currency pairs configured for ECB exchange rate sensors.")
        return

    sensors = []
    for pair in currency_pairs:
        sensor = ECBExchangeRateSensor(pair, update_interval, precision, hass)
        sensors.append(sensor)

    async_add_entities(sensors)

class ECBExchangeRateSensor(Entity):
    """Representation of a sensor for ECB exchange rate."""

    def __init__(self, currency_pair, update_interval, precision, hass):
        self._currency_pair = currency_pair
        self._update_interval = update_interval
        self._precision = precision
        self._hass = hass
        self._rate = 1.0
        self._name = f"Exchange Rate {currency_pair}"
        self._unique_id = f"ecb_{currency_pair.replace('/', '_')}"
        self._state = None
        self._last_updated = None

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return round(self._rate, self._precision)

    @property
    def unique_id(self):
        return self._unique_id

    async def async_update(self):
        """Fetch data from ECB and refresh rates."""
        try:
            _LOGGER.info("Fetching ECB data from URL: %s", ECB_URL)
            async with aiohttp.ClientSession() as session:
                async with session.get(ECB_URL) as response:
                    content = await response.text()
                    if response.status != 200:
                        _LOGGER.error("Failed to fetch data from ECB API. Status code: %d", response.status)
                        return

                    root = ET.fromstring(content)
                    rates = {"EUR": 1.0}
                    available_currencies = []

                    # Find the Cube with time attribute inside the namespace
                    cube_time = root.find(".//ns:Cube[@time]", NAMESPACE)
                    if cube_time is not None:
                        for cube in cube_time.findall("ns:Cube", NAMESPACE):
                            currency = cube.attrib.get("currency")
                            rate = cube.attrib.get("rate")
                            if currency and rate:
                                rates[currency] = float(rate)
                                available_currencies.append(currency)
                    else:
                        _LOGGER.warning("No Cube[@time] found in ECB XML.")

                    pair = self._currency_pair.split("/")
                    if len(pair) == 2 and pair[0] in rates and pair[1] in rates:
                        self._rate = rates[pair[0]] / rates[pair[1]]
                    else:
                        _LOGGER.warning("Currency pair %s not found in ECB data.", self._currency_pair)
                        self._rate = 1.0

                    _LOGGER.info("ECB exchange rate updated: %s = %s", self._currency_pair, self._rate)
                    _LOGGER.info("Currencies found in ECB data: %s", available_currencies)

        except Exception as e:
            _LOGGER.error("Failed to refresh ECB rates: %s", e)


