"""SQLAlchemy models for LXMF telemetry sensors."""

from .acceleration import Acceleration
from .ambient_light import AmbientLight
from .angular_velocity import AngularVelocity
from .battery import Battery
from .connection_map import ConnectionMap
from .generic import (
    Custom,
    Fuel,
    NonVolatileMemory,
    PowerConsumption,
    PowerProduction,
    Processor,
    RandomAccessMemory,
    Tank,
)
from .gravity import Gravity
from .humidity import Humidity
from .information import Information
from .location import Location
from .magnetic_field import MagneticField
from .lxmf_propagation import LXMFPropagation, LXMFPropagationPeer
from .physical_link import PhysicalLink
from .pressure import Pressure
from .proximity import Proximity
from .received import Received
from .rns_transport import RNSTransport
from .sensor import Sensor
from .sensor_enum import *
from .sensor_mapping import sid_mapping
from .temperature import Temperature
from .time import Time

__all__ = [
    "Acceleration",
    "AmbientLight",
    "AngularVelocity",
    "Battery",
    "ConnectionMap",
    "Custom",
    "Fuel",
    "Gravity",
    "Humidity",
    "Information",
    "Location",
    "LXMFPropagation",
    "LXMFPropagationPeer",
    "MagneticField",
    "NonVolatileMemory",
    "PhysicalLink",
    "PowerConsumption",
    "PowerProduction",
    "Processor",
    "Proximity",
    "Pressure",
    "RandomAccessMemory",
    "Received",
    "RNSTransport",
    "Sensor",
    "Temperature",
    "Time",
    "Tank",
    "sid_mapping",
]
