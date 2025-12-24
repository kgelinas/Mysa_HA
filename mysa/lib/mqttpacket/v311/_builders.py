"""
Copyright 2018 Jason Litzinger
See LICENSE for details.
"""
import struct
from typing import Union # pylint: disable=unused-import

try:
    import attr
    if not hasattr(attr, "s"):
        import attrs as attr
except ImportError:
    import attrs as attr
import six

from . import _constants

_CONNECT_REMAINING_LENGTH = 10

PROTOCOL_NAME = 'MQTT'.encode('utf-8')

def _check_none_or_text(_instance, attribute, value):
    if value is not None and not isinstance(value, six.text_type):
        raise TypeError('{} must be None or text'.format(attribute))

def _check_will_message(instance, _attribute, value):
    if value is not None and instance.will_topic is None:
        raise ValueError('Will topic must be set with will message')

def _check_will_topic(instance, _attribute, value):
    if value is not None and instance.will_message is None:
        raise ValueError('Will message must be set with will topic')

def _check_password(instance, _attribute, value):
    if value is not None and instance.username is None:
        raise ValueError('Password requires username.')

def _check_will_qos(instance, _attribute, value):
    if value != 0x00 and instance.will_topic is None:
        raise ValueError('Will QOS requires topic/message')


def encode_remainining_length(remaining_length):
    # type: (int) -> bytes
    """Encode the remaining length for the packet.

    :returns: Encoded remaining length
    :rtype: bytes
    """
    encoding = True
    encoded_bytes = bytearray()
    encoded_byte = 0
    while encoding:
        encoded_byte = remaining_length % 128
        remaining_length //= 128
        if remaining_length:
            encoded_byte |= 0x80
        else:
            encoding = False
        encoded_bytes.append(encoded_byte)
    return bytes(encoded_bytes)


def encode_string(text):
    """Encode a string as per MQTT spec: two byte length, UTF-8 data"""
    if not isinstance(text, six.text_type):
        raise TypeError('text must be unicode')

    encoded_text = text.encode('utf-8')
    text_len = struct.pack('!H', len(encoded_text))
    return b''.join([text_len, encoded_text])


@attr.s
class ConnectSpec(object):
    """
    Data class for connection related options.
    """
    username = attr.ib(
        default=None,
        validator=_check_none_or_text,
    )
    password = attr.ib(
        default=None,
        validator=[
            _check_none_or_text,
            _check_password,
        ],
    )
    will_topic = attr.ib(
        default=None,
        validator=[
            _check_none_or_text,
            _check_will_topic
        ],
    )
    will_message = attr.ib(
        default=None,
        validator=[
            _check_none_or_text,
            _check_will_message
        ]
    )
    will_qos = attr.ib(
        default=0x00,
        validator=[
            attr.validators.in_(_constants.VALID_QOS),
            _check_will_qos,
        ]
    )

    def flags(self):
        """Get the flags for this connect spec."""
        flags = 0x02

        if self.will_topic:
            flags |= 0x04
            flags |= (self.will_qos << 3)

        if self.username:
            flags |= 0x80

        if self.password:
            flags |= 0x40

        return flags

    def payload(self):
        """Return the encoded connect options."""
        parts = []
        if self.username:
            parts.append(encode_string(self.username))

        if self.password:
            parts.append(encode_string(self.password))

        if self.will_topic:
            parts.append(encode_string(self.will_topic))
            parts.append(encode_string(self.will_message))

        return b''.join(parts)


def connect(client_id, keepalive=60, connect_spec=None):
    """Create a CONNECT packet

    :param client_id: The id of the client.
    :type client_id: unicode

    :param keepalive: How long to keep the network alive, default
        60s.
    :type keepalive: int

    :param connect_spec: The spec for this connection or None
    :type connect_spec: mqttpacket.ConnectSpec

    :returns: A connect packet.
    :rtype: bytes

    """

    remaining_length = 0

    msg = six.int2byte(
        (_constants.MQTT_PACKET_CONNECT << 4),
    )

    parts = [msg]

    encoded_conn_spec = b''
    if connect_spec is not None:
        encoded_conn_spec = connect_spec.payload()
        meta = struct.pack(
            "!H4sBBH",
            0x0004,
            PROTOCOL_NAME,
            _constants.PROTOCOL_LEVEL,
            connect_spec.flags(),
            keepalive,
        )
        remaining_length += len(encoded_conn_spec)
    else:
        meta = struct.pack(
            "!H4sBBH",
            0x0004,
            PROTOCOL_NAME,
            _constants.PROTOCOL_LEVEL,
            0x02,
            keepalive,
        )

    remaining_length += len(meta)
    encoded_client_id = b''
    if client_id:
        encoded_client_id = encode_string(client_id)
        remaining_length += len(encoded_client_id)

    parts.append(encode_remainining_length(remaining_length))
    parts.append(meta)
    parts.append(encoded_client_id)
    parts.append(encoded_conn_spec)

    return b''.join(parts)


def pingreq():
    """
    Create a PINGREQ packet.
    """
    return b'\xc0\x00'


def _validate_qos(_instance, _attribute, value):
    if not 0 <= value < 3:
        raise ValueError('qos must be 0 <= qos < 3')


@attr.s(slots=True)
class SubscriptionSpec(object):
    """
    A data class for a topicfilter qos pair.
    """
    topicfilter = attr.ib(
        validator=attr.validators.instance_of(six.text_type),
    )

    qos = attr.ib(
        validator=_validate_qos,
    )

    _encoded = attr.ib(init=False)

    def __attrs_post_init__(self):
        self._encoded = self.topicfilter.encode('utf-8')

    def remaining_len(self):
        """
        Length for this spec.
        """
        return 3 + len(self._encoded)

    def to_bytes(self):
        """Encode this spec as bytes"""
        return b''.join([
            struct.pack('!H', len(self._encoded)),
            self._encoded,
            struct.pack('!B', self.qos)
        ])


def subscribe(packetid, topicspecs):
    """Create a subscribe packet.

    :param topicfilter: The list of topicfilter specs.

    :param qos: The QoS level to use.

    """
    if not 0 < packetid < 65535:
        raise ValueError('Packetid must be 0 < packetid < 65535')

    remaining_len = 2 # packetid
    for spec in topicspecs:
        remaining_len += spec.remaining_len()

    msg = six.int2byte(
        (_constants.MQTT_PACKET_SUBSCRIBE << 4) | 0x02,
    )

    encoded_specs = [msg]
    encoded_specs.append(encode_remainining_length(remaining_len))
    encoded_specs.append(struct.pack('!H', packetid))
    encoded_specs.extend(
        [s.to_bytes() for s in topicspecs]
    )

    return b''.join(encoded_specs)


def disconnect():
    # type: () -> bytes
    """Build a DISCONNECT packet."""
    return struct.pack(
        "!BB",
        (_constants.MQTT_PACKET_DISCONNECT << 4),
        0
    )


def publish(topic, dup, qos, retain, payload, packet_id=None):
    # type: (str, bool, int, bool, bytes, Union[None,int]) -> bytes
    """Build a PUBLISH packet.
    """
    #remaining_len = (topiclen after encoding + 2) + (2 | 0 if packetid) + payload_len
    if qos not in _constants.VALID_QOS:
        raise ValueError('QoS must be 0, 1, or 2')

    if not isinstance(topic, six.text_type):
        raise ValueError('Qos must be 0, 1, or 2')

    if qos > 0 and packet_id is None:
        raise ValueError('QoS of 1 or 2 must have a packet id')

    if qos == 0 and dup:
        raise ValueError('Dup must not be set on QoS of 0')

    if not isinstance(payload, bytes):
        raise TypeError('Payload must be bytes')

    remaining_len = len(payload)
    encoded_packet_id = b''
    if qos > 0:
        remaining_len += _constants.PACKET_ID_LEN
        encoded_packet_id = struct.pack('!H', packet_id)

    encoded_topic = encode_string(topic)
    remaining_len += len(encoded_topic)

    rl = encode_remainining_length(remaining_len)
    byte1 = _constants.MQTT_PACKET_PUBLISH << 4
    byte1 |= (int(dup) << 3)
    byte1 |= qos << 1
    byte1 |= int(retain)
    return b''.join((
        six.int2byte(byte1),
        rl,
        encoded_topic,
        encoded_packet_id,
        payload
    ))


def unsubscribe(packet_id, topics):
    # (int, List[str]) -> bytes
    """Build an UNSUBSCRIBE message for the specified topics."""
    if not topics:
        raise ValueError('At least one topic must be specified')

    remaining_len = 2
    encoded_packet_id = struct.pack('!H', packet_id)
    encoded_topics = [encode_string(t) for t in topics]
    for et in encoded_topics:
        remaining_len += len(et)

    parts = [six.int2byte((_constants.MQTT_PACKET_UNSUBSCRIBE << 4) | 0x1)]
    parts.append(encode_remainining_length(remaining_len))
    parts.append(encoded_packet_id)
    parts.extend(encoded_topics)
    return b''.join(parts)
