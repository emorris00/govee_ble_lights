from enum import Enum

DOMAIN = "govee-ble-lights"

CONF_KEEP_ALIVE = "keep-alive"


class PacketType(Enum):
    KEEP_ALIVE = bytes([0xAA])

    DIY_DATA = bytes([0xA1])

    GET_BRIGHTNESS = bytes([0xAA, 0x04])
    GET_COLOR_MODE = bytes([0xAA, 0x05, 0x01])
    GET_LIGHT_POWER = bytes([0xAA, 0x33])
    GET_POWER = bytes([0xAA, 0x01])
    GET_SEGMENT_INFO = bytes([0xAA, 0xA5])

    SCENE_DATA = bytes([0xA3])

    SET_BRIGHTNESS = bytes([0x33, 0x04])
    SET_LIGHT_POWER = bytes([0x33, 0x33])
    SET_POWER = bytes([0x33, 0x01])
    SET_RGB = bytes([0x33, 0x05, 0x02])
    SET_SCENE = bytes([0x33, 0x05, 0x04])
    SET_SEGMENTS_BRIGHTNESS = bytes([0x33, 0x05, 0x15, 0x02])
    SET_SEGMENTS_RGB = bytes([0x33, 0x05, 0x0B])
    SET_SEGMENTS_RGBWW = bytes([0x33, 0x05, 0x15, 0x01])
    # SET_SEGMENT_POWER = bytes([0x33, 0x05, 0x15, 0x01])
