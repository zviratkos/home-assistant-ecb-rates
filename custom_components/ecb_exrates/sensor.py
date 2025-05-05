import xml.etree.ElementTree as ET
import logging
from datetime import timedelta
from aiohttp import ClientSession
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN, ECB_URL

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    symbols_config = config.get("symbols", [])
    update_interval = timedelta(hours=config.get("update_interval", 12))
    precision = config.get("precision", 4)

    pairs = []
    for symbol in symbols_config:
        if "/" in symbol:
            base, quote = symbol.upper().split("/")
            pairs.append((base, quote))
        else:
            _LOGGER.warning("Invalid symbol format: %s", symbol)

    if not pairs:
        _LOGGER.error("No valid currency pairs provided in configuration")
        return

    coordinator = EcbCoordinator(hass)
    await coordinator.async_refresh()

    sensors = []
    for base, quote in pairs:
        if base in coordinator.rates and quote in coordinator.rates:
            sensors.append(ExchangeRateSensor(coordinator, base, quote, precision))
        else:
            _LOGGER.warning("Missing currency in ECB data: %s or %s", base, quote)
    async_add_entities(sensors)

    async_track_time_interval(hass, coordinator.async_refresh, update_interval)


class EcbCoordinator:
    def __init__(self, hass):
        self.hass = hass
        self.rates = {}

    async def async_refresh(self, *_):
        session: ClientSession = async_get_clientsession(self.hass)
        try:
            async with session.get(ECB_URL) as response:
                content = await response.text()
                root = ET.fromstring(content)
                rates = {"EUR": 1.0}
                for cube in root.findall(".//Cube/Cube/Cube"):
                    currency = cube.attrib["currency"]
                    rate = float(cube.attrib["rate"])
                    rates[currency] = rate
                self.rates = rates
                _LOGGER.info("ECB exchange rates updated: %s", rates)
        except Exception as e:
            _LOGGER.error("Failed to refresh ECB rates: %s", e)


class ExchangeRateSensor(Entity):
    def __init__(self, coordinator, base, quote, precision):
        self.coordinator = coordinator
        self.base = base
        self.quote = quote
        self.precision = precision
        self._pair_id = f"{base}{quote}".lower()

    @property
    def name(self):
        return f"Exchange Rate {self.base}/{self.quote}"

    @property
    def state(self):
        if self.base in self.coordinator.rates and self.quote in self.coordinator.rates:
            return round(self.coordinator.rates[self.quote] / self.coordinator.rates[self.base], self.precision)
        return None

    @property
    def unique_id(self):
        return f"sensor.ecbrates.{self._pair_id}"

    @property
    def unit_of_measurement(self):
        return self.quote

    @property
    def device_class(self):
        return "monetary"

    @property
    def should_poll(self):
        return False

    async def async_update(self):
        await self.coordinator.async_refresh()

