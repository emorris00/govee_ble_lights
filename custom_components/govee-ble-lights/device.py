import asyncio
import json
import logging
import math
from array import array
from collections.abc import Iterable
from functools import cached_property
from pathlib import Path
from typing import Optional

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection
from homeassistant.util.color import brightness_to_value, color_temperature_to_rgb

from .const import PacketType
from .db import get_device_info
from .govee_utils import PacketArg, prepare_packet
from .models import DeviceState, Mode, SegmentState

_LOGGER = logging.getLogger(__name__)

READ_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"
WRITE_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"


class Segment:
    id: int

    def __init__(self, id: int, device: "Device"):
        self.id = id
        self._device = device
        self._state = SegmentState()

    async def set_brightness(self, brightness: int):
        await self._device.set_brightness(brightness, [self])

    async def set_power(self, on: bool):
        await self._device.set_power(on, [self])

    async def set_color(self, color: tuple[int, int, int]):
        await self._device.set_color(color, [self])

    async def set_temp(self, temp: int):
        await self._device.set_temp(temp, [self])


class SegmentGroup:
    def __init__(self, device: "Device", segments: list[Segment]):
        self._device = device
        self._segments = segments

    async def set_brightness(self, brightness: int):
        await self._device.set_brightness(brightness, self._segments)

    async def set_power(self, on: bool):
        await self._device.set_power(on, self._segments)

    async def set_color(self, color: tuple[int, int, int]):
        await self._device.set_color(color, self._segments)

    async def set_temp(self, brightness: int):
        await self._device.set_temp(brightness, self._segments)


class Device:
    def __init__(self, ble_device: BLEDevice, model: str):
        self._ble_device = ble_device
        self._state = DeviceState()
        self._model = model
        self._supported_modes = [Mode.MANUAL, Mode.SCENE]
        self._scenes: list[str] = []

        self._client: Optional[BleakClient] = None
        self._lock: asyncio.Lock = asyncio.Lock()

        self._data = get_device_info(self._model)

        if self._data.segments:
            self._segments: list[Segment] = []
            self._segment_groups: list[SegmentGroup] = []
            for segment_ids in self._data.segments:
                segments = [Segment(x, self) for x in segment_ids]
                self._segments += segments
                self._segment_groups.append(SegmentGroup(self, list(segments)))

        self._data = json.loads(Path(Path(__file__).parent / "jsons" / (self._model + ".json")).read_text("utf-8"))

    @cached_property
    def name(self) -> str:
        """Get the name of the device."""
        return self._ble_device.name or self._ble_device.address

    def segment_bytes(self, segments: Iterable[Segment]) -> bytes:
        return sum([int(math.pow(2, x.id - 1)) for x in segments]).to_bytes(self._data.segment_byte_length, "little")

    async def set_brightness(self, brightness: int, segments: Optional[Iterable[Segment]] = None):
        scaled_brightness = round(brightness_to_value(self._data.brightness_scale, brightness))
        if segments:
            segment_bytes = self.segment_bytes(segments)
            await self.send(PacketType.SET_SEGMENTS_BRIGHTNESS, scaled_brightness, segment_bytes)

            for segment in segments:
                segment._state.brightness = brightness
        else:
            await self.send(PacketType.SET_BRIGHTNESS, scaled_brightness)
            self._state.brightness = brightness

    async def set_power(self, on: bool, segments: Optional[Iterable[Segment]] = None):
        if segments:
            if on:
                segment_bytes = self.segment_bytes(segments)
                if self._data.temp_range:
                    await self.send(PacketType.SET_SEGMENTS_RGB_TEMP, [0, 0, 0, 0, 0, 0, 0, 0], segment_bytes)
                else:
                    await self.send(PacketType.SET_SEGMENTS_RGB, [0, 0, 0], segment_bytes)
                for segment in segments:
                    segment._state.on = True
            else:
                packets = []

                for segment in segments:
                    segment_bytes = self.segment_bytes([segment])
                    if self._data.temp_range:
                        temp = segment._state.temp or 0
                        temp_color = [round(x) for x in color_temperature_to_rgb(temp)] if temp > 0 else [0, 0, 0]
                        packets.append(
                            prepare_packet(
                                PacketType.SET_SEGMENTS_RGB_TEMP,
                                segment._state.color,
                                temp.to_bytes(2),
                                temp_color,
                                segment_bytes,
                            )
                        )
                    else:
                        packets.append(prepare_packet(PacketType.SET_SEGMENTS_RGB, segment._state.color, segment_bytes))

        else:
            await self.send(PacketType.SET_POWER, int(on))
            self._state.on = on

    async def set_color(self, color: tuple[int, int, int], segments: Optional[list[Segment]] = None):
        if self._segment_groups:
            segments = segments or self._segments
            segment_bytes = self.segment_bytes(segments)

            if self._data.temp_range:
                await self.send(PacketType.SET_SEGMENTS_RGB_TEMP, color, [0, 0, 0, 0, 0], segment_bytes)
            else:
                await self.send(PacketType.SET_SEGMENTS_RGB, color, segment_bytes)

            for segment in segments:
                segment._state.color = color
                segment._state.temp = None
        else:
            await self.send(PacketType.SET_RGB, color)
            self._state.color = color

    async def set_temp(self, temp: int, segments: Optional[Iterable[Segment]] = None):
        temp_range = self._data.temp_range
        if not temp_range or temp < temp_range[0] or temp > temp_range[1]:
            return

        if self._segment_groups:
            segments = segments or self._segments
            segment_bytes = self.segment_bytes(segments)

            color = [round(x) for x in color_temperature_to_rgb(temp)]
            await self.send(PacketType.SET_SEGMENTS_RGB_TEMP, [0, 0, 0], temp.to_bytes(2), color, segment_bytes)

            for segment in segments:
                segment._state.color = (0, 0, 0)
                segment._state.temp = temp
        else:
            pass

    async def send(self, *args: PacketArg):
        await self.send_packets([prepare_packet(*args)])

    async def send_packets(self, packets: list[array[int]]):
        async with self._lock:
            client = await self._get_client()
            for packet in packets:
                await client.write_gatt_char(WRITE_UUID, packet, response=False)

    async def _get_client(self):
        if self._client is None or not self._client.is_connected:
            self._client = await establish_connection(
                BleakClient,
                self._ble_device,
                self.name,
                use_services_cache=True,
                ble_device_callback=lambda: self._ble_device,
            )

            await self._client.start_notify(READ_UUID, self._notify_callback)

            asyncio.create_task(self._update())

        return self._client

    async def _update(self):
        packets = []
        packets.append(prepare_packet(PacketType.GET_BRIGHTNESS))
        packets.append(prepare_packet(PacketType.GET_COLOR_MODE))
        packets.append(prepare_packet(PacketType.GET_POWER))
        await self.send_packets(packets)

    async def _update_segments(self):
        if self._segments:
            num = math.ceil(len(self._segments) / 4)
            packets = [prepare_packet(PacketType.GET_SEGMENT_INFO, [i]) for i in range(0, num)]
            await self.send_packets(packets)

    def _notify_callback(self, _: BleakGATTCharacteristic, packet: bytearray) -> None:
        if packet.startswith(PacketType.GET_BRIGHTNESS.value):
            self._brightness = packet[2]

        elif packet.startswith(PacketType.GET_POWER.value):
            self._on = bool(packet[2])

        elif packet.startswith(PacketType.GET_COLOR_MODE.value):
            self._color_mode = packet[3]
            if self._color_mode == 0x15:
                asyncio.create_task(self._update_segments())

        elif packet.startswith(PacketType.GET_SEGMENT_INFO.value):
            offset = (packet[2] - 1) * 4
            for i in range(0, 12, 4):
                id = offset + i + 1
                self._segments[id]._state.brightness = packet[i]
                self._segments[id]._state.color = (packet[i + 1], packet[i + 2], packet[i + 2])
