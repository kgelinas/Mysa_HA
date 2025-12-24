#!/usr/bin/env
from argparse import ArgumentParser
import base64
import json
import logging
import os
from sys import stderr
from time import time, sleep
from typing import Optional
from uuid import uuid1
from urllib.parse import urlparse

logging.basicConfig(format='[%(levelname)s:%(name)s] %(asctime)s - %(message)s',
    level=os.environ.get('LOGLEVEL', 'INFO').strip().upper())
logger = logging.getLogger(__name__)

from .util import slurpy
from . import mysa_stuff
from .aws import boto3
from .mysa_stuff import BASE_URL, MysaReading, MysaReadingV0, MysaReadingV3
from .auth import authenticate, CONFIG_FILE

import websockets.exceptions, websockets.sync.client
import mqttpacket.v311 as mqttpacket
import requests


def translate_packet(ws: websockets.sync.client.ClientConnection, pkt: mqttpacket._packet.MQTTPacket, current: float, last_sensor_temp: dict[str, float]) -> Optional[int]:
    replied = None

    if isinstance(pkt, mqttpacket._packet.DisconnectPacket):
        logger.warning("Received MQTT disconnect from server")
    elif isinstance(pkt, mqttpacket.PublishPacket):
        did, subtopic = pkt.topic.split('/')[-2:]
        try:
            payload = json.loads(pkt.payload, object_hook=slurpy, strict=False)
        except json.JSONDecodeError as exc:
            # Very rarely (every few days-weeks) I receive a packet with a
            # malformed or incomplete JSON payload, something like:
            #   '{"ver":"1.0","src":{"type": 1, "ref": "$DID"},"time":$UNIXTIME,"msg":44,"id":$RANDOM_HUGE_INTEGER, "resp_id":$UNIXTIMEMS, "body":'
            # FIXME: should we ack such messages if their QOS is >0?
            logger.warning(f"Received packet with non-JSON payload: {pkt.payload}", exc_info=exc)
            return replied

        if subtopic == 'in' and payload.get('msg') == 44:
            # Setpoint message for BB-V2-0 device (we need to change $TYPE from 1 to 5):
            #
            # {"Timestamp": $UNIXTIME,
            #  "body": {"cmd": [{"sp": 17, "tm": -1}], "type": $TYPE, "ver": 1},
            #  "dest": {"ref": "$DID", "type": 1},
            #  "id": $UNIXTIMEMS,
            #  "msg": 44,
            #  "resp": 2,
            #  "src": {"ref": "$USER_UUID", "type": 100},
            #  "time": $UNIXTIME,
            #  "ver": "1.0"}

            assert payload.ver == "1.0"
            assert payload.resp == 2
            assert payload.dest == {'ref': did, 'type': 1}
            body = payload.body
            assert body.ver == 1
            if body.type == 1:   # what the app sends for model BB-V1-1
                body.type = 5    # ... what the model BB-V2-0-L actually wants
                payload.id = int(time() * 1000)
                payload.time = payload.Timestamp = payload.id // 1000
                opkt = mqttpacket.publish(pkt.topic, pkt.dup, pkt.qos, pkt.retain, packet_id=pkt.packetid ^ 0x8000,
                    payload=json.dumps(payload).encode())
                logger.debug(f"Translated command packet for BB-V1-0 into BB-V2-0-L: {mqttpacket.parse_one(opkt)}")

                ws.send(opkt)
                replied = time()
            elif body.type == 5:
                pass             # don't re-echo our own message

        elif subtopic == 'batch' and payload.get('msg') == 3:
            assert payload.ver == '1.0'
            assert payload.src == {'ref': did, 'type': 1}
            body = payload.body
            readings = MysaReading.parse_readings(base64.b64decode(body.readings))
            if readings[0].ver == 0:
                logger.debug(f'Saw already-translated-to-v0 readings packet')
            elif current is None:
                logger.warning(f'Skipping translation of readings packet because no current level was specified.')
            else:
                assert readings[0].ver == 3
                last_sensor_temp[did] = readings[-1].sensor_t  # stash latest SensorTemp so we can parrot it
                newr = b''.join(
                    bytes(MysaReadingV0(**{
                        k: getattr(r, k) for k, v in r.__dataclass_fields__.items()
                        if k not in ('voltage', 'current', 'always0', 'ver', 'rest')}))
                    for r in readings)
                body.readings = base64.b64encode(newr).decode()
                payload.id += 1
                opkt = mqttpacket.publish(pkt.topic, pkt.dup, pkt.qos, pkt.retain,
                    packet_id=pkt.packetid ^ 0x8000 if pkt.packetid else None,
                    payload=json.dumps(payload).encode())
                logger.debug(f"Translated readings packet for BB-V2-0 into BB-V1-0-L: {mqttpacket.parse_one(opkt)}")

                ws.send(opkt)
                replied = time()

        elif subtopic == 'out' and payload.get('msg') == 40:
            if current is None:
                logger.warning(f'Skipping translation of device state packet because no current level was specified.')

            # Device state message from BB-V2-0-L device:
            #
            # {"body": {"ambTemp": 16.7, "dtyCycle": 1.0, "hum": 48.0, "stpt": 17.8},
            #  "id": ${large random number},     # 64-bits long?
            #  "msg": 40,
            #  "src": {"ref": "$DID", "type": 1},
            #  "time": $UNIXTIME,
            #  "ver": "1.0"}

            assert payload.ver == "1.0"

            # Device state message from BB-V1-1 devices:
            #
            # {"ComboTemp": 20.93,          # = "SensorTemp" in /devices/state
            # "Current": 0.0,               # This is "the current right now" as opposed to "the highest current seen" reported in /devices/state
            # "Device": "$DID",
            # "Humidity": 48.0,
            # "MainTemp": 17.15,            # = "CorrectedTemp" in /devices/state
            # "MsgType": 0,
            # "SetPoint": 15.5,
            # "Stream": 1,
            # "ThermistorTemp": 0.0,
            # "Timestamp": $UNIXTIME}

            opkt = mqttpacket.publish(pkt.topic, pkt.dup, pkt.qos, pkt.retain,
                packet_id=pkt.packetid ^ 0x8000 if pkt.packetid else None,
                payload=json.dumps({
                    "ComboTemp": last_sensor_temp[did],   # whatever we got last
                    "Current": None if current is None else current * payload.body.get('dtyCycle', 1.0),
                    "Device": did,
                    "Humidity": payload.body.get('hum', 0.0),
                    "MainTemp": payload.body.get('ambTemp', 0.0),
                    "MsgType": 0,
                    "SetPoint": payload.body.get('stpt', 0.0),
                    "Stream": 1,
                    "ThermistorTemp": 0.0,
                    "Timestamp": payload.time,
            }).encode())
            logger.debug(f"Translated device state packet from BB-V2-0-L into BB-V1-1: {mqttpacket.parse_one(opkt)}")

            ws.send(opkt)
            replied = time()

        if pkt.qos > 0:
            ws.send(p := mqttpacket.puback(pkt.packetid))
            logger.debug(f"Sent PUBACK packet for packet_id={pkt.packetid}")
            replied = time()

    return replied


def main(args=None):
    p = ArgumentParser(description=
        '''This tool makes your Mysa Lite thermostat (model BB-V2-0-L) look like
        a Mysa Baseboard V1 thermostat (model BB-V1-1) to the official Mysa apps.

        This enables zone control, the usage graph, and the humidity sensor in the
        app.

        The Mysa Lite doesn't have a current sensor, and it doesn't report any
        estimated energy usage to the servers.''')
    p.add_argument('-u', '--user', help=f'Mysa username (default is first one configured in {CONFIG_FILE!r})')
    p.add_argument('-d', '--device', action='append', type=lambda s: s.replace(':','').lower(), help='Specific device (MAC address)')
    p.add_argument('-C', '--current', type=float, help="Estimated max current level (in Amperes). Mysa V2 Lite devices don't have current sensors.")
    p.add_argument('-V', '--voltage', default=240, type=int, help="RMS voltage level for the heater circuit (in Volts), typically 240 V (the default) but may be 208 V or 120 V.")
    p.add_argument('-R', '--reset', action='store_true', help='Just reset faked Mysa Lite devices, and exit')
    args = p.parse_args(args)

    # Authenticate with pycognito
    bsess = boto3.session.Session(region_name=mysa_stuff.REGION)
    try:
        u = authenticate(args.user, CONFIG_FILE, bsess)
    except Exception as exc:
        p.error(exc)

    assert u.token_type == 'Bearer'
    sess = requests.Session()
    sess.auth = mysa_stuff.auther(u)
    sess.headers.update(mysa_stuff.CLIENT_HEADERS)

    # This endpoint has the "real" device models, even after faking them in /devices
    r = sess.get(f'{BASE_URL}/users')
    r.raise_for_status()
    user = r.json(object_hook=slurpy).User
    r = sess.get(f'{BASE_URL}/devices')
    devicesobj = r.json(object_hook=slurpy).DevicesObj
    real_models = {k: v.deviceType for k, v in user.DevicesPaired.State.BB.items() if k in devicesobj}

    # Find applicable device(s)
    if args.device:
        for did in args.device:
            if did not in real_models:
                p.error(f'Mysa thermostat with ID (MAC address) of {args.device} not found in your account.')
            elif (m := real_models[did]) != 'BB-V2-0-L':
                p.error(f'Your Mysa thermostat {args.device} is model {m}, not BB-V2-0-L (Mysa V2 Lite). This trick is not applicable to it.')
        devices = args.device
    else:
        devices = [k for k, m in real_models.items() if m == 'BB-V2-0-L']
        if not devices:
            p.error(f'No Mysa thermostats with model BB-V2-0-L (Mysa V2 Lite) found in your account.')
        else:
            print(f'Found {len(devices)} with model BB-V2-0-L (Mysa V2 Lite) in your account.')
            for did in devices:
                print(f'  {did}: {devicesobj[did].Name}')

    if args.reset:
        for did in devices:
            r = sess.post(f'{BASE_URL}/devices/{did}', json={'Model': 'BB-V2-0-L'})
            r.raise_for_status()
            print(f'Restored Mysa thermostat {args.device} to model BB-V2-0-L')
        p.exit(0)

    # Check firmware versions
    r = sess.get(f'{BASE_URL}/devices/firmware')
    r.raise_for_status()
    firmware = {k: v.InstalledVersion for k, v in r.json(object_hook=slurpy).Firmware.items()}
    for did in devices:
        if (v := firmware.get(did)) is None:
            print(f'WARNING: Your Mysa thermostat {did} has an unknown firmware version. This might not work.\n'
                '  Please report success or failure at https://github.com/dlenski/mysotherm/issues or via email', file=stderr)
        elif not (vmin := (3, 13, 1, 25)) <= tuple(int(x) for x in v.split('.')) <= (vmax := (3, 17, 4, 1)):
            print(f'WARNING: Your Mysa thermostat {did} is on firmware version {v}. This has only been tested with v{'.'.join(map(str, vmin))}-v{'.'.join(map(str, vmax))}'
                '  Please report success or failure at https://github.com/dlenski/mysotherm/issues or via email', file=stderr)

    # Connect to MQTT-over-WebSockets endpoint
    cred = u.get_credentials(identity_pool_id=mysa_stuff.IDENTITY_POOL_ID)
    signed_mqtt_url = mysa_stuff.sigv4_sign_mqtt_url(cred)
    urlp = urlparse(signed_mqtt_url)
    cid = str(uuid1)
    with websockets.sync.client.connect(
        urlp._replace(scheme='wss').geturl(),
        subprotocols=('mqtt',),
        # Seemingly not necessary for the server, but Mysa official client adds all this:
        origin=urlp._replace(path='', params='', query='', fragment='').geturl(),
        additional_headers={'accept-encoding': 'gzip'},
        user_agent_header=sess.headers['user-agent'],
    ) as ws:
        connected_at = time()
        ws.send(mqttpacket.connect(str(uuid1()), 60))
        timeout = time() + 60
        pkt = mqttpacket.parse_one(ws.recv())
        assert isinstance(pkt, mqttpacket.ConnackPacket)

        # Subscribe to feeds for these devices
        for ii, did in enumerate(devices, 1):
            ws.send(mqttpacket.subscribe(ii, [
                mqttpacket.SubscriptionSpec(f'/v1/dev/{did}/out', 0x01),
                mqttpacket.SubscriptionSpec(f'/v1/dev/{did}/in', 0x01),
                mqttpacket.SubscriptionSpec(f'/v1/dev/{did}/batch', 0x01)
                ]))
            timeout = time() + 60
            pkt = mqttpacket.parse_one(ws.recv())
            assert isinstance(pkt, mqttpacket.SubackPacket) and pkt.packet_id == ii

        try:
            last_sensor_temp = {}

            # Do the "magic upgrades"
            for did in devices:
                r = sess.post(f'{BASE_URL}/devices/{did}', json=
                    {'Model': 'BB-V1-1', 'MaxCurrent': args.current, 'Current': args.current})  # do I need/want both?
                r.raise_for_status()
                # ... and stash the latest SensorTemp
                last_sensor_temp[did] = sess.get(f'{BASE_URL}/devices/state/{did}').json(object_hook=slurpy).DeviceState.SensorTemp.v

            # Await messages and translate as needed
            while True:
                try:
                    pkt = mqttpacket.parse_one(ws.recv(timeout - time()))
                    logger.debug(f'Received packet: {pkt}')
                except TimeoutError:
                    pkt = None
                else:
                    replied = translate_packet(ws, pkt, args.current, last_sensor_temp)
                    if replied is not None:
                        timeout = replied + 60

                if time() > timeout:
                    ws.send(mqttpacket.pingreq())
                    logger.debug(f"Sent PINGREQ keepalive packet")
                    timeout = time() + 60

        except websockets.exceptions.ConnectionClosed as exc:
            print(f"Websockets connection closed after {int(time() - connected_at)}s (rcvd={exc.rcvd}, sent={exc.sent})...")

        except KeyboardInterrupt:
            print(f"Got interrupt (Ctrl-C) after {int(time() - connected_at)} s...")

        finally:
            print(f'Restoring Mysa V2 Lite thermostats to normal state...')
            for did in devices:
                r = sess.post(f'{BASE_URL}/devices/{did}', json={'Model': 'BB-V2-0-L'})
                r.raise_for_status()
                print(f'Restored Mysa thermostat {did} to model BB-V2-0-L')


if __name__ == '__main__':
    main()
