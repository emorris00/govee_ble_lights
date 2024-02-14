from array import array

from .const import PacketType


def prepare_packet(type: PacketType | None = None, data: list[int] | bytes | None = None) -> array[int]:
    packet = []
    if type is not None:
        packet += type.value

    if data is not None:
        packet += data

    if len(packet) == 0:
        raise ValueError("Packet is empty")

    packet = array("B", packet + [0] * (20 - len(packet)))

    checksum = 0
    for x in packet:
        checksum ^= x
    packet[19] = checksum & 0xFF

    return packet


def prepare_scene_data_packets(data: list[int] | bytes) -> list[array[int]]:
    packets = []
    i = 0
    while len(data) > 0:
        payload = [*PacketType.SCENE_DATA.value, i]
        if i == 0:
            payload += [0x01, 0x00, 0x02]
        remaining = 19 - len(payload)
        payload += data[0:remaining]
        data = data[remaining:]
        payload += [0] * (20 - len(payload))
        packets.append(array("B", payload))
        i += 1

    packets[0][3] = len(packets)
    if len(packets) > 1:
        packets[-1][1] = 0xFF

    return [prepare_packet(packet) for packet in packets]
