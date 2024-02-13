import array

from .const import CommandType


def prepareSinglePacketData(commandType: CommandType, data=[]):
    payload = [*commandType.value, *data]
    packet = array.array("B", payload + [0] * (20 - len(payload)))
    signPacket(packet)
    return packet


def prepareMultiplePacketsData(data):
    packets = []
    i = 0
    while len(data) > 0:
        payload = [0xA3, i]
        if i == 0:
            payload += [0x01, 0x00, 0x02]
        remaining = 19 - len(payload)
        payload += data[0:remaining]
        data = data[remaining:]
        payload += [0] * (20 - len(payload))
        packets.append(array.array("B", payload))
        i += 1

    packets[0][3] = len(packets)
    if len(packets) > 1:
        packets[-1][1] = 0xFF

    for packet in packets:
        signPacket(packet)

    return packets


def signPacket(data):
    checksum = 0
    for b in data:
        checksum ^= b
    data[19] = checksum & 0xFF
    return data
