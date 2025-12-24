"""
Copyright 2018 Jason Litzinger
See LICENSE for details.

A parser should either consume all packet data, or raise and error.

"""
from __future__ import absolute_import
from typing import (  # pylint: disable=unused-import
    ByteString,
    List,
    Any,
    Callable,
    Dict
)

from . import _packet, _errors, _constants

def parse_connack(data, remaining_length, variable_begin):
    # type: (bytearray, int, int) -> _packet.ConnackPacket
    """Parse a CONNACK packet

    :param data: Data to parse

    :param variable_begin: Offset of start of variable length header

    :raises: MQTTParseError if packet is malformed
    :returns: length consumed, return code and session_present flag from the
        CONNACK packet.

    :rtype: int

    """
    if remaining_length != 2:
        raise _errors.MQTTParseError("Remaining length invalid")

    ack_flags = data[variable_begin]
    rc = data[variable_begin+1]

    if (ack_flags & 0xFE) != 0:
        raise _errors.MQTTParseError("Reserved bits not clear")

    return _packet.ConnackPacket(
        rc,
        ack_flags
    )


_PINGRESP = _packet.PingrespPacket()

def parse_pingresp(_data, _length, _variable_begin):
    """
    Parse a PINGRESP, consume and discard.
    """
    return _PINGRESP


def parse_suback(data, remaining_length, variable_begin):
    """
    Parse a SUBACK packet.

    :param data: The data to parse.

    :param remaining_length: Remaining length field parsed
        from the packet.

    :param variable_begin: Offset of start of variable length header

    :param output: List of output packets.

    """
    end_payload = remaining_length + variable_begin
    packet_id = (data[variable_begin] << 8) | data[variable_begin+1]
    variable_begin += 2
    return _packet.SubackPacket(
        packet_id,
        [rc for rc in data[variable_begin:end_payload]]
    )



def parse_publish(data, remaining_length, variable_begin):
    # type: (bytearray, int, int) -> _packet.PublishPacket
    """Parse a PUBLISH packet.

    :param data: Incoming data to parse.
    :type data: bytearray

    :param variable_begin: Offset of start of variable length header

    :param output: List of result messages

    :returns: number of bytes consumed.

    """
    flags = data[0] & 0x0F
    qos = (flags & 0x06) >> 1

    end_packet = remaining_length + variable_begin

    topic_len = (data[variable_begin] << 8) | data[variable_begin+1]
    variable_begin += 2
    topic = data[variable_begin:variable_begin+topic_len].decode('utf-8')
    # Check for wildcard chars
    variable_begin += topic_len
    packetid = None
    if qos:
        packetid = (data[variable_begin] << 8) | data[variable_begin+1]
        variable_begin += 2

    return _packet.PublishPacket(
        (flags & 0x08) >> 3,
        qos,
        flags & 0x1,
        topic,
        packetid,
        data[variable_begin:end_packet]
    )


def parse_disconnect(data, _remaining_length, _offset):
    # type: (bytearray, int, int) -> _packet.DisconnectPacket
    """Parse a DISCONNECT packet and validate"""
    return _packet.DisconnectPacket(data[0] & 0x0f)


def parse_puback(data, remaining_length, offset):
    """Parse a puback from a payload."""
    if remaining_length != 2:
        raise _errors.MQTTInvalidPacketError(
            'Remaining length should be 2 for PUBACK'
        )
    return _packet.PubackPacket(
        (data[offset] << 8) | data[offset+1]
    )


def _null_parse(_data, _remaining_length, _offset):
    # type: (bytearray, int, int) -> None
    """Empty parser"""


PARSERS = {
    _constants.MQTT_PACKET_CONNECT: _null_parse,
    _constants.MQTT_PACKET_CONNACK: parse_connack,
    _constants.MQTT_PACKET_PUBLISH: parse_publish,
    _constants.MQTT_PACKET_PUBACK: parse_puback,
    _constants.MQTT_PACKET_PUBREC: _null_parse,
    _constants.MQTT_PACKET_PUBREL: _null_parse,
    _constants.MQTT_PACKET_PUBCOMP: _null_parse,
    _constants.MQTT_PACKET_SUBSCRIBE: _null_parse,
    _constants.MQTT_PACKET_SUBACK: parse_suback,
    _constants.MQTT_PACKET_UNSUBSCRIBE: _null_parse,
    _constants.MQTT_PACKET_UNSUBACK: _null_parse,
    _constants.MQTT_PACKET_PINGREQ: _null_parse,
    _constants.MQTT_PACKET_PINGRESP: parse_pingresp,
    _constants.MQTT_PACKET_DISCONNECT: parse_disconnect,
} # type: Dict[int, Callable[[bytearray, int, int], Any]]


_MULTIPLIERS = (1, 128, 128 * 128, 128 * 128 * 128, 0)
_MAX_REMAINING_LENGTH = 268435455

def check_total_len(data, offset, remaining_length, variable_begin):
    # type: (ByteString, int, int, int) -> bool
    """Verify enough data is available"""
    size_rem_len = variable_begin - offset - 1
    return (len(data) - offset) == (remaining_length + 1 + size_rem_len)

def parse(data, output):
    # type: (ByteString, List[Any]) -> int
    """Parse packets from data.

    :param data: Data to parse into MQTT packets

    :param output: Output list for storing parsed packets.

    :returns: number of bytes from data consumed

    """
    if not isinstance(data, bytearray):
        raise TypeError("data must be a bytearray")

    consumed = 0
    offset = 0

    while offset < len(data):
        pkt_type = data[offset] >> 4
        variable_begin = offset + 1
        remaining_length = 0
        parsing_len = True
        nb = 0
        while parsing_len:
            remaining_length += (data[variable_begin] & 127) * _MULTIPLIERS[nb]
            nb += 1
            parsing_len = (
                variable_begin < len(data)
                and (nb < 5)
                and ((data[variable_begin] & 128) != 0)
            )
            variable_begin += 1

        if nb == 5:
            raise _errors.MQTTParseError("Invalid remaining length")

        size_rem_len = variable_begin - offset - 1

        if not check_total_len(data, offset, remaining_length, variable_begin):
            return consumed

        try:
            r = PARSERS[pkt_type](
                data,
                remaining_length,
                variable_begin,
            )
        except KeyError:
            offset += 1
        except _errors.MQTTMoreDataNeededError:
            return consumed
        else:
            consumed += size_rem_len + 1 + remaining_length
            offset += consumed
            output.append(r)

    return consumed
