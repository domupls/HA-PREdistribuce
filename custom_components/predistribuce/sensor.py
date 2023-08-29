__version__ = "1.0"

import math
import logging
import voluptuous as vol
from datetime import timedelta, datetime, date
from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

import requests
from lxml import html, etree

MIN_TIME_BETWEEN_SCANS = timedelta(seconds=3600)
_LOGGER = logging.getLogger(__name__)

DOMAIN = "predistribuce"
CONF_CMD = "receiver_command_id"
CONF_PERIODS = "periods"
CONF_NAME = "name"
CONF_MINUTES = "minutes"

PERIOD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_MINUTES): vol.All(vol.Coerce(int), vol.Range(min=1, max=300))
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_CMD): cv.string,
        vol.Optional(CONF_PERIODS): vol.All(cv.ensure_list, [PERIOD_SCHEMA])
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    conf_cmd = config.get(CONF_CMD)
    ents = []
    ents.append(PreDistribuce(conf_cmd, 0, "HDO čas do nízkého tarifu"))
    add_entities(ents)

class PreDistribuce(Entity):

    def __init__(self, conf_cmd, minutes, name):
        """Initialize the sensor."""
        self.conf_cmd = conf_cmd
        self.minutes = minutes
        self._name = name
        self.time_left_NT = None
        self.time_left_VT = None
        self.start_NT = None
        self.end_NT = None
        self.time_left_VT = None
        self.start_VT = None
        self.end_VT = None
        self.html = "<div><i>Není spojení</i></div>"
        self.tree = ""
        self.update()

    @property
    def name(self):
        """Return name of the sensor."""
        return self._name

    @property
    def unit_of_measurement(self):
        return "minut"

    @property
    def icon(self):
        return "mdi:av-timer"

    def set_states(self):
        """Return time to wait until low tariff."""
        NV_tariffs = self.tree.xpath(
            '//div[@id="component-hdo-dnes"]/div[@class="hdo-bar"]/span[starts-with(@class, "hdo")]/@class')
        hdo_times = self.tree.xpath(
            '//div[@id="component-hdo-dnes"]/div/span[@class="span-overflow"]/@title')
        NV_tariffs = [x[3].upper() for x in NV_tariffs]
        hdo_times_beg = [x[0:5].upper() for x in hdo_times]
        tariff_time = list(zip(NV_tariffs, hdo_times_beg))

        current_datetime = datetime.now()
        current_date = current_datetime.date()

        next_time = None
        next_hdo = None
        for i, (hdo, time_str) in enumerate(tariff_time):
            time_obj = datetime.strptime(time_str, "%H:%M").time()
            tariff_datetime = datetime.combine(current_date, time_obj)
            if tariff_datetime > current_datetime:
                next_time = tariff_datetime
                next_hdo = hdo
                time_difference = next_time - current_datetime
                if next_hdo == "N":
                    end_NT = datetime.strptime(tariff_time[i+1][1], "%H:%M")
                    self._set_tariff_times(next_time, end_NT, time_difference, end_NT, datetime.strptime(
                        tariff_time[i+2][1], "%H:%M"), end_NT - self.start_NT + self.time_left_VT)
                else:
                    start_NT = datetime.strptime(tariff_time[i+1][1], "%H:%M")
                    end_NT = datetime.strptime(tariff_time[i+2][1], "%H:%M")
                    self._set_tariff_times(
                        start_NT, end_NT, (end_NT - start_NT + time_difference), next_time, start_NT, time_difference)
                break

    def _set_tariff_times(self, start_NT, end_NT, left_NT, start_VT, end_VT, left_VT):
        self.start_NT = start_NT
        self.end_NT = end_NT
        self.time_left_NT = left_NT
        self.start_VT = start_VT
        self.end_VT = end_VT
        self.time_left_VT = left_VT

    @ property
    def get_start_NT(self):
        return self.start_NT

    @ property
    def get_end_NT(self):
        return self.end_NT

    @ property
    def get_left_NT(self):
        return self.time_left_NT

    @ property
    def get_start_VT(self):
        return self.start_VT

    @ property
    def get_end_VT(self):
        return self.end_VT

    @ property
    def get_left_VT(self):
        return self.time_left_VT

    @ property
    def device_state_attributes(self):
        attributes = {}
        attributes['HDO čas do vysokého tarifu'] = math.floor(self.timetoVT)
        return attributes

    @ property
    def should_poll(self):
        return True

    @ property
    def available(self):
        """Return if entity is available."""
        return self.last_update_success

    @ property
    def device_class(self):
        return 'plug'

    # TODO make default sensor (minutes=0) responsible for fetching, storing tree and html as static global variables
    @Throttle(MIN_TIME_BETWEEN_SCANS)
    def update(self):
        """Update the entity by scraping website"""
        today = date.today()
        page = requests.get("https://www.predistribuce.cz/cs/potrebuji-zaridit/zakaznici/stav-hdo/?povel={3}&den_od={0}&mesic_od={1}&rok_od={2}&den_do={0}&mesic_do={1}&rok_do={2}".format(
            today.day, today.month, today.year, self.conf_cmd))
        if page.status_code == 200:
            self.tree = html.fromstring(page.content)
            self.html = etree.tostring(self.tree.xpath('//div[@id="component-hdo-dnes"]')[0]).decode(
                "utf-8").replace('\n', '').replace('\t', '').replace('"/>', '"></span>')
            # _LOGGER.warn("UPDATING POST {}".format(self.html))
            self.last_update_success = True
        else:
            self.last_update_success = False
        self.set_states()
