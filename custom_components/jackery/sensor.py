"""Jackery Sensor Platform."""
import asyncio
import json
import logging
import random
import re
import time
from typing import Any

from homeassistant.components import mqtt as ha_mqtt
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

REQUEST_INTERVAL = 10  # seconds; intentionally 10 s (upstream uses 5 s — too much MQTT traffic for homelab)
OFFLINE_TIMEOUT = 60  # seconds without any message → mark entities unavailable
# If the device never answers within this window after setup the token is most likely rejected
# (the device stays silent on a bad token instead of replying with an error).
REAUTH_HINT_TIMEOUT = 120

# Device model lookup from deviceType field in MQTT payload
DEVICE_TYPE_MODEL_MAP: dict[int, str] = {
    3: "DIY3",   # SolarVault 3 Pro Max
}
DEFAULT_MODEL = "Energy Monitor"

# ENUM value → option-key maps for status sensors (Ü5/Ü6 from upstream v2.0.0)
DEVICE_STATUS_MAP: dict[int, str] = {
    0: "normal", 1: "waiting", 2: "alarm", 3: "fault", 4: "standby", 5: "low_power",
}
ONGRID_STATUS_MAP: dict[int, str] = {0: "disconnected", 1: "connected"}
CT_STATUS_MAP: dict[int, str] = {0: "disconnected", 1: "connected"}
GRID_METER_LINK_MAP: dict[int, str] = {0: "not_linked", 1: "linked"}

# 传感器配置
SENSORS = {
    # 电池相关
    "battery_soc": {
        "json_key": "batSoc",
        "name": "Battery SOC",
        "unit": PERCENTAGE,
        "icon": "mdi:battery-50",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_charge_power": {
        "json_key": "batInPw",
        "name": "Main Unit Charge Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:battery-charging",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_discharge_power": {
        "json_key": "batOutPw",
        "name": "Main Unit Discharge Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:battery-minus",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "total_battery_charge_power": {
        "json_key": "total_battery_charge_power",
        "name": "Total Battery Charge Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:battery-charging",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "total_battery_discharge_power": {
        "json_key": "total_battery_discharge_power",
        "name": "Total Battery Discharge Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:battery-minus",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_temperature": {
        "json_key": "cellTemp",
        "name": "Battery Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_count": {
        "json_key": "batNum",
        "name": "Battery Count",
        "unit": None,
        "icon": "mdi:battery-multiple",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # 电池能量统计
    "battery_charge_energy": {
        "json_key": "batChgEgy",
        "name": "Battery Charge Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:battery-plus",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "battery_discharge_energy": {
        "json_key": "batDisChgEgy",
        "name": "Battery Discharge Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:battery-minus",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },

    # 太阳能
    "solar_power": {
        "json_key": "pvPw",
        "name": "Solar Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:solar-power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "solar_energy": {
        "json_key": "pvEgy",
        "name": "Solar Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:solar-power",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "solar_power_pv1": {
        "json_key": "pv1",
        "name": "Solar Power PV1",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:solar-panel",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "solar_energy_pv1": {
        "json_key": "pv1Egy",
        "name": "Solar Energy PV1",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:solar-panel",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "solar_power_pv2": {
        "json_key": "pv2",
        "name": "Solar Power PV2",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:solar-panel",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "solar_energy_pv2": {
        "json_key": "pv2Egy",
        "name": "Solar Energy PV2",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:solar-panel",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "solar_power_pv3": {
        "json_key": "pv3",
        "name": "Solar Power PV3",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:solar-panel",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "solar_energy_pv3": {
        "json_key": "pv3Egy",
        "name": "Solar Energy PV3",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:solar-panel",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "solar_power_pv4": {
        "json_key": "pv4",
        "name": "Solar Power PV4",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:solar-panel",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "solar_energy_pv4": {
        "json_key": "pv4Egy",
        "name": "Solar Energy PV4",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:solar-panel",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },

    # 电网相关
    "grid_import_power": { # Grid -> System (outOngridPw)
        "json_key": "inOngridPw",
        "name": "Grid Import Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:transmission-tower-import",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_import_energy": {
        "json_key": "inOngridEgy",
        "name": "Grid Import Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:transmission-tower-import",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "grid_export_power": { # System -> AC bus / home (outOngridPw); NOT net export to public grid
        "json_key": "outOngridPw",
        "name": "OnGrid AC Output Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:transmission-tower-export",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_export_energy": {
        "json_key": "outOngridEgy",
        "name": "Grid Export Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:transmission-tower-export",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "max_output_power": {
        "json_key": "maxOutPw",
        "name": "Max Output Power (OnGrid)",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },

    # EPS (离网输出)
    "eps_output_power": {
        "json_key": "swEpsOutPw",
        "name": "EPS Output Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:power-plug",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "eps_output_energy": {
        "json_key": "outEpsEgy",
        "name": "EPS Output Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:power-plug",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "eps_input_power": {
        "json_key": "swEpsInPw",
        "name": "EPS Input Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:power-plug",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "eps_input_energy": {
        "json_key": "inEpsEgy",
        "name": "EPS Input Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:power-plug",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "eps_state": {
         "json_key": "swEpsState",
         "name": "EPS State",
         "unit": None,
         "icon": "mdi:power-settings",
         "device_class": None,
         "state_class": None, # 1-Normal, 0-Abnormal
    },
    "eps_switch": {
         "json_key": "swEps",
         "name": "EPS Switch Status",
         "unit": None,
         "icon": "mdi:toggle-switch",
         "device_class": None,
         "state_class": None, # 1-On, 0-Off
    },

    # Limits & Settings & Status
    "soc_charge_limit": {
        "json_key": "socChgLimit",
        "name": "SOC Charge Limit",
        "unit": PERCENTAGE,
        "icon": "mdi:battery-arrow-up",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "soc_discharge_limit": {
        "json_key": "socDischgLimit",
        "name": "SOC Discharge Limit",
        "unit": PERCENTAGE,
        "icon": "mdi:battery-arrow-down",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "soc_force_charge": {
        "json_key": "socForceChg",
        "name": "SOC Force Charge Target",
        "unit": PERCENTAGE,
        "icon": "mdi:battery-arrow-up-outline",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # "is_auto_standby": {
    #     "json_key": "isAutoStandby",
    #     "name": "Auto Standby Allowed",
    #     "unit": None,
    #     "icon": "mdi:power-sleep",
    #     "device_class": None,
    #     "state_class": None, # 1-Allowed, 0-Not Allowed
    # },
    # "auto_standby_status": {
    #     "json_key": "autoStandby",
    #     "name": "Auto Standby Mode",
    #     "unit": None,
    #     "icon": "mdi:power-sleep",
    #     "device_class": None,
    #     "state_class": None, # 0-Invalid, 1-Sleep/Off, 2-On
    # },

    # Calculated Sensors
    "home_power": {
        "json_key": "calc_home_power",
        "name": "Home Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:home-lightning-bolt",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "battery_net_power": {
        "json_key": "calc_batt_net_power",
        "name": "Battery Net Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:battery-sync",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_net_power": {
        "json_key": "calc_grid_net_power",
        "name": "Grid Net Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:transmission-tower",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # 更多能量流向统计
    "ac_to_battery_energy": {
        "json_key": "acOtBatEgy",
        "name": "AC to Battery Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:battery-arrow-up",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "pv_to_battery_energy": {
        "json_key": "pvOtBatEgy",
        "name": "PV to Battery Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:solar-power-variant",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "pv_to_ac_energy": {
        "json_key": "pvOtAcEgy",
        "name": "PV to AC Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:solar-panel",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "pv_to_grid_energy": {
        "json_key": "pvOtOngridEgy",
        "name": "PV to Grid Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:transmission-tower-export",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "grid_to_ac_load_energy": {
        "json_key": "ongridOtAcLoadEgy",
        "name": "Grid to AC Load Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:home-import-outline",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "battery_to_ac_energy": {
        "json_key": "batOtAcEgy",
        "name": "Battery to AC Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:battery-arrow-down",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "battery_to_grid_energy": {
        "json_key": "batOtGridEgy",
        "name": "Battery to Grid Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:transmission-tower-export",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "grid_to_battery_energy": {
        "json_key": "ongridOtBatEgy",
        "name": "Grid to Battery Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:battery-arrow-up",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "ct_import_energy": {
        "json_key": "inCtEgy",
        "name": "CT Import Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:transmission-tower-import",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "ct_export_energy": {
        "json_key": "outCtEgy",
        "name": "CT Export Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:transmission-tower-export",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },
    "ac_to_grid_energy": {
        "json_key": "acOtOngridEgy",
        "name": "AC to Grid Energy",
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:transmission-tower-export",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "scale": 0.01,
    },

    # Wechselrichter-Stack — semantics unclear; do NOT use for energy balance calculations
    "stack_in_power": {
        "json_key": "stackInPw",
        "name": "Inverter Stack Input Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:lightning-bolt-circle",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "stack_out_power": {
        "json_key": "stackOutPw",
        "name": "Inverter Stack Output Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:lightning-bolt-circle",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },

    # BMS SOC (separat von Display-SOC batSoc)
    "bms_soc": {
        "json_key": "soc",
        "name": "BMS SOC",
        "unit": PERCENTAGE,
        "icon": "mdi:battery-heart",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
    },

    # Batteriestatus
    "battery_state": {
        "json_key": "batState",
        "name": "Battery State",
        "unit": None,
        "icon": "mdi:battery-heart-variant",
        "device_class": None,
        "state_class": None,
    },

    # Netzwerk-Status
    "ethernet_connected": {
        "json_key": "ethPort",
        "name": "Ethernet Connected",
        "unit": None,
        "icon": "mdi:ethernet",
        "device_class": None,
        "state_class": None,
    },
    "wifi_signal": {
        "json_key": "wsig",
        "name": "WiFi Signal",
        "unit": SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        "icon": "mdi:wifi",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "state_class": SensorStateClass.MEASUREMENT,
    },

    # Leistungsgrenzen (nur lesbar)
    "max_inverter_standby_power": {
        "json_key": "maxInvStdPw",
        "name": "Max Inverter Standby Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "max_grid_standby_power": {
        "json_key": "maxGridStdPw",
        "name": "Max Grid Standby Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:transmission-tower",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },

    # Netzwerk-Diagnostik
    "wifi_ssid": {
        "json_key": "wname",
        "name": "WiFi SSID",
        "unit": None,
        "icon": "mdi:wifi",
        "device_class": None,
        "state_class": None,
    },
    "ethernet_ip": {
        "json_key": "eip",
        "name": "Ethernet IP",
        "unit": None,
        "icon": "mdi:ip-network",
        "device_class": None,
        "state_class": None,
    },
    "wlan_ip": {
        "json_key": "wip",
        "name": "WLAN IP",
        "unit": None,
        "icon": "mdi:ip-network",
        "device_class": None,
        "state_class": None,
    },
    "device_capability": {
        "json_key": "ability",
        "name": "Device Capability",
        "unit": None,
        "icon": "mdi:chip",
        "device_class": None,
        "state_class": None,
    },
    # funcEnable bitmask (type-106). The individual bits are decoded into the
    # `func_enable_flags` attribute via FUNC_ENABLE_BITS.
    "func_enable": {
        "json_key": "funcEnable",
        "name": "Function Enable Flags",
        "unit": None,
        "icon": "mdi:tune-variant",
        "device_class": None,
        "state_class": None,
    },

    # Gerätestatus (type=2 / type=106) — ENUM sensors with readable labels (Ü5)
    "device_status": {
        "json_key": "stat",
        "name": "Device Status",
        "unit": None,
        "icon": "mdi:state-machine",
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "options": list(DEVICE_STATUS_MAP.values()),
        "value_map": DEVICE_STATUS_MAP,
    },
    "ongrid_status": {
        "json_key": "ongridStat",
        "name": "OnGrid Status",
        "unit": None,
        "icon": "mdi:transmission-tower",
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "options": list(ONGRID_STATUS_MAP.values()),
        "value_map": ONGRID_STATUS_MAP,
    },
    "ct_status": {
        "json_key": "ctStat",
        "name": "CT Status",
        "unit": None,
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "options": list(CT_STATUS_MAP.values()),
        "value_map": CT_STATUS_MAP,
    },
    "grid_meter_link": {
        "json_key": "gridSate",
        "name": "Grid Meter Link",
        "unit": None,
        "icon": "mdi:lan-connect",
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "options": list(GRID_METER_LINK_MAP.values()),
        "value_map": GRID_METER_LINK_MAP,
    },

    # Type-106 fields (response to type-105 poll, ~every 5 min)
    "other_load_power": {
        "json_key": "otherLoadPw",
        "name": "Home Load Power (Estimated)",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:home-lightning-bolt-outline",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_in_power": {
        "json_key": "gridInPw",
        "name": "Grid AC Input Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:transmission-tower-import",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_out_power": {
        "json_key": "gridOutPw",
        "name": "Grid AC Output Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:transmission-tower-export",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_side_in_power": {
        "json_key": "inGridSidePw",
        "name": "Grid Side Input Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:transmission-tower-import",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "grid_side_out_power": {
        "json_key": "outGridSidePw",
        "name": "Grid Side Output Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:transmission-tower-export",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "energy_plan_power": {
        "json_key": "energyPlanPw",
        "name": "Energy Plan Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:lightning-bolt-outline",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "standby_power": {
        "json_key": "standbyPw",
        "name": "Standby Power Threshold",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:power-sleep",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "pv_max_charge_power": {
        "json_key": "pvMaxChgPower",
        "name": "PV Max Charge Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:solar-power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "max_system_output_power": {
        "json_key": "maxSysOutPw",
        "name": "Max System Output Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "max_system_input_power": {
        "json_key": "maxSysInPw",
        "name": "Max System Input Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "off_grid_time": {
        "json_key": "offGridTime",
        "name": "Off-Grid Switch Time",
        "unit": UnitOfTime.SECONDS,
        "icon": "mdi:timer-outline",
        "device_class": None,
        "state_class": None,
    },
    # maxFeedGrid (type-106): enforced system-level grid feed-in cap. Read-back sensor for
    # the value reported by the device. Writable via Number entity in number.py (Issue #11).
    # Distinct from maxOutPw (user-selectable app limit, controlled via JackeryMaxFeedInSelect).
    "max_feed_grid_power": {
        "json_key": "maxFeedGrid",
        "name": "Max Feed Grid Power",
        "unit": UnitOfPower.WATT,
        "icon": "mdi:transmission-tower-export",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
    },
}

# 子设备传感器配置
SUBDEVICE_SENSORS = {
    # 智能插座 (devType=6 or 1)
    "plug": {
        "power": {
            "key": "outPw", # Fallback to 'power'
            "name": "Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:power-socket-eu",
        },
        "energy": {
            "key": "totalEgy",
            "name": "Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:lightning-bolt",
            "scale": 0.01,
        },
    },
    # CT / Smart Meter (devType=2, subType 1-4)
    "ct": {
        "power": {
            "key": "phasePw",
            "name": "Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:current-ac",
        },
        "energy": {
            "key": "phaseEgy",
            "name": "Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:lightning-bolt",
            "scale": 0.01,
        },
    },
    # SmartMeter 3P (devType=3, subType=5, model HTO907A)
    # xPhasePw  = Consumption / Grid Import per phase
    # xnPhasePw = Production  / Grid Export per phase
    "ct_3phase": {
        "import_total": {
            "key": "tPhasePw",
            "name": "Grid Import Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:transmission-tower-import",
        },
        "export_total": {
            "key": "tnPhasePw",
            "name": "Grid Export Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:transmission-tower-export",
        },
        "import_l1": {
            "key": "aPhasePw",
            "name": "L1 Import Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:current-ac",
        },
        "import_l2": {
            "key": "bPhasePw",
            "name": "L2 Import Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:current-ac",
        },
        "import_l3": {
            "key": "cPhasePw",
            "name": "L3 Import Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:current-ac",
        },
        "export_l1": {
            "key": "anPhasePw",
            "name": "L1 Export Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:current-ac",
        },
        "export_l2": {
            "key": "bnPhasePw",
            "name": "L2 Export Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:current-ac",
        },
        "export_l3": {
            "key": "cnPhasePw",
            "name": "L3 Export Power",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:current-ac",
        },
        "import_energy_total": {
            "key": "tPhaseEgy",
            "name": "Grid Import Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:transmission-tower-import",
            "scale": 0.01,
        },
        "export_energy_total": {
            "key": "tnPhaseEgy",
            "name": "Grid Export Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:transmission-tower-export",
            "scale": 0.01,
        },
        "import_energy_l1": {
            "key": "aPhaseEgy",
            "name": "L1 Import Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:lightning-bolt",
            "scale": 0.01,
        },
        "import_energy_l2": {
            "key": "bPhaseEgy",
            "name": "L2 Import Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:lightning-bolt",
            "scale": 0.01,
        },
        "import_energy_l3": {
            "key": "cPhaseEgy",
            "name": "L3 Import Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:lightning-bolt",
            "scale": 0.01,
        },
        "export_energy_l1": {
            "key": "anPhaseEgy",
            "name": "L1 Export Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:lightning-bolt",
            "scale": 0.01,
        },
        "export_energy_l2": {
            "key": "bnPhaseEgy",
            "name": "L2 Export Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:lightning-bolt",
            "scale": 0.01,
        },
        "export_energy_l3": {
            "key": "cnPhaseEgy",
            "name": "L3 Export Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:lightning-bolt",
            "scale": 0.01,
        },
        # Diagnostik-Sensoren
        "comm_mode": {
            "key": "commMode",
            "name": "Communication Mode",
            "unit": None,
            "device_class": SensorDeviceClass.ENUM,
            "state_class": None,
            "icon": "mdi:network",
            "options": ["lan", "cloud"],
            "options_offset": 1,  # commMode is 1-based: 1=LAN, 2=Cloud
        },
        "comm_state": {
            "key": "commState",
            "name": "Communication State",
            "unit": None,
            "device_class": SensorDeviceClass.ENUM,
            "state_class": None,
            "icon": "mdi:connection",
            "options": ["offline", "online"],
        },
        "ip_address": {
            "key": "wip",
            "name": "IP Address",
            "unit": None,
            "device_class": None,
            "state_class": None,
            "icon": "mdi:ip",
        },
    },
    # Meter Collector (devType=4, subType=7, model HTO910A "Smart Meter D0 Reader")
    # Optical D0 interface reader: sits on the IR port of a German electricity meter and reads
    # meter data via IEC 62056-21 / SML protocol. Reports totals from the meter — no per-phase
    # breakdown. Appears in the "collectors" array of type-101 messages (not "cts").
    # Fields confirmed from live MQTT capture (Issue #19, 2026-07-24):
    #   inPw  = total grid import power as reported by the meter (W)
    #   outPw = total grid export power as reported by the meter (W)
    "collector": {
        "import_power": {
            "key": "inPw",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:transmission-tower-import",
        },
        "export_power": {
            "key": "outPw",
            "unit": UnitOfPower.WATT,
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon": "mdi:transmission-tower-export",
        },
        "comm_state": {
            "key": "commState",
            "device_class": SensorDeviceClass.ENUM,
            "options": ["offline", "online"],
            "unit": None,
            "icon": "mdi:connection",
        },
        "comm_mode": {
            "key": "commMode",
            "device_class": SensorDeviceClass.ENUM,
            "options": ["lan", "cloud"],
            "options_offset": 1,  # commMode is 1-based: 1=LAN, 2=Cloud
            "unit": None,
            "icon": "mdi:lan",
        },
        "ip_address": {
            "key": "wip",
            "unit": None,
            "icon": "mdi:ip-network",
        },
    },
    # Expansion battery (e.g. BP2500, devType=1, subType=0)
    # Only cumulative energy is exposed via MQTT (type-23 messages). No real-time power.
    "expansion_battery": {
        "charge_energy": {
            "key": "inEgy",
            "name": "Charge Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:battery-arrow-up",
            "scale": 0.01,
        },
        "discharge_energy": {
            "key": "outEgy",
            "name": "Discharge Energy",
            "unit": UnitOfEnergy.KILO_WATT_HOUR,
            "device_class": SensorDeviceClass.ENERGY,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "icon": "mdi:battery-arrow-down",
            "scale": 0.01,
        },
    },
}

# devType values that identify CT/meter sub-devices (2=standard CT, 3=SmartMeter 3P, 4=Meter Collector)
CT_DEV_TYPES: frozenset[int] = frozenset({2, 3, 4})

# devType values that identify smart plugs
PLUG_ITEM_DEV_TYPES: frozenset[int] = frozenset({6})

# commMode constants for smart plugs
COMM_MODE_LOCAL = 1
COMM_MODE_CLOUD = 2

COMM_MODE_LABELS: dict[int, str] = {
    COMM_MODE_LOCAL: "local",
    COMM_MODE_CLOUD: "cloud",
}

# CT / meter subType → human readable hardware name (diagnostic attribute only)
CT_SUBTYPE_MAP: dict[int, str] = {
    1: "Shelly Single Phase",
    2: "Shelly Three Phase",
    3: "Shelly 63A",
    4: "Eastron Single Phase (4002)",
    5: "Eastron Three Phase (4003)",
    6: "Jackery Wireless Smart Meter (US L1/L2 4007)",
    7: "Jackery Smart Meter 3P (UK 4008)",
}

# funcEnable bitmask: bit index → feature name (1 = enabled, 0 = disabled).
# Exposed as attributes of the `func_enable` sensor.
FUNC_ENABLE_BITS: dict[int, str] = {
    0: "aerosol",            # bit0 aerosol
    1: "soc_calibration",    # bit1 SOC calibration
    2: "low_power",          # bit2 low power
    3: "soh_calibration",    # bit3 SOH calibration
    4: "pcs_comm_diag",      # bit4 PCS communication diagnosis
    5: "shutdown_2h",        # bit5 2h shutdown
    6: "fault_shutdown",     # bit6 fault shutdown
    7: "epo",                # bit7 EPO function
    8: "func_48v",           # bit8 48 V function
    9: "ethernet_debug",     # bit9 Ethernet debug function
    10: "energy_flow_fill",  # bit10 energy flow data backfill
    11: "smart_plug_first",  # bit11 smart plug priority
}

# Fields that identify a *flat* status message (payload without a type/body wrapper).
# If any of these appear at the top level, the message body is reconstructed from the
# remaining top-level keys (see _extract_flat_body).
_FLAT_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "batSoc",
        "soc",
        "pvPw",
        "stat",
        "workMode",
        "inOngridPw",
        "outOngridPw",
        "gridInPw",
        "gridOutPw",
        "inGridSidePw",
        "outGridSidePw",
        "swEpsInPw",
        "swEpsOutPw",
        "batInPw",
        "batOutPw",
        "otherLoadPw",
    }
)

# Top-level envelope keys that are never part of the payload body
_FLAT_META_KEYS: frozenset[str] = frozenset(
    {"type", "eventId", "messageId", "ts", "deviceType", "token", "softver", "body"}
)

# Real-time power fields shared between type-2 (~11 s) and type-106 (~30 s).
# type-2 is more current; once the cache has a type-2 reading for these keys,
# the snapshot values from a type-106 poll must not overwrite them.
# At startup (empty cache) type-106 is still allowed to populate them so the
# initial state is available for the ~11 s before the first type-2 arrives.
_TYPE106_SKIP_IF_ESTABLISHED: frozenset[str] = frozenset({
    "batInPw", "batOutPw",
    "pvPw", "pv1", "pv2", "pv3", "pv4",
    "swEpsInPw", "swEpsOutPw",
    "stackInPw", "stackOutPw",
})


def plug_comm_mode(item: dict) -> int | None:
    """Read plug commMode (1=local, 2=cloud)."""
    val = item.get("commMode")
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def plug_mqtt_control_allowed(item: dict) -> tuple[bool, str]:
    """Check if MQTT control is allowed for plug; returns (allowed, reason)."""
    mode = plug_comm_mode(item)
    if mode == COMM_MODE_LOCAL:
        return True, ""
    if mode == COMM_MODE_CLOUD:
        return (
            False,
            "Smart plug is cloud-connected (commMode=2) and cannot be controlled via MQTT. Please use the Jackery App.",
        )
    if mode is None:
        return (
            False,
            "Unknown commMode. MQTT control is only supported when commMode=1 (local).",
        )
    return (
        False,
        f"Smart plug commMode={mode} does not support MQTT control. Only commMode=1 (local) is supported.",
    )


def should_create_plug_switch(item: dict) -> bool:
    """Only create switch entities for smart plugs (devType=6)."""
    return item.get("devType") in PLUG_ITEM_DEV_TYPES


def _subdevice_sn(item: dict) -> str | None:
    """Extract device serial number from a sub-device dict (Ü7)."""
    return item.get("deviceSn") or item.get("sn")


def _merge_subdevice_list(
    existing: list[dict] | None,
    new_items: list[dict],
) -> list[dict]:
    """Merge sub-device entries by deviceSn/sn, preserving fields not present in new_items.

    Instead of replacing the whole list on every message, each device is identified by its
    serial number and new fields are merged on top of the existing entry.  Fields that are
    present in the cache but absent from the current message are kept intact.
    """
    merged: dict[str, dict] = {}
    for item in (existing or []) + new_items:
        if not isinstance(item, dict):
            continue
        sn = item.get("deviceSn") or item.get("sn")
        if not sn:
            continue
        merged[sn] = {**merged.get(sn, {}), **item}
    return list(merged.values())


def _field_present(data: dict, key: str) -> bool:
    """Return True if `key` exists in `data` and is not None (0 is a valid reading)."""
    return key in data and data[key] is not None


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert an MQTT field to float, falling back to `default` on None/garbage."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick_best_power_net(candidates: list[float]) -> float:
    """Pick the non-zero candidate with the largest magnitude.

    A device may report the same physical quantity through several fields
    (type-2 vs. type-106).  A field that is present but reports 0 must not
    mask a field that carries an actual reading, so the largest magnitude wins.
    If every candidate is 0 the last one is returned (still a valid "no flow").
    """
    if not candidates:
        return 0.0
    non_zero = [v for v in candidates if abs(v) > 0]
    if non_zero:
        return max(non_zero, key=abs)
    return candidates[-1]


def _effective_ongrid_net(
    data: dict,
    grid_in: float,
    grid_out: float,
    ongrid_charge: float,
    ongrid_supply: float,
    in_grid_side: float,
    out_grid_side: float,
) -> float:
    """Net power at the grid-tied port (positive = grid → unit).

    Multi-source: `gridInPw/gridOutPw` (type-106), `inOngridPw/outOngridPw` (type-2)
    and `inGridSidePw/outGridSidePw` all describe the same port on different firmware
    revisions.  Only sources actually present in the payload are considered.
    """
    candidates: list[float] = []
    if _field_present(data, "gridInPw") or _field_present(data, "gridOutPw"):
        candidates.append(grid_in - grid_out)
    if _field_present(data, "inOngridPw") or _field_present(data, "outOngridPw"):
        candidates.append(ongrid_charge - ongrid_supply)
    if _field_present(data, "inGridSidePw") or _field_present(data, "outGridSidePw"):
        candidates.append(in_grid_side - out_grid_side)
    return _pick_best_power_net(candidates)


def _grid_net_from_system(
    data: dict,
    grid_in: float,
    grid_out: float,
    ongrid_charge: float,
    ongrid_supply: float,
    in_grid_side: float,
    out_grid_side: float,
    *,
    include_ongrid: bool = True,
) -> tuple[float, bool]:
    """Derive net grid power from device-reported fields when no CT/meter is available.

    Returns `(net_power, available)`; positive = import from grid.

    `include_ongrid` controls whether `inOngridPw/outOngridPw` may act as the grid
    reading.  This fork calls it with `include_ongrid=False`: those two fields are
    already used to compute `p_ong`, so accepting them as the "grid meter" would make
    `p_home = p_grid - p_ong` collapse to 0 and destroy the AC-output fallback
    (`p_home = outOngridPw`) used on installations without a meter.
    """
    candidates: list[float] = []
    if _field_present(data, "inGridSidePw") or _field_present(data, "outGridSidePw"):
        candidates.append(in_grid_side - out_grid_side)
    if _field_present(data, "gridInPw") or _field_present(data, "gridOutPw"):
        candidates.append(grid_in - grid_out)
    if include_ongrid and (
        _field_present(data, "inOngridPw") or _field_present(data, "outOngridPw")
    ):
        candidates.append(ongrid_charge - ongrid_supply)
    if not candidates:
        return 0.0, False
    return _pick_best_power_net(candidates), True


def _normalize_payload_fields(payload: dict) -> dict:
    """Normalize MQTT field aliases before merging a payload into the cache.

    - `gridBuyPw`  → `gridInPw`
    - `gridSellPw` → `gridOutPw`
    - `workModel`  (type-106) → `workMode` (type-107 / our sensor key)

    Existing keys are never overwritten, so an explicit value always wins over its alias.
    """
    result = dict(payload)

    if result.get("gridInPw") is None and result.get("gridBuyPw") is not None:
        result["gridInPw"] = result["gridBuyPw"]
    if result.get("gridOutPw") is None and result.get("gridSellPw") is not None:
        result["gridOutPw"] = result["gridSellPw"]
    if result.get("workMode") is None and result.get("workModel") is not None:
        result["workMode"] = result["workModel"]

    return result


def _extract_flat_body(raw_data: dict) -> dict:
    """Reconstruct a body dict from a flat status message (no `body` wrapper).

    Returns an empty dict when the payload does not look like device status data.
    """
    if not any(key in raw_data for key in _FLAT_PAYLOAD_KEYS):
        return {}
    return {key: value for key, value in raw_data.items() if key not in _FLAT_META_KEYS}


class JackeryDataCoordinator:
    """协调器：管理MQTT订阅和数据获取，供所有传感器实体共享使用."""

    def __init__(self, hass: HomeAssistant, topic_prefix: str, token: str, mqtt_host: str, device_sn: str) -> None:
        self.hass = hass
        self._topic_prefix = topic_prefix
        self._token = token
        self._mqtt_host = mqtt_host
        self._device_sn = device_sn
        self._topic_root = topic_prefix

        self._sensors: dict[str, Any] = {}
        self._data_task: asyncio.Task[None] | None = None
        self._subscribed = False
        self._last_update_time = time.time()
        self._start_time = time.time()

        self._known_plugs: set[str] = set()
        self._subdevice_missing_since: dict[str, float] = {}
        self._subdevice_last_seen: dict[str, float] = {}
        self._expansion_battery_sns: set[str] = set()
        self._poll_105_counter: int = 2  # starts at threshold-1 so type-105 fires on first cycle
        self.add_entities_callback: Any = None
        self.add_switch_entities_callback: Any = None
        self._data_cache: dict[str, Any] = {}

        # Device meta — populated from first MQTT message, used to update device registry (Ü2/Ü3)
        self._device_type: int | None = None
        self._soft_ver: str | None = None

        # Re-Auth guard — prevents multiple simultaneous re-auth flows
        self._reauth_started: bool = False
        # True as soon as one valid message for this device SN was received (re-auth heuristic)
        self._ever_received: bool = False
        self.config_entry_id: str = ""  # set by async_setup_entry

        self._topic_status_wildcard = f"{self._topic_root}/device/+/status"
        self._topic_event_wildcard = f"{self._topic_root}/device/+/event"

    def register_sensor(self, sensor_id: str, entity: Any) -> None:
        """Register any HA entity that implements _update_from_coordinator."""
        self._sensors[sensor_id] = entity

    def unregister_sensor(self, sensor_id: str) -> None:
        """注销传感器实体."""
        if sensor_id in self._sensors:
            del self._sensors[sensor_id]

    async def async_start(self) -> None:
        """启动协调器."""
        if self._subscribed:
            return

        try:
            # 订阅状态主题 (Wildcard) 以发现设备和接收数据
            @callback
            def message_received(msg):
                self._handle_message(msg)

            await ha_mqtt.async_subscribe(
                self.hass,
                self._topic_status_wildcard,
                message_received,
                1
            )
            _LOGGER.info(f"Coordinator subscribed to: {self._topic_status_wildcard}")

            # Subscribe to event topic for sub-device data (Type 101)
            await ha_mqtt.async_subscribe(
                self.hass,
                self._topic_event_wildcard,
                message_received,
                1
            )
            _LOGGER.info(f"Coordinator subscribed to: {self._topic_event_wildcard}")

            self._subscribed = True

            # 启动定时轮询
            self._data_task = asyncio.create_task(self._periodic_data_request())

        except Exception as e:
            _LOGGER.error(f"Failed to start coordinator: {e}")

    async def async_stop(self) -> None:
        """停止协调器."""
        if self._data_task and not self._data_task.done():
            self._data_task.cancel()
            try:
                await self._data_task
            except asyncio.CancelledError:
                pass
        _LOGGER.info("Coordinator stopped")

    def _handle_message(self, msg) -> None:
        """处理接收到的 MQTT 消息."""
        self._last_update_time = time.time()
        try:
            topic = msg.topic
            payload = msg.payload
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")

            # Extract device SN from topic: {prefix}/device/{sn}/status OR .../event
            match = re.search(rf"{self._topic_root}/device/([^/]+)/(status|event)", topic)
            if match:
                sn = match.group(1)
                if not self._device_sn:
                    self._device_sn = sn
                    _LOGGER.info(f"Discovered device SN: {self._device_sn}")
                elif self._device_sn != sn:
                    # Ü1: ignore messages from other devices on the same broker
                    _LOGGER.debug(f"Ignoring data from another device: {sn}")
                    return

            # A valid message for our device arrived → token is accepted, no re-auth needed
            self._ever_received = True

            # Parse Payload
            try:
                raw_data = json.loads(payload)
                msg_code = raw_data.get("type")
                body = raw_data.get("body")

                # No `body` wrapper: some firmware revisions send a flat status payload
                # with all fields at the top level. Reconstruct the body from those.
                if body is None:
                     # If Type 101 and body is None, ignore.
                     if msg_code == 101:
                         return
                     flat_body = _extract_flat_body(raw_data)
                     body = flat_body if flat_body else {}

                # Capture device model/firmware from first message (Ü2)
                if isinstance(body, dict):
                    self._capture_device_meta(raw_data, body)

                # Merge logic
                # Type 23: Statistical/Energy Data
                if msg_code == 23 and isinstance(body, dict):
                    device_sn_in_body = body.get("deviceSn")
                    dev_type_in_body = body.get("devType")
                    if device_sn_in_body == "system" or device_sn_in_body is None:
                        # Merge into main device cache
                        self._merge_normalized_cache(body)
                    elif dev_type_in_body == 1:
                        # Expansion battery (e.g. BP2500) — not in type-101, store separately
                        exp_bats = self._data_cache.setdefault("expansion_batteries", {})
                        if device_sn_in_body not in exp_bats:
                            exp_bats[device_sn_in_body] = {}
                        # Only update with non-null values to preserve previously cached real data.
                        # Devices occasionally send null for energy fields (e.g. during a restart);
                        # overwriting with null would cause sensors to show "unknown" until the
                        # next type-23 arrives (~10 min later).
                        for k, v in body.items():
                            if v is not None:
                                exp_bats[device_sn_in_body][k] = v
                        # Update last_seen so offline detection doesn't mark them unavailable
                        self._subdevice_last_seen[device_sn_in_body] = time.time()
                        self._check_for_new_expansion_batteries()
                    else:
                        # Find and update sub-device in cache (CTs, SmartMeter)
                        for key in ["plugs", "plug", "cts"]:
                            items = self._data_cache.get(key)
                            if isinstance(items, list):
                                for item in items:
                                    if item.get("sn") == device_sn_in_body or item.get("deviceSn") == device_sn_in_body:
                                        item.update(body)
                                        break

                # Type 101: Sub-device full data
                elif msg_code == 101 and isinstance(body, dict):
                    self._merge_subdevice_arrays(body)

                # Type 102: Sub-device incremental / point updates
                # (plug switchSta/outPw, CT phase power, …). Not observed on the
                # SolarVault 3 Pro Max, but sent by newer firmware / other models.
                elif msg_code == 102 and isinstance(body, dict):
                    if not self._merge_subdevice_arrays(body):
                        self._merge_subdevice_point_update(body)

                # Type 106: Full system state (response to type-105 poll)
                elif msg_code == 106 and isinstance(body, dict):
                    # Settings (workMode, maxFeedGrid, …): always update.
                    # Real-time power fields: only populate if not already established
                    # by a fresher type-2 message — prevents 30 s-stale snapshots
                    # from overwriting live readings (see _TYPE106_SKIP_IF_ESTABLISHED).
                    normalized = _normalize_payload_fields(body)
                    for k, v in normalized.items():
                        if k not in _TYPE106_SKIP_IF_ESTABLISHED or k not in self._data_cache:
                            self._data_cache[k] = v
                    _LOGGER.debug("Received type-106 system state (%d fields)", len(body))

                # Type 107: Incremental system update (soc, workMode, …)
                elif msg_code == 107 and isinstance(body, dict):
                    self._merge_normalized_cache(body)
                    _LOGGER.debug("Received type-107 incremental update: %s", body)

                # Type 123: Auth error from device
                elif msg_code == 123 and isinstance(body, dict):
                    error_code = body.get("errorCode")
                    if error_code == 401:
                        self._trigger_reauth("device reported token mismatch (type-123/401)")

                # Type 25 or Status: Main device data
                elif isinstance(body, dict):
                    # Merge top-level keys into cache to preserve fields not present in current message
                    self._merge_normalized_cache(body)

            except json.JSONDecodeError:
                _LOGGER.warning(f"Invalid JSON payload on {topic}")
                return

            # Enrich data with calculations using merged cache
            # operate on copy or direct? Direct is fine.
            self._data_cache = self._calculate_energy_flow(self._data_cache)

            # Check for new plugs
            self._check_for_new_plugs(self._data_cache)

            self._distribute_data(self._data_cache)

        except Exception as e:
            _LOGGER.error(f"Error handling message: {e}")

    def _merge_normalized_cache(self, payload: dict) -> None:
        """Normalize field aliases and merge a main-device payload into the cache."""
        self._data_cache.update(_normalize_payload_fields(payload))

    def _merge_subdevice_arrays(self, body: dict) -> bool:
        """Merge plugs/cts/collectors arrays from a body into the cache.

        Each section is merged independently by deviceSn so that:
        - A plug poll response (no "cts" key) never wipes the CT cache (issue #16)
        - Partial updates preserve fields not present in the current message

        Returns True if at least one array was merged.
        """
        raw_plugs = (
            body.get("plug") or body.get("plugs")
            or body.get("socket") or body.get("sockets")
        )
        raw_cts = body.get("ct") or body.get("cts")
        raw_collectors = body.get("collectors")

        now_ts = time.time()
        updated = False

        if isinstance(raw_plugs, list) and raw_plugs:
            new_plugs = []
            for item in raw_plugs:
                if not isinstance(item, dict):
                    continue
                if item.get("devType") is None:
                    item = {**item, "devType": 6}
                new_plugs.append(item)
                sn = _subdevice_sn(item)
                if sn:
                    self._subdevice_last_seen[sn] = now_ts
            self._data_cache["plugs"] = _merge_subdevice_list(
                self._data_cache.get("plugs"), new_plugs
            )
            self._data_cache["plug"] = self._data_cache["plugs"]
            updated = True

        if isinstance(raw_cts, list) and raw_cts:
            new_cts = []
            for item in raw_cts:
                if not isinstance(item, dict):
                    continue
                if item.get("devType") is None:
                    item = {**item, "devType": 2}
                new_cts.append(item)
                sn = _subdevice_sn(item)
                if sn:
                    self._subdevice_last_seen[sn] = now_ts
            self._data_cache["cts"] = _merge_subdevice_list(
                self._data_cache.get("cts"), new_cts
            )
            updated = True

        # Meter Collectors (HTO910A, devType=4, subType=7): appear under "collectors"
        # key in type-101 devType=2 responses, not under "cts".
        if isinstance(raw_collectors, list) and raw_collectors:
            new_collectors = []
            for item in raw_collectors:
                if not isinstance(item, dict):
                    continue
                new_collectors.append(item)
                sn = _subdevice_sn(item)
                if sn:
                    self._subdevice_last_seen[sn] = now_ts
            self._data_cache["collectors"] = _merge_subdevice_list(
                self._data_cache.get("collectors"), new_collectors
            )
            updated = True

        return updated

    def _merge_subdevice_point_update(self, body: dict) -> bool:
        """Merge a single sub-device point update (type-102) into the cache.

        The body describes one sub-device directly (no wrapping array).  If the SN is
        already cached the entry is patched in place, otherwise the device is classified
        by devType and appended to the matching section.
        """
        sn = _subdevice_sn(body)
        if not sn or sn == self._device_sn or sn == "system":
            return False

        self._subdevice_last_seen[sn] = time.time()

        # 1. Known device → patch in place (skip null values, they carry no information)
        for key in ("plugs", "plug", "cts", "collectors"):
            items = self._data_cache.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and _subdevice_sn(item) == sn:
                    item.update({k: v for k, v in body.items() if v is not None})
                    return True

        # 2. New device → classify by devType, inferring it from the fields if absent
        entry = dict(body)
        dev_type = entry.get("devType")
        if dev_type is None:
            if any(k in body for k in ("switchSta", "sysSwitch", "totalEgy")):
                dev_type = 6
            elif any(k in body for k in ("aPhasePw", "AphasePw", "tPhasePw", "TphasePw", "phasePw")):
                dev_type = 3
            if dev_type is not None:
                entry["devType"] = dev_type

        if dev_type in PLUG_ITEM_DEV_TYPES:
            self._data_cache["plugs"] = _merge_subdevice_list(
                self._data_cache.get("plugs"), [entry]
            )
            self._data_cache["plug"] = self._data_cache["plugs"]
            return True
        if dev_type in CT_DEV_TYPES:
            key = "collectors" if (dev_type == 4 and entry.get("subType") == 7) else "cts"
            self._data_cache[key] = _merge_subdevice_list(
                self._data_cache.get(key), [entry]
            )
            return True
        return False

    def _capture_device_meta(self, raw_data: dict, body: dict) -> None:
        """Extract deviceType and firmware version from MQTT payload to update HA device registry (Ü2)."""
        changed = False
        device_type = raw_data.get("deviceType")
        if device_type is not None and self._device_type is None:
            self._device_type = int(device_type)
            changed = True
        soft_ver = body.get("softver")
        if soft_ver is not None and soft_ver != self._soft_ver:
            self._soft_ver = str(soft_ver)
            changed = True
        if changed:
            asyncio.create_task(self._update_device_registry())

    async def _update_device_registry(self) -> None:
        """Update HA device registry with model name and firmware version (Ü3)."""
        from homeassistant.helpers import device_registry as dr
        registry = dr.async_get(self.hass)
        model = DEVICE_TYPE_MODEL_MAP.get(self._device_type or 0, DEFAULT_MODEL)
        identifier = self._device_sn or self.config_entry_id
        device = registry.async_get_device(identifiers={(DOMAIN, identifier)})
        if device:
            registry.async_update_device(device.id, model=model, sw_version=self._soft_ver)
            _LOGGER.debug("Device registry updated: model=%s sw_version=%s", model, self._soft_ver)

    def _trigger_reauth(self, reason: str) -> None:
        """Initiate a re-authentication flow in HA (Re-Auth feature)."""
        if self._reauth_started:
            return
        self._reauth_started = True
        _LOGGER.warning("Triggering re-authentication: %s", reason)
        from homeassistant.config_entries import SOURCE_REAUTH
        self.hass.async_create_task(
            self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_REAUTH, "entry_id": self.config_entry_id},
                data={},
            )
        )

    def _entity_keys_for_subdevice(self, sn: str) -> list[str]:
        """Return all registered entity keys (unique_ids) belonging to a sub-device SN."""
        return [
            sensor_id
            for sensor_id in self._sensors
            if f"_{sn}_" in sensor_id or sensor_id.endswith(f"_{sn}")
        ]

    def _remove_subdevice_from_ha(self, sn: str) -> None:
        """Remove an unbound sub-device and all its entities from Home Assistant.

        Removing the *device* from the registry removes all of its entities in one go
        and also drops the (now orphaned) device card — cleaner than calling
        `async_remove(force_remove=True)` on every entity individually, which left the
        empty device behind.
        """
        try:
            from homeassistant.helpers import device_registry as dr
            dev_reg = dr.async_get(self.hass)
            # Identifier must match JackerySubDeviceSensor._attr_device_info
            device = dev_reg.async_get_device(identifiers={(DOMAIN, f"sub_{sn}")})
            if device is not None:
                dev_reg.async_remove_device(device.id)
                _LOGGER.info("Sub-device %s unbound — removed from HA device registry.", sn)
        except Exception as err:  # registry not available (e.g. during teardown/tests)
            _LOGGER.warning("Could not remove sub-device %s from device registry: %s", sn, err)

        # Drop all in-memory references so the device can be re-discovered cleanly
        self._known_plugs.discard(sn)
        self._expansion_battery_sns.discard(sn)
        self._subdevice_missing_since.pop(sn, None)
        self._subdevice_last_seen.pop(sn, None)
        for sensor_id in self._entity_keys_for_subdevice(sn):
            self.unregister_sensor(sensor_id)

    def _check_for_new_plugs(self, data: dict) -> None:
        """Check and sync plugs/CTs/collectors (add new, remove old)."""
        all_devices = []
        for key in ("plugs", "plug", "cts", "collectors"):
            items = data.get(key)
            if isinstance(items, list):
                all_devices.extend(items)

        if not all_devices:
            return

        current_sns = set()
        for plug in all_devices:
            sn = plug.get("deviceSn") or plug.get("sn")
            if sn:
                current_sns.add(sn)

        now = time.time()

        # 0. Update sub-device availability based on last_seen timestamps
        for sn in self._known_plugs:
            last_seen = self._subdevice_last_seen.get(sn, 0)
            # During the first 60s after start, don't mark offline (device might not have reported yet)
            if last_seen == 0 and (now - self._start_time) < OFFLINE_TIMEOUT:
                continue
            # Expansion batteries report cumulative energy via type-23 (~10 min cadence).
            # Once data has been received (last_seen > 0), keep available indefinitely —
            # the value is still valid between updates. Only go unavailable if never seen.
            if sn in self._expansion_battery_sns:
                is_available = last_seen > 0
            else:
                is_available = last_seen > 0 and (now - last_seen) <= OFFLINE_TIMEOUT
            for sensor_id in self._entity_keys_for_subdevice(sn):
                entity = self._sensors.get(sensor_id)
                if entity is None or entity.available == is_available:
                    continue
                entity._attr_available = is_available
                entity.async_write_ha_state()
                if not is_available:
                    _LOGGER.debug("Sub-device %s offline (last seen %.0fs ago)", sn, now - last_seen)

        # 1. 更新 missing 状态
        for sn in current_sns:
            if sn in self._subdevice_missing_since:
                _LOGGER.info(f"Sub-device {sn} reappeared, cancelling deletion.")
                del self._subdevice_missing_since[sn]

        for sn in self._known_plugs:
            if sn in self._expansion_battery_sns:
                continue  # expansion batteries appear in type-23, not type-101 — never subject to deletion timer
            if sn not in current_sns:
                if sn not in self._subdevice_missing_since:
                    self._subdevice_missing_since[sn] = now
                    _LOGGER.info(f"Sub-device {sn} missing, starting {OFFLINE_TIMEOUT}s deletion timer...")

        # 2. 执行真正的移除
        for sn in list(self._subdevice_missing_since.keys()):
            if sn not in self._known_plugs:
                del self._subdevice_missing_since[sn]
                continue
            if sn in self._expansion_battery_sns:
                del self._subdevice_missing_since[sn]
                continue
            if sn in current_sns:
                del self._subdevice_missing_since[sn]
                continue

            missing_time = self._subdevice_missing_since[sn]
            if now - missing_time > OFFLINE_TIMEOUT:
                _LOGGER.info(f"Sub-device {sn} missing for >{OFFLINE_TIMEOUT}s. Removing.")
                self._remove_subdevice_from_ha(sn)

        # 3. Add newly discovered devices
        new_entities = []
        new_switch_entities = []
        for plug in all_devices:
            sn = plug.get("deviceSn") or plug.get("sn")
            dev_type = plug.get("devType")
            sub_type = plug.get("subType")
            if dev_type is None and sub_type == 2:
                dev_type = 2

            if sn and sn not in self._known_plugs:
                _LOGGER.info(f"Discovered new sub-device: {sn} (devType={dev_type}, subType={sub_type})")
                self._known_plugs.add(sn)

                if hasattr(self, "config_entry_id"):
                    # Determine sensor group and data source key
                    is_collector = dev_type == 4 and sub_type == 7
                    is_ct = dev_type in CT_DEV_TYPES and not is_collector
                    if is_collector:
                        sensor_group = "collector"
                        data_key = "collectors"
                    elif is_ct:
                        sensor_group = "ct_3phase" if (dev_type == 3 and sub_type == 5) else "ct"
                        data_key = "cts"
                    else:
                        sensor_group = "plug"
                        data_key = "plugs"

                    group_config = SUBDEVICE_SENSORS.get(sensor_group, {})
                    for sensor_key, sensor_cfg in group_config.items():
                        entity = JackerySubDeviceSensor(
                            plug_sn=sn,
                            dev_type=dev_type,
                            sensor_key=sensor_key,
                            sensor_config=sensor_cfg,
                            coordinator=self,
                            config_entry_id=self.config_entry_id,
                            data_key=data_key,
                            sensor_group=sensor_group,
                        )
                        new_entities.append(entity)

                    if not is_ct and not is_collector:
                        from .switch import JackeryPlugSwitch
                        switch_entity = JackeryPlugSwitch(
                            plug_sn=sn,
                            dev_type=dev_type,
                            coordinator=self,
                            config_entry_id=self.config_entry_id
                        )
                        new_switch_entities.append(switch_entity)

        if new_entities and self.add_entities_callback:
            self.add_entities_callback(new_entities)
        if new_switch_entities and self.add_switch_entities_callback:
            self.add_switch_entities_callback(new_switch_entities)

    def _check_for_new_expansion_batteries(self) -> None:
        """Create sensors for expansion batteries discovered via type-23 messages."""
        exp_bats = self._data_cache.get("expansion_batteries")
        if not exp_bats or not hasattr(self, "config_entry_id"):
            return
        new_entities = []
        for sn in exp_bats:
            if sn not in self._known_plugs:
                self._known_plugs.add(sn)
                self._expansion_battery_sns.add(sn)
                _LOGGER.info(f"Discovered expansion battery: {sn}")
                group_config = SUBDEVICE_SENSORS.get("expansion_battery", {})
                exp_data = exp_bats.get(sn, {})
                for sensor_key, sensor_cfg in group_config.items():
                    entity = JackerySubDeviceSensor(
                        plug_sn=sn,
                        dev_type=1,
                        sensor_key=sensor_key,
                        sensor_config=sensor_cfg,
                        coordinator=self,
                        config_entry_id=self.config_entry_id,
                        use_expansion=True,
                        sensor_group="expansion_battery",
                    )
                    # Pre-initialize value so the entity shows the correct reading immediately
                    # when added to HA rather than briefly showing "unknown" (null in charts).
                    pre_val = exp_data.get(sensor_cfg.get("key"))
                    if pre_val is not None:
                        try:
                            entity._attr_native_value = float(pre_val) * sensor_cfg.get("scale", 1)
                        except (TypeError, ValueError):
                            entity._attr_available = False
                    else:
                        entity._attr_available = False
                    new_entities.append(entity)
        if new_entities and self.add_entities_callback:
            self.add_entities_callback(new_entities)

    def get_subdevices(self) -> list[dict[str, Any]]:
        """Return latest sub-device list from cache."""
        plugs = self._data_cache.get("plugs") or self._data_cache.get("plug")
        if isinstance(plugs, list):
            return [p for p in plugs if isinstance(p, dict)]
        cts = self._data_cache.get("cts")
        if isinstance(cts, list):
            return [p for p in cts if isinstance(p, dict)]
        return []

    def get_plug_item(self, plug_sn: str) -> dict[str, Any] | None:
        """Return cached plug item by SN, or None if not found."""
        plugs = self._data_cache.get("plugs") or self._data_cache.get("plug")
        if not isinstance(plugs, list):
            return None
        return next(
            (
                p for p in plugs
                if isinstance(p, dict) and (p.get("deviceSn") == plug_sn or p.get("sn") == plug_sn)
            ),
            None,
        )

    async def async_control_subdevice_switch(self, plug_sn: str, dev_type: int, is_on: bool) -> None:
        """Control sub-device switch via type 103."""
        if not self._device_sn:
            _LOGGER.warning("Cannot control sub-device: device SN not discovered")
            return

        action_topic = f"{self._topic_root}/device/{self._device_sn}/action"
        ts = int(time.time())
        payload = {
            "type": 103,
            "eventId": 0,
            "messageId": random.randint(1000, 9999),
            "ts": ts,
            "body": {
                "deviceSn": plug_sn,
                "devType": dev_type,
                "sysSwitch": 1 if is_on else 0,
            },
        }
        if self._token:
            payload["token"] = self._token

        await ha_mqtt.async_publish(
            self.hass,
            action_topic,
            json.dumps(payload),
            0,
            False
        )

    async def async_control_main_device(self, params: dict[str, Any]) -> None:
        """Control main device via type 1, cmd 5."""
        if not self._device_sn:
            _LOGGER.warning("Cannot control main device: device SN not discovered")
            return

        action_topic = f"{self._topic_root}/device/{self._device_sn}/action"
        ts = int(time.time())
        body = {"cmd": 5, "rc": 1}
        body.update(params)
        payload = {
            "type": 1,
            "eventId": 3,
            "messageId": random.randint(1000, 9999),
            "ts": ts,
            "body": body,
        }
        if self._token:
            payload["token"] = self._token

        await ha_mqtt.async_publish(
            self.hass,
            action_topic,
            json.dumps(payload),
            0,
            False
        )

    def _calculate_energy_flow(self, data: dict) -> dict:
        """Compute the derived energy-flow values from the merged cache.

        Sources, in priority order:
        - PV:      `pvPw` (scalar or dict)
        - Ongrid:  `_effective_ongrid_net()` over gridInPw/gridOutPw, inOngridPw/outOngridPw
                   and inGridSidePw/outGridSidePw (positive = grid → unit)
        - ACSocket: `swEpsInPw` / `swEpsOutPw`
        - Grid:    CT (`cts`) → Meter Collector (`collectors`) → `_grid_net_from_system()`
        - Battery: `batInPw`/`batOutPw` when reported, else the estimate pv + p_ac + p_ong
        - Home:    p_grid − p_ong (clamped to ≥ 0), else the unit's net AC output
        """
        try:
            # 0. Normalize field aliases (gridBuyPw→gridInPw, gridSellPw→gridOutPw,
            #    workModel→workMode) so the multi-source helpers see canonical keys.
            data.update(_normalize_payload_fields(data))

            # 1. PV
            # Handle dict for PV if necessary (copied from sensor logic)
            pv_val = data.get("pvPw", 0)
            if isinstance(pv_val, dict):
                pv = _safe_float(pv_val.get("pvPw") or pv_val.get("w") or pv_val.get("power"))
            else:
                pv = _safe_float(pv_val)

            # 2. Ongrid — net power at the grid-tied port, multi-source so that a
            #    type-106 zero cannot mask a live type-2 reading (and vice versa).
            grid_in = _safe_float(data.get("gridInPw"))
            grid_out = _safe_float(data.get("gridOutPw"))
            ongrid_charge = _safe_float(data.get("inOngridPw"))
            ongrid_supply = _safe_float(data.get("outOngridPw"))
            in_grid_side = _safe_float(data.get("inGridSidePw"))
            out_grid_side = _safe_float(data.get("outGridSidePw"))
            p_ong = _effective_ongrid_net(  # 流入主机为正
                data,
                grid_in,
                grid_out,
                ongrid_charge,
                ongrid_supply,
                in_grid_side,
                out_grid_side,
            )

            # 3. ACSocket (EPS)
            ac_in = _safe_float(data.get("swEpsInPw"))
            ac_out = _safe_float(data.get("swEpsOutPw"))
            p_ac = ac_in - ac_out # 流入主机为正

            # 4. Grid (Meter)
            # 优先从 'cts' 数组中提取 CT 数据 (Smart CT Meter)
            # cts item: { ..., "TphasePw": <Import>, "TnphasePw": <Export>, "commState": 1/0, ... }
            grid_available = False
            grid_buy = 0.0
            grid_sell = 0.0

            cts = data.get("cts")
            if cts and isinstance(cts, list) and len(cts) > 0:
                # 尝试获取第一个 CT 数据
                ct_data = cts[0]
                # 检查通讯状态 (如果 commState 存在且为 0 可能表示离线，视具体协议而定，这里暂定只要有数据即可)
                # TphasePw: 总正向有功 (Grid Buy)
                # TnphasePw: 总负向有功 (Grid Sell)
                t_phase_pw = ct_data.get("TphasePw") or ct_data.get("tPhasePw")
                tn_phase_pw = ct_data.get("TnphasePw") or ct_data.get("tnPhasePw")

                # Fallback: if total phase missing, sum A/B/C
                if t_phase_pw is None:
                    a_pw = ct_data.get("AphasePw") or ct_data.get("aPhasePw") or 0
                    b_pw = ct_data.get("BphasePw") or ct_data.get("bPhasePw") or 0
                    c_pw = ct_data.get("CphasePw") or ct_data.get("cPhasePw") or 0
                    if any(v is not None for v in [a_pw, b_pw, c_pw]):
                        t_phase_pw = float(a_pw) + float(b_pw) + float(c_pw)

                if tn_phase_pw is None:
                    an_pw = ct_data.get("AnphasePw") or ct_data.get("anPhasePw") or 0
                    bn_pw = ct_data.get("BnphasePw") or ct_data.get("bnPhasePw") or 0
                    cn_pw = ct_data.get("CnphasePw") or ct_data.get("cnPhasePw") or 0
                    if any(v is not None for v in [an_pw, bn_pw, cn_pw]):
                        tn_phase_pw = float(an_pw) + float(bn_pw) + float(cn_pw)

                if t_phase_pw is not None or tn_phase_pw is not None:
                    grid_buy = float(t_phase_pw or 0)
                    grid_sell = float(tn_phase_pw or 0)
                    grid_available = True

            # Fallback 1: Meter Collector (HTO910A, devType=4, subType=7)
            # Appears in data_cache["collectors"]; fields inPw/outPw are direct W values.
            if not grid_available:
                collectors = data.get("collectors")
                if collectors and isinstance(collectors, list):
                    for collector in collectors:
                        if not isinstance(collector, dict):
                            continue
                        in_pw = collector.get("inPw")
                        out_pw = collector.get("outPw")
                        if in_pw is not None or out_pw is not None:
                            grid_buy = float(in_pw or 0)
                            grid_sell = float(out_pw or 0)
                            grid_available = True
                            break

            # Fallback 2: device-reported system fields (gridInPw/gridOutPw — already
            # alias-normalized from gridBuyPw/gridSellPw — or inGridSidePw/outGridSidePw).
            # inOngridPw/outOngridPw are deliberately excluded (see _grid_net_from_system).
            if not grid_available:
                sys_net, sys_available = _grid_net_from_system(
                    data,
                    grid_in,
                    grid_out,
                    ongrid_charge,
                    ongrid_supply,
                    in_grid_side,
                    out_grid_side,
                    include_ongrid=False,
                )
                if sys_available:
                    grid_available = True
                    grid_buy = max(0.0, sys_net)
                    grid_sell = max(0.0, -sys_net)

            # Calculate P_grid
            p_grid = None
            if grid_available:
                p_grid = grid_buy - grid_sell

                # 🔴异常流程（仅当电表可用且并网口处于充电态时生效）
                # GridAvailable=true 且 GridBuy < OngridCharge 且 (OngridCharge - GridBuy) <= 50W
                if grid_buy < ongrid_charge and (ongrid_charge - grid_buy) <= 50:
                    p_grid = p_ong

            # 5. Battery (total stack — main unit + expansion batteries)
            # batInPw/batOutPw are main-unit-only and do NOT include expansion batteries
            # (e.g. BP2500). Confirmed 2026-08-04 by parallel MQTT/app measurement:
            # energy balance matches the Jackery app within ≤13 W; batInPw diverges by
            # 200–300 W when the BP2500 is actively charging.
            # Formula: PV + grid_in − grid_out_to_ac − eps_out + eps_in
            total_batt_net = pv + ongrid_charge - ongrid_supply - ac_out + ac_in
            total_batt_charge = max(0.0, total_batt_net)
            total_batt_discharge = max(0.0, -total_batt_net)
            p_batt = total_batt_net

            # 6. Home (Calculated)
            p_home = 0.0

            if p_grid is not None:
                # 电表可用
                # Base formula: p_home = p_grid - p_ong
                #   = (grid_buy - grid_sell) - (ongrid_charge - ongrid_supply)
                #   = ongrid_supply + grid_buy - grid_sell - ongrid_charge
                # This correctly handles all normal scenarios including phase-balanced
                # feed-in (outOngridPw is total SolarVault AC output, not net-to-grid).
                p_home = p_grid - p_ong

                # 🔴 异常分支 1: measurement noise — grid_buy slightly below ongrid_charge
                if grid_buy > 0 and ongrid_charge > 0 and grid_buy < ongrid_charge and (ongrid_charge - grid_buy) <= 50:
                    p_home = 0.0

                # 🔴 异常分支 2: larger discrepancy between grid_buy and ongrid_charge
                elif grid_buy > 0 and ongrid_charge > 0 and grid_buy < ongrid_charge and (ongrid_charge - grid_buy) > 50:
                    p_home = ongrid_charge - grid_buy

            else:
                # 电表不可用 (No CT / collector / system fields) — the unit's net AC output
                # is the only available estimate of the house load.
                p_home = max(0.0, -p_ong)

            # House loads cannot be negative — clamp any sensor-timing artefact to 0.
            p_home = max(0.0, p_home)

            # Store calculated values
            data["calc_home_power"] = p_home
            data["calc_batt_net_power"] = p_batt
            data["total_battery_charge_power"] = total_batt_charge
            data["total_battery_discharge_power"] = total_batt_discharge
            data["grid_available"] = grid_available
            data["calc_grid_net_power"] = p_grid if grid_available else None

        except Exception as e:
            _LOGGER.error(f"Error calculating energy flow: {e}")

        return data

    def _distribute_data(self, data: dict) -> None:
        """分发数据给传感器."""
        for sensor_id, entity in self._sensors.items():
            entity._update_from_coordinator(data)

    def _mark_all_offline(self) -> None:
        """Mark all entities as unavailable."""
        for entity in self._sensors.values():
            if entity.available:
                entity._attr_available = False
                entity.async_write_ha_state()

    async def _periodic_data_request(self) -> None:
        """Send periodic poll requests (type-25, type-105, type-100)."""
        _LOGGER.info("Starting periodic data polling for %s...", self._device_sn)

        # Ü8: Send initial poll immediately so sensors populate before the first sleep.
        # Small delay lets subscriptions settle first.
        await asyncio.sleep(2)
        if self._device_sn:
            await self._send_poll_requests()

        while True:
            try:
                if time.time() - self._last_update_time > OFFLINE_TIMEOUT:
                    self._mark_all_offline()

                # Re-auth heuristic: the device stays completely silent when it rejects
                # the token (it does not answer with an error). If we have been polling
                # for REAUTH_HINT_TIMEOUT seconds without a single reply, the token
                # (or the configured SN) is most likely wrong.
                if (
                    not self._ever_received
                    and self._device_sn
                    and time.time() - self._start_time > REAUTH_HINT_TIMEOUT
                ):
                    self._trigger_reauth(
                        f"no device response within {REAUTH_HINT_TIMEOUT}s after setup"
                    )

                if not self._device_sn:
                    _LOGGER.debug("Waiting for device SN discovery...")
                    await asyncio.sleep(5)
                    continue

                await self._send_poll_requests()
                await asyncio.sleep(REQUEST_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in polling task: %s", e)
                await asyncio.sleep(REQUEST_INTERVAL)

    async def _send_poll_requests(self) -> None:
        """Send type-25, throttled type-105, and type-100 poll requests."""
        if not self._device_sn:
            return
        action_topic = f"{self._topic_root}/device/{self._device_sn}/action"
        ts = int(time.time())

        # 1. Poll device status (type-25)
        try:
            payload_25 = {
                "type": 25, "eventId": 0,
                "messageId": random.randint(1000, 9999),
                "ts": ts, "token": self._token, "body": None,
            }
            await ha_mqtt.async_publish(self.hass, action_topic, json.dumps(payload_25), 0, False)
        except Exception as e:
            _LOGGER.warning("Error polling device status (type-25): %s", e)

        # 1b. Read-all-settings request (type-2). Some firmware answers this with a
        # settings block that type-25 does not contain; harmless when unsupported.
        try:
            payload_2 = {
                "type": 2, "eventId": 0,
                "messageId": random.randint(1000, 9999),
                "ts": ts, "token": self._token, "body": None,
            }
            await ha_mqtt.async_publish(self.hass, action_topic, json.dumps(payload_2), 0, False)
        except Exception as e:
            _LOGGER.debug("Error sending read-all-settings request (type-2): %s", e)

        # 2. Poll full system state (type-105) every 3 cycles ≈ 30 s
        self._poll_105_counter += 1
        if self._poll_105_counter >= 3:
            self._poll_105_counter = 0
            try:
                payload_105 = {
                    "type": 105, "eventId": 0,
                    "messageId": random.randint(1000, 9999),
                    "ts": ts, "token": self._token, "body": None,
                }
                await ha_mqtt.async_publish(self.hass, action_topic, json.dumps(payload_105), 0, False)
                _LOGGER.debug("Sent type-105 poll (full system state)")
            except Exception as e:
                _LOGGER.warning("Error polling full system state (type-105): %s", e)

        # 3. Poll sub-devices (type-100): CTs (2), SmartMeter 3P (3), Plugs (6)
        try:
            for dev_type in [2, 3, 6]:
                payload_100 = {
                    "type": 100, "eventId": 0,
                    "messageId": random.randint(1000, 9999),
                    "ts": ts, "token": self._token,
                    "body": {"devType": dev_type},
                }
                await ha_mqtt.async_publish(self.hass, action_topic, json.dumps(payload_100), 0, False)
                await asyncio.sleep(0.5)
        except Exception as e:
            _LOGGER.warning("Error polling sub-devices (type-100): %s", e)

        _LOGGER.debug("Sent poll requests to %s", action_topic)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jackery sensors."""
    config = config_entry.data
    topic_prefix = config.get("topic_prefix", "hb")
    token = config.get("token")
    mqtt_host = config.get("mqtt_host")
    device_sn = config.get("device_sn")

    coordinator = JackeryDataCoordinator(hass, topic_prefix, token, mqtt_host, device_sn)
    coordinator.config_entry_id = config_entry.entry_id

    # Register callback for dynamic entities
    def add_entities_callback(new_entities):
        async_add_entities(new_entities)
    coordinator.add_entities_callback = add_entities_callback

    hass.data[DOMAIN][config_entry.entry_id]["coordinator"] = coordinator

    entities = []
    for sensor_id, sensor_config in SENSORS.items():
        if sensor_config.get("json_key") is None:
            continue

        entity = JackerySensor(
            sensor_id=sensor_id,
            coordinator=coordinator,
            config_entry_id=config_entry.entry_id,
        )
        entities.append(entity)

    async_add_entities(entities)
    await coordinator.async_start()


class JackerySensor(SensorEntity):
    """Jackery Sensor."""
    # ... (Existing JackerySensor Code) ...
    def __init__(
        self,
        sensor_id: str,
        coordinator: JackeryDataCoordinator,
        config_entry_id: str,
    ) -> None:
        """Initialize."""
        self._sensor_id = sensor_id
        self._coordinator = coordinator
        self._config = SENSORS[sensor_id]

        self._attr_translation_key = sensor_id
        self._attr_native_unit_of_measurement = self._config["unit"]
        self._attr_icon = self._config["icon"]
        self._attr_device_class = self._config["device_class"]
        self._attr_state_class = self._config["state_class"]
        # Multi-instance unique ID: includes device_sn so two SolarVaults on the same HA don't clash
        device_sn = coordinator._device_sn or config_entry_id
        self._attr_unique_id = f"jackery_{device_sn}_{sensor_id}"
        self._attr_has_entity_name = True
        if self._config.get("options"):
            self._attr_options = self._config["options"]

        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_sn)},
            "name": "Jackery",
            "manufacturer": "Jackery",
            "model": DEFAULT_MODEL,
        }

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.register_sensor(self._sensor_id, self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_sensor(self._sensor_id)
        await super().async_will_remove_from_hass()

    def _update_from_coordinator(self, data: dict) -> None:
        """Receive data from coordinator."""
        # Special handling for EPS Output Power (Bidirectional)
        if self._sensor_id == "eps_output_power":
            out_p = float(data.get("swEpsOutPw", 0))
            in_p = float(data.get("swEpsInPw", 0))
            self._attr_native_value = out_p - in_p
            self._attr_available = True
            self.async_write_ha_state()
            return

        json_key = self._config.get("json_key")
        if not json_key or json_key not in data:
            return

        value = data[json_key]

        if self._sensor_id == "grid_net_power" and value is None:
            # Keep last value when CT data is temporarily missing
            return

        # Process specific conversions
        if self._sensor_id == "battery_temperature":
            # cellTemp is 0.1 C
            try:
                self._attr_native_value = float(value) * 0.1
            except (TypeError, ValueError):
                pass
        elif self._sensor_id == "battery_soc":
             self._attr_native_value = value
        elif self._sensor_id.startswith("solar_power_pv") and isinstance(value, dict):
            # Handle dictionary for PV if it occurs
            if "pvPw" in value:
                self._attr_native_value = value["pvPw"]
            elif "w" in value:
                self._attr_native_value = value["w"]
            elif "power" in value:
                self._attr_native_value = value["power"]
            else:
                self._attr_native_value = str(value)  # type: ignore[assignment]
        else:
            value_map = self._config.get("value_map")
            if value_map is not None:
                # ENUM sensor: translate integer MQTT value to option string (Ü5)
                try:
                    self._attr_native_value = value_map.get(int(value), str(value))
                except (TypeError, ValueError):
                    self._attr_native_value = str(value)  # type: ignore[assignment]
            else:
                scale = self._config.get("scale", 1)
                try:
                    raw = float(value) * scale
                    if self._config.get("unit") is None and scale == 1:
                        self._attr_native_value = int(raw) if raw == int(raw) else raw
                    else:
                        self._attr_native_value = raw
                except (TypeError, ValueError):
                    self._attr_native_value = value

        self._attr_available = True
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "device_sn": self._coordinator._device_sn,
            "raw_key": self._config.get("json_key"),
        }
        # Decode the funcEnable bitmask into named flags for troubleshooting.
        if self._sensor_id == "func_enable":
            raw_bits: Any = self._coordinator._data_cache.get("funcEnable")
            try:
                bits = int(raw_bits)
            except (TypeError, ValueError):
                return attrs
            attrs["func_enable_raw"] = bits
            attrs["func_enable_flags"] = {
                name: bool(bits & (1 << bit)) for bit, name in FUNC_ENABLE_BITS.items()
            }
        return attrs


class JackerySubDeviceSensor(SensorEntity):
    """Jackery Smart Plug / CT Sub-device Sensor."""

    def __init__(
        self,
        plug_sn: str,
        dev_type: int,
        sensor_key: str,
        sensor_config: dict,
        coordinator: JackeryDataCoordinator,
        config_entry_id: str,
        data_key: str = "plugs",
        use_cts: bool = False,       # legacy — prefer data_key
        use_expansion: bool = False,
        sensor_group: str = "",
    ) -> None:
        """Initialize."""
        self._plug_sn = plug_sn
        self._dev_type = dev_type
        self._sensor_key = sensor_key
        self._sensor_config = sensor_config
        self._coordinator = coordinator
        self._use_expansion = use_expansion
        # data_key determines which cache entry to read sub-device data from.
        # Explicit data_key takes precedence; fall back to use_cts for backward compat.
        if data_key != "plugs":
            self._data_key = data_key
        elif use_cts:
            self._data_key = "cts"
        else:
            self._data_key = "plugs"

        if self._use_expansion:
            device_name = "Battery"
        elif self._data_key == "collectors":
            device_name = "Collector"
        elif self._data_key == "cts":
            device_name = "SmartMeter" if dev_type == 3 else "CT"
        else:
            device_name = "Plug"

        translation_key = f"{sensor_group}_{sensor_key}" if sensor_group else sensor_key
        self._attr_translation_key = translation_key

        self._attr_native_unit_of_measurement = self._sensor_config.get("unit")
        self._attr_icon = self._sensor_config.get("icon")
        self._attr_device_class = self._sensor_config.get("device_class")
        self._attr_state_class = self._sensor_config.get("state_class")
        if self._sensor_config.get("options"):
            self._attr_options = self._sensor_config["options"]

        # Unique ID: jackery_ct_{sn}_power, jackery_plug_{sn}_energy, etc.
        safe_key = self._sensor_key.replace("_", "") # e.g. energy_import -> energyimport
        self._attr_unique_id = f"jackery_{device_name.lower()}_{plug_sn}_{safe_key}"
        self._attr_has_entity_name = True

        main_device_id = coordinator._device_sn or config_entry_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"sub_{plug_sn}")},
            "via_device": (DOMAIN, main_device_id),
            "name": f"Jackery {device_name} {plug_sn}",
            "manufacturer": "Jackery",
            "model": f"Sub-device Type {dev_type}",
        }

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Register with coordinator using a unique ID format
        self._coordinator.register_sensor(self._attr_unique_id, self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_sensor(self._attr_unique_id)
        await super().async_will_remove_from_hass()

    def _update_from_coordinator(self, data: dict) -> None:
        """Receive data from coordinator."""
        if self._use_expansion:
            exp_data = (data.get("expansion_batteries") or {}).get(self._plug_sn)
            if not exp_data:
                return
            val = exp_data.get(self._sensor_config.get("key"))
            if val is None:
                return
            try:
                scale = self._sensor_config.get("scale", 1)
                self._attr_native_value = float(val) * scale
                self._attr_available = True
                self.async_write_ha_state()
            except (TypeError, ValueError):
                pass
            return

        source = data.get(self._data_key)
        if self._data_key == "plugs":
            source = source or data.get("plug")
        if not source or not isinstance(source, list):
            return

        my_plug = next((p for p in source if (p.get("sn") == self._plug_sn or p.get("deviceSn") == self._plug_sn)), None)
        if not my_plug:
            return

        self._raw_data = dict(my_plug)

        target_key = self._sensor_config.get("key")

        # Direct field access: ct_3phase (HTO907A, cts, devType=3) and
        # collector (HTO910A, collectors, devType=4) — no subType phase mapping.
        is_direct_access = (
            (self._data_key == "cts" and self._dev_type == 3)
            or self._data_key == "collectors"
        )
        if is_direct_access:
            val = my_plug.get(target_key)
            if val is None:
                return
            options = self._sensor_config.get("options")
            if options is not None:
                # ENUM sensor: map integer value to option key.
                # options_offset shifts 1-based MQTT values (e.g. commMode: 1=LAN, 2=Cloud)
                # to 0-based list indices. Default offset=0 for 0-based values (commState).
                try:
                    offset = self._sensor_config.get("options_offset", 0)
                    idx = int(float(val)) - offset
                    self._attr_native_value = options[idx] if 0 <= idx < len(options) else str(val)
                except (TypeError, ValueError, IndexError):
                    self._attr_native_value = str(val)
            else:
                scale = self._sensor_config.get("scale", 1)
                try:
                    raw = float(val) * scale
                    if self._sensor_config.get("unit") is None and scale == 1:
                        self._attr_native_value = int(raw) if raw == int(raw) else raw
                    else:
                        self._attr_native_value = raw
                except (TypeError, ValueError):
                    self._attr_native_value = val
            self._attr_available = True
            self.async_write_ha_state()
            return

        val = my_plug.get(target_key)

        # CT phase mapping by subType (1=A, 2=B, 3=C, 4=Total, 5=Net dual-circuit)
        if self._data_key == "cts" and target_key in {"phasePw", "phaseEgy"}:
            sub_type = my_plug.get("subType")
            if target_key == "phasePw":
                if sub_type == 1:
                    val = my_plug.get("AphasePw") or my_plug.get("aPhasePw")
                elif sub_type == 2:
                    val = my_plug.get("BphasePw") or my_plug.get("bPhasePw")
                elif sub_type == 3:
                    # C 相（单相：A+B 路）
                    val = my_plug.get("CphasePw") or my_plug.get("cPhasePw")
                    if not val:
                        a_pw = my_plug.get("AphasePw") or my_plug.get("aPhasePw") or 0
                        b_pw = my_plug.get("BphasePw") or my_plug.get("bPhasePw") or 0
                        if any(v is not None for v in [a_pw, b_pw]):
                            val = float(a_pw) + float(b_pw)
                else:
                    val = my_plug.get("TphasePw") or my_plug.get("tPhasePw")
            else:
                if sub_type == 1:
                    val = my_plug.get("AphaseEgy") or my_plug.get("aPhaseEgy")
                elif sub_type == 2:
                    val = my_plug.get("BphaseEgy") or my_plug.get("bPhaseEgy")
                elif sub_type == 3:
                    # C 相（单相：A+B 路）
                    val = my_plug.get("CphaseEgy") or my_plug.get("cPhaseEgy")
                    if not val:
                        a_egy = my_plug.get("AphaseEgy") or my_plug.get("aPhaseEgy") or 0
                        b_egy = my_plug.get("BphaseEgy") or my_plug.get("bPhaseEgy") or 0
                        if any(v is not None for v in [a_egy, b_egy]):
                            val = float(a_egy) + float(b_egy)
                else:
                    val = my_plug.get("TphaseEgy") or my_plug.get("tPhaseEgy")
                # If subtype energy is zero/None but total is non-zero, fall back to the single non-zero phase
                if not val:
                    total_egy = my_plug.get("TphaseEgy") or my_plug.get("tPhaseEgy")
                    if total_egy:
                        a_egy = my_plug.get("AphaseEgy") or my_plug.get("aPhaseEgy") or 0
                        b_egy = my_plug.get("BphaseEgy") or my_plug.get("bPhaseEgy") or 0
                        c_egy = my_plug.get("CphaseEgy") or my_plug.get("cPhaseEgy") or 0
                        non_zero = [v for v in [a_egy, b_egy, c_egy] if v]
                        if len(non_zero) == 1:
                            val = non_zero[0]

        # Fallback logic for specific keys if needed (like Power)
        if val is None:
             if target_key == "outPw":
                 val = my_plug.get("power")
             elif target_key == "TphasePw":
                 # Accept alternate key casing and sum phase powers if needed
                 val = my_plug.get("tPhasePw")
                 if val is None:
                     a_pw = my_plug.get("AphasePw") or my_plug.get("aPhasePw") or 0
                     b_pw = my_plug.get("BphasePw") or my_plug.get("bPhasePw") or 0
                     c_pw = my_plug.get("CphasePw") or my_plug.get("cPhasePw") or 0
                     if any(v is not None for v in [a_pw, b_pw, c_pw]):
                         val = float(a_pw) + float(b_pw) + float(c_pw)
             elif target_key == "TphaseEgy":
                 # Total forward active energy
                 val = my_plug.get("tPhaseEgy")
                 if val is None:
                     a_egy = my_plug.get("AphaseEgy") or my_plug.get("aPhaseEgy") or 0
                     b_egy = my_plug.get("BphaseEgy") or my_plug.get("bPhaseEgy") or 0
                     c_egy = my_plug.get("CphaseEgy") or my_plug.get("cPhaseEgy") or 0
                     if any(v is not None for v in [a_egy, b_egy, c_egy]):
                         val = float(a_egy) + float(b_egy) + float(c_egy)
             elif target_key == "TnphaseEgy":
                 # Total reverse active energy
                 val = my_plug.get("tnPhaseEgy")
                 if val is None:
                     an_egy = my_plug.get("AnphaseEgy") or my_plug.get("anPhaseEgy") or 0
                     bn_egy = my_plug.get("BnphaseEgy") or my_plug.get("bnPhaseEgy") or 0
                     cn_egy = my_plug.get("CnphaseEgy") or my_plug.get("cnPhaseEgy") or 0
                     if any(v is not None for v in [an_egy, bn_egy, cn_egy]):
                         val = float(an_egy) + float(bn_egy) + float(cn_egy)

        if val is not None:
            try:
                scale = self._sensor_config.get("scale", 1)
                raw = float(val) * scale
                if self._sensor_config.get("unit") is None and scale == 1:
                    self._attr_native_value = int(raw) if raw == int(raw) else raw
                else:
                    self._attr_native_value = raw
                self._attr_available = True
                self.async_write_ha_state()
            except (TypeError, ValueError):
                pass

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        raw = getattr(self, "_raw_data", None) or {}
        attrs: dict[str, Any] = {
            "device_sn": self._plug_sn,
            "dev_type": self._dev_type,
            "sub_type": raw.get("subType"),
            "sensor_key": self._sensor_key,
            "comm_state": raw.get("commState"),
            "name": raw.get("name") or raw.get("scanName"),
        }
        if self._data_key in ("cts", "collectors"):
            # Human readable meter hardware name (diagnostic only)
            sub_type: Any = raw.get("subType")
            attrs["sub_type_label"] = CT_SUBTYPE_MAP.get(sub_type)
        if self._data_key == "cts" and self._dev_type == 3:
            # SmartMeter 3P (HTO907A)
            attrs.update({
                "import_l1_w": raw.get("aPhasePw"),
                "import_l2_w": raw.get("bPhasePw"),
                "import_l3_w": raw.get("cPhasePw"),
                "import_total_w": raw.get("tPhasePw"),
                "export_l1_w": raw.get("anPhasePw"),
                "export_l2_w": raw.get("bnPhasePw"),
                "export_l3_w": raw.get("cnPhasePw"),
                "export_total_w": raw.get("tnPhasePw"),
                "sche_phase": raw.get("schePhase"),
                "fun_form": raw.get("funForm"),
            })
        elif self._data_key == "cts":
            attrs.update({
                "tPhasePw": raw.get("tPhasePw"),
                "tPhaseEgy": raw.get("tPhaseEgy"),
                "tnPhaseEgy": raw.get("tnPhaseEgy"),
            })
        elif self._data_key == "collectors":
            # Meter Collector (HTO910A)
            attrs.update({
                "scan_name": raw.get("scanName"),
                "in_pw": raw.get("inPw"),
                "out_pw": raw.get("outPw"),
            })
        else:
            attrs.update({
                "inPw": raw.get("inPw"),
                "outPw": raw.get("outPw"),
                "sysSwitch": raw.get("sysSwitch") if raw.get("sysSwitch") is not None else raw.get("switchSta"),
                "totalEgy": raw.get("totalEgy"),
            })
        return attrs
