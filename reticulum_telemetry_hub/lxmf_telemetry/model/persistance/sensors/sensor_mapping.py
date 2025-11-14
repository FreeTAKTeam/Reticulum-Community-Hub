from .sensor_enum import *
from .acceleration import Acceleration
from .ambient_light import AmbientLight
from .angular_velocity import AngularVelocity
from .battery import Battery
from .gravity import Gravity
from .humidity import Humidity
from .information import Information
from .location import Location
from .magnetic_field import MagneticField
from .physical_link import PhysicalLink
from .pressure import Pressure
from .proximity import Proximity
from .received import Received
from .temperature import Temperature
from .time import Time
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
from .lxmf_propagation import LXMFPropagation
from .rns_transport import RNSTransport

sid_mapping = {
    SID_TIME: Time,
    SID_LOCATION: Location,
    SID_PRESSURE: Pressure,
    SID_BATTERY: Battery,
    SID_PHYSICAL_LINK: PhysicalLink,
    SID_ACCELERATION: Acceleration,
    SID_TEMPERATURE: Temperature,
    SID_HUMIDITY: Humidity,
    SID_MAGNETIC_FIELD: MagneticField,
    SID_AMBIENT_LIGHT: AmbientLight,
    SID_GRAVITY: Gravity,
    SID_ANGULAR_VELOCITY: AngularVelocity,
    SID_PROXIMITY: Proximity,
    SID_INFORMATION: Information,
    SID_RECEIVED: Received,
    SID_POWER_CONSUMPTION: PowerConsumption,
    SID_POWER_PRODUCTION: PowerProduction,
    SID_PROCESSOR: Processor,
    SID_RAM: RandomAccessMemory,
    SID_NVM: NonVolatileMemory,
    SID_TANK: Tank,
    SID_FUEL: Fuel,
    SID_LXMF_PROPAGATION: LXMFPropagation,
    SID_RNS_TRANSPORT: RNSTransport,
    SID_CONNECTION_MAP: ConnectionMap,
    SID_CUSTOM: Custom,
}
