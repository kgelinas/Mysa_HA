"""
Copyright 2018 Jason Litzinger
See LICENSE for details
"""
import attr

from . import _constants

@attr.s
class ConnackPacket(object):
    """Parsed CONNACK packet

    :ivar return_code: Return code from the connect operation.

    :ivar session_present: Whether stored session state exists.

    :ivar pkt_type: MQTT_PACKET_CONNACK
    """
    return_code = attr.ib()
    session_present = attr.ib()
    pkt_type = attr.ib(default=_constants.MQTT_PACKET_CONNACK)


@attr.s
class SubackPacket(object):
    """Parsed SUBACK packet

    """
    packet_id = attr.ib()
    return_codes = attr.ib()
    pkt_type = attr.ib(default=_constants.MQTT_PACKET_SUBACK)


@attr.s(slots=True)
class PublishPacket(object):
    """
    Packet representing an incoming publish message.
    """
    dup = attr.ib()
    qos = attr.ib(
        validator=attr.validators.in_(_constants.VALID_QOS)
    )
    retain = attr.ib()
    topic = attr.ib()
    packetid = attr.ib()
    payload = attr.ib()
    pkt_type = attr.ib(default=_constants.MQTT_PACKET_PUBLISH)


@attr.s(slots=True)
class DisconnectPacket(object):
    """
    Packet representing a disconnect

    :ivar reserved: Reserved bits from the packet.
    """
    reserved = attr.ib()
    pkt_type = attr.ib(default=_constants.MQTT_PACKET_DISCONNECT)


@attr.s(slots=True)
class PubackPacket(object):
    """
    Class representing a PUBACK packet.

    :ivar packet_id: The packet identifier being ack'd.
    """
    packet_id = attr.ib()
    pkt_type = attr.ib(default=_constants.MQTT_PACKET_PUBACK)


@attr.s(slots=True)
class PingrespPacket(object):
    """
    Class representing a PINGRESP packet.  In
    generally this can be created once and reused.
    """
    pkt_type = attr.ib(default=_constants.MQTT_PACKET_PINGRESP)
