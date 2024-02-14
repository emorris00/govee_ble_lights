import asyncio
import logging
import math
from array import array
from datetime import timedelta

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)

from .const import PacketType
from .govee_utils import prepare_packet

_LOGGER = logging.getLogger(__name__)

READ_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"
WRITE_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"


class GoveeBLECoordinator(DataUpdateCoordinator):
    _segments: int | None
    _segment_states: list
    _lock: asyncio.Lock = asyncio.Lock()

    _client: BleakClient | None = None
    _packets: list[array[int]] = []
    _ble_device: BLEDevice

    def __init__(self, hass, unique_id: str):
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="My sensor",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=30),
        )
        ble_device = bluetooth.async_ble_device_from_address(hass, unique_id.upper(), True)
        if ble_device is not None:
            self._ble_device = ble_device

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
        packets.append(prepare_packet(PacketType.GET_LIGHT_POWER))
        await self.send_packets(packets)

    async def _update_segments(self):
        if self._segments:
            packets = [
                prepare_packet(PacketType.GET_SEGMENT_INFO, [i]) for i in range(0, math.ceil(self._segments / 4))
            ]
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
            index = (packet[2] - 1) * 4
            for i in range(0, 3):
                blah = 3 + (i * 4)
                self._segment_states[index + i] = packet[blah : blah + 4]

    async def _async_update_data(self):
        return
