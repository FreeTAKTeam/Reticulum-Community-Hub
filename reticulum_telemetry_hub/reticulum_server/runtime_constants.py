"""Runtime constants for the Reticulum telemetry hub."""

from __future__ import annotations

import LXMF
import RNS

from reticulum_telemetry_hub.config.constants import DEFAULT_STORAGE_PATH

STORAGE_PATH = DEFAULT_STORAGE_PATH
APP_NAME = LXMF.APP_NAME + ".delivery"
REM_APP_NAME = "r3akt.emergency"
DEFAULT_LOG_LEVEL = getattr(RNS, "LOG_DEBUG", getattr(RNS, "LOG_INFO", 3))
LOG_LEVELS = {
    "error": getattr(RNS, "LOG_ERROR", 1),
    "warning": getattr(RNS, "LOG_WARNING", 2),
    "info": getattr(RNS, "LOG_INFO", 3),
    "debug": getattr(RNS, "LOG_DEBUG", DEFAULT_LOG_LEVEL),
}
R3AKT_CUSTOM_TYPE_IDENTIFIER = "r3akt.mission.change.v1"
R3AKT_CUSTOM_META_VERSION = "1.0"
R3AKT_CUSTOM_TYPE_FIELD = int(getattr(LXMF, "FIELD_CUSTOM_TYPE", 0xFB))
R3AKT_CUSTOM_DATA_FIELD = int(getattr(LXMF, "FIELD_CUSTOM_DATA", 0xFC))
R3AKT_CUSTOM_META_FIELD = int(getattr(LXMF, "FIELD_CUSTOM_META", 0xFD))
MARKDOWN_RENDERER_FIELD = int(getattr(LXMF, "FIELD_RENDERER", 0x0F))
MARKDOWN_RENDERER_VALUE = int(getattr(LXMF, "RENDERER_MARKDOWN", 0x02))
ESCAPED_COMMAND_PREFIX = "\\\\\\"
IDENTITY_CAPABILITY_CACHE_TTL_SECONDS = 6 * 60 * 60

