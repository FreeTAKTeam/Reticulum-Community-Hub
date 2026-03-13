
LXMF fields are extensible data structures that allow LXMF messages to carry various types of metadata and content beyond basic text. They are defined as constants in the `LXMF` module and used within the `fields` dictionary of an `LXMessage` [1](#0-0) .

## Core Fields

The standard LXMF fields include:

| Field | Hex Value | Purpose |
|-------|-----------|---------|
| `FIELD_EMBEDDED_LXMS` | 0x01 | Embedded LXMF messages |
| `FIELD_TELEMETRY` | 0x02 | Telemetry data |
| `FIELD_TELEMETRY_STREAM` | 0x03 | Streaming telemetry |
| `FIELD_ICON_APPEARANCE` | 0x04 | Icon/appearance data |
| `FIELD_FILE_ATTACHMENTS` | 0x05 | File attachments |
| `FIELD_IMAGE` | 0x06 | Image data |
| `FIELD_AUDIO` | 0x07 | Audio data |
| `FIELD_THREAD` | 0x08 | Thread/conversation grouping |
| `FIELD_COMMANDS` | 0x09 | Command structures |
| `FIELD_RESULTS` | 0x0A | Command results |
| `FIELD_GROUP` | 0x0B | Group information |
| `FIELD_TICKET` | 0x0C | Authentication tickets |
| `FIELD_EVENT` | 0x0D | Event data |
| `FIELD_RNR_REFS` | 0x0E | Reticulum name references |
| `FIELD_RENDERER` | 0x0F | Message rendering hints |

## Custom and Extension Fields

LXMF provides fields for custom extensions and external protocol bridging [2](#0-1) :

- `FIELD_CUSTOM_TYPE` (0xFB): Format/type/protocol identifier
- `FIELD_CUSTOM_DATA` (0xFC): Embedded payload data
- `FIELD_CUSTOM_META` (0xFD): Custom metadata

## Field-Specific Constants

### Audio Modes
For `FIELD_AUDIO`, LXMF defines audio codec modes [3](#0-2) :

**Codec2 Modes**: 450PWB, 450, 700C, 1200, 1300, 1400, 1600, 2400, 3200
**Opus Modes**: OGG, LBW, MBW, PTT, RT_HDX, RT_FDX, STANDARD, HQ, BROADCAST, LOSSLESS

### Renderer Specifications
For `FIELD_RENDERER`, LXMF defines rendering hints [4](#0-3) :

- `RENDERER_PLAIN` (0x00): Plain text
- `RENDERER_MICRON` (0x01): Micron markup
- `RENDERER_MARKDOWN` (0x02): Markdown formatting
- `RENDERER_BBCODE` (0x03): BBCode formatting

## Usage in Messages

Fields are used in the `LXMessage` class through the `fields` parameter [5](#0-4) . The fields dictionary is included in the message payload during packing [6](#0-5)  and can be accessed via the `get_fields()` method [7](#0-6) .

The delivery callback in the example receiver shows how fields are displayed when a message is received [8](#0-7) .

## Notes

Fields are optional but must be included in the message structure (can be empty). The fields dictionary can contain any structure or depth, allowing for extensive customization while maintaining interoperability through standardized field types.

Wiki pages you might want to explore:
- [Overview (markqvist/LXMF)](/wiki/markqvist/LXMF#1)
- [API Reference (markqvist/LXMF)](/wiki/markqvist/LXMF#8)

### Citations

**File:** LXMF/LXMF.py (L8-41)
```python
FIELD_EMBEDDED_LXMS    = 0x01
FIELD_TELEMETRY        = 0x02
FIELD_TELEMETRY_STREAM = 0x03
FIELD_ICON_APPEARANCE  = 0x04
FIELD_FILE_ATTACHMENTS = 0x05
FIELD_IMAGE            = 0x06
FIELD_AUDIO            = 0x07
FIELD_THREAD           = 0x08
FIELD_COMMANDS         = 0x09
FIELD_RESULTS          = 0x0A
FIELD_GROUP            = 0x0B
FIELD_TICKET           = 0x0C
FIELD_EVENT            = 0x0D
FIELD_RNR_REFS         = 0x0E
FIELD_RENDERER         = 0x0F

# For usecases such as including custom data structures,
# embedding or encapsulating other data types or protocols
# that are not native to LXMF, or bridging/tunneling
# external protocols or services over LXMF, the following
# fields are available. A format/type/protocol (or other)
# identifier can be included in the CUSTOM_TYPE field, and
# the embedded payload can be included in the CUSTOM_DATA
# field. It is up to the client application to correctly
# discern and potentially utilise any data embedded using
# this mechanism.
FIELD_CUSTOM_TYPE      = 0xFB
FIELD_CUSTOM_DATA      = 0xFC
FIELD_CUSTOM_META      = 0xFD

# The non-specific and debug fields are intended for
# development, testing and debugging use.
FIELD_NON_SPECIFIC     = 0xFE
FIELD_DEBUG            = 0xFF
```

**File:** LXMF/LXMF.py (L55-79)
```python
AM_CODEC2_450PWB       = 0x01
AM_CODEC2_450          = 0x02
AM_CODEC2_700C         = 0x03
AM_CODEC2_1200         = 0x04
AM_CODEC2_1300         = 0x05
AM_CODEC2_1400         = 0x06
AM_CODEC2_1600         = 0x07
AM_CODEC2_2400         = 0x08
AM_CODEC2_3200         = 0x09

# Opus Audio Modes
AM_OPUS_OGG            = 0x10
AM_OPUS_LBW            = 0x11
AM_OPUS_MBW            = 0x12
AM_OPUS_PTT            = 0x13
AM_OPUS_RT_HDX         = 0x14
AM_OPUS_RT_FDX         = 0x15
AM_OPUS_STANDARD       = 0x16
AM_OPUS_HQ             = 0x17
AM_OPUS_BROADCAST      = 0x18
AM_OPUS_LOSSLESS       = 0x19

# Custom, unspecified audio mode, the client must
# determine it itself based on the included data.
AM_CUSTOM              = 0xFF
```

**File:** LXMF/LXMF.py (L89-93)
```python
RENDERER_PLAIN         = 0x00
RENDERER_MICRON        = 0x01
RENDERER_MARKDOWN      = 0x02
RENDERER_BBCODE        = 0x03

```

**File:** LXMF/LXMessage.py (L113-147)
```python
    def __init__(self, destination, source, content = "", title = "", fields = None, desired_method = None, destination_hash = None, source_hash = None, stamp_cost=None, include_ticket=False):

        if isinstance(destination, RNS.Destination) or destination == None:
            self.__destination    = destination
            if destination != None:
                self.destination_hash = destination.hash
            else:
                self.destination_hash = destination_hash
        else:
            raise ValueError("LXMessage initialised with invalid destination")

        if isinstance(source, RNS.Destination) or source == None:
            self.__source    = source
            if source != None:
                self.source_hash = source.hash
            else:
                self.source_hash = source_hash
        else:
            raise ValueError("LXMessage initialised with invalid source")

        if title == None:
            title = ""

        if type(title) == bytes:
            self.set_title_from_bytes(title)
        else:
            self.set_title_from_string(title)

        if type(content) == bytes:
            self.set_content_from_bytes(content)
        else:
            self.set_content_from_string(content)

        self.set_fields(fields)

```

**File:** LXMF/LXMessage.py (L219-220)
```python
    def get_fields(self):
        return self.fields
```

**File:** LXMF/LXMessage.py (L344-344)
```python
            self.payload = [self.timestamp, self.title, self.content, self.fields]
```

**File:** docs/example_receiver.py (L34-34)
```python
  RNS.log("\t| Fields                 : "+str(message.fields))
```
