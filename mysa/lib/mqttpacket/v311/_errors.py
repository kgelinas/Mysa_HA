"""
Copyright 2018 Jason Litzinger
See LICENSE for details.
"""

class MQTTParseError(Exception):
    """Parse error"""


class MQTTMoreDataNeededError(Exception):
    """Parse Error when more data is needed."""

    
class MQTTInvalidPacketError(Exception):
    """Invalid packet"""
