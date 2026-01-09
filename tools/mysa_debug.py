#!/usr/bin/env python3
"""
Mysa Debug Tool

Interactive command-line utility for testing and debugging Mysa device
communication via HTTP and MQTT protocols.

Usage:
    cd tools
    python mysa_debug.py

See docs/MYSA_DEBUG.md for detailed usage instructions.
"""
import asyncio
import json
import logging
import sys
import os
import time
import ssl
import getpass
from datetime import datetime
from urllib.parse import urlparse
from uuid import uuid1

# Add custom_components directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
mysa_path = os.path.join(parent_dir, 'custom_components', 'mysa')
lib_path = os.path.join(mysa_path, 'lib')
sys.path.insert(0, mysa_path)
sys.path.insert(0, lib_path)

try:
    from mysotherm import auth, mysa_stuff, aws
    import mqtt_packet
except ImportError as e:
    print(f"\nCRITICAL: Could not import required modules: {e}")
    print("Make sure you're running from the tools/ directory")
    sys.exit(1)

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False
    print("Note: Install prompt_toolkit for better input experience: pip install prompt_toolkit")

import websockets
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
_LOGGER = logging.getLogger(__name__)


class MysaDebugTool:
    def __init__(self, auth_path):
        self.auth_path = auth_path
        self._user_obj = None
        self.devices = {}
        self.ws = None
        self.user_id = None
        self.session = None
        self.sniff_mode = False

    async def run(self):
        print("\n" + "="*60)
        print("        MYSA DEBUG TOOL - HTTP/MQTT Sender")
        print("="*60)
        
        # Authenticate
        if not await self.authenticate():
            return
        
        # Fetch devices
        await self.fetch_devices()
        
        # Start MQTT and command loop
        mqtt_task = asyncio.create_task(self.mqtt_loop())
        cmd_task = asyncio.create_task(self.command_loop())
        
        await cmd_task
        
        print("Stopping MQTT...")
        mqtt_task.cancel()
        try:
            await mqtt_task
        except asyncio.CancelledError:
            pass

    async def authenticate(self):
        bsess = aws.boto3.session.Session(region_name=mysa_stuff.REGION)
        
        # Try saved credentials
        if os.path.exists(self.auth_path):
            try:
                with open(self.auth_path, 'r') as f:
                    saved = json.load(f)
                print(f"Using saved credentials from {self.auth_path}")
                self._user_obj = auth.login(saved['username'], saved['password'], bsess, cf=None)
                self.session = requests.Session()
                self.session.auth = mysa_stuff.auther(self._user_obj)
                self.session.headers.update(mysa_stuff.CLIENT_HEADERS)
                
                # Get user ID
                r = self.session.get(f"{mysa_stuff.BASE_URL}/users")
                r.raise_for_status()
                self.user_id = r.json().get("User", {}).get("Id", self._user_obj.id_claims['cognito:username'])
                print(f"✓ Authenticated as {self.user_id[:8]}...")
                return True
            except Exception as e:
                print(f"Saved auth failed: {e}")
        
        # Manual login
        username = input("Mysa Email: ").strip()
        password = getpass.getpass("Mysa Password: ").strip()
        
        try:
            self._user_obj = auth.login(username, password, bsess, cf=None)
            self.session = requests.Session()
            self.session.auth = mysa_stuff.auther(self._user_obj)
            self.session.headers.update(mysa_stuff.CLIENT_HEADERS)
            
            r = self.session.get(f"{mysa_stuff.BASE_URL}/users")
            r.raise_for_status()
            self.user_id = r.json().get("User", {}).get("Id", self._user_obj.id_claims['cognito:username'])
            
            # Save credentials
            with open(self.auth_path, 'w') as f:
                json.dump({'username': username, 'password': password}, f)
            os.chmod(self.auth_path, 0o600)
            print(f"✓ Authenticated and saved to {self.auth_path}")
            return True
        except Exception as e:
            print(f"✗ Auth failed: {e}")
            return False

    async def fetch_devices(self):
        print("Fetching devices...")
        r = self.session.get(f"{mysa_stuff.BASE_URL}/devices")
        r.raise_for_status()
        data = r.json()
        dev_list = data.get('DevicesObj', data.get('Devices', []))
        if isinstance(dev_list, list):
            self.devices = {d['Id']: d for d in dev_list}
        else:
            self.devices = dev_list
        print(f"✓ Found {len(self.devices)} devices\n")
        self.list_devices()

    def list_devices(self):
        for i, (did, d) in enumerate(self.devices.items(), 1):
            model = d.get('Model', 'Unknown')
            name = d.get('Name', 'Unnamed')
            print(f"  {i}. {name} ({did}) - {model}")
        print()

    async def command_loop(self):
        # Create prompt session if prompt_toolkit is available
        session = PromptSession() if HAS_PROMPT_TOOLKIT else None
        
        self.print_help()
        
        while True:
            try:
                if HAS_PROMPT_TOOLKIT:
                    # prompt_toolkit keeps prompt at bottom while output scrolls above
                    with patch_stdout():
                        cmd_raw = await session.prompt_async("CMD> ")
                else:
                    # Fallback to standard input
                    cmd_raw = await asyncio.get_event_loop().run_in_executor(None, input, "CMD> ")
                
                parts = cmd_raw.strip().split(maxsplit=2)
                if not parts:
                    continue
                
                cmd = parts[0].lower()
                
                if cmd in ('q', 'quit', 'exit'):
                    print("Goodbye!")
                    return
                elif cmd == 'ls':
                    self.list_devices()
                elif cmd == 'sniff':
                    self.sniff_mode = not self.sniff_mode
                    print(f"Sniff Mode: {'ON' if self.sniff_mode else 'OFF'}")
                elif cmd == 'examples':
                    self.show_examples()
                elif cmd == 'help' or cmd == '?':
                    self.print_help()
                elif cmd == 'http' and len(parts) >= 3:
                    await self.send_http(parts[1], parts[2])
                elif cmd == 'mqtt' and len(parts) >= 3:
                    await self.send_mqtt_raw(parts[1], parts[2])
                elif cmd == 'state' and len(parts) >= 2:
                    await self.show_state(parts[1])
                else:
                    print("Unknown command. Type 'help' or 'examples' for help.")
            except Exception as e:
                print(f"Error: {e}")

    def print_help(self):
        print("\n" + "-"*50)
        print("Commands:")
        print("  ls                     - List devices")
        print("  state <DID>            - Show raw device state")
        print("  http <DID> <JSON>      - Send HTTP POST to /devices/<DID>")
        print("  mqtt <DID> <JSON>      - Send MQTT command (wrapped)")
        print("  sniff                  - Toggle MQTT sniffer mode")
        print("  examples               - Show example payloads")
        print("  q                      - Quit")
        print("-"*50)

    def show_examples(self):
        did = list(self.devices.keys())[0] if self.devices else "DEVICE_ID"
        
        print("\n" + "="*60)
        print("                   EXAMPLE COMMANDS")
        print("="*60)
        
        print("\n--- HTTP Examples (POST /devices/<DID>) ---")
        print(f'  http {did} {{"ButtonState": 1}}       # Lock buttons')
        print(f'  http {did} {{"ButtonState": 0}}       # Unlock buttons')
        print(f'  http {did} {{"ecoMode": "0"}}         # Eco ON (inverted!)')
        print(f'  http {did} {{"ecoMode": "1"}}         # Eco OFF')
        print(f'  http {did} {{"ProximityMode": true}}  # Proximity wake ON')
        print(f'  http {did} {{"ProximityMode": false}} # Proximity wake OFF')
        print(f'  http {did} {{"AutoBrightness": true}} # Auto brightness ON')
        print(f'  http {did} {{"MinBrightness": 20}}    # Idle brightness (0-100)')
        print(f'  http {did} {{"MaxBrightness": 100}}   # Active brightness (0-100)')
        print(f'  http {did} {{"Format": "celsius"}}    # Temperature unit')
        print(f'  http {did} {{"Name": "New Name"}}     # Rename device')
        
        print("\n--- MQTT Thermostat Examples (type=4 for BB-V2) ---")
        print(f'  mqtt {did} {{"cmd":[{{"sp":21,"stpt":21,"a_sp":21,"tm":-1}}],"type":4,"ver":1}}')
        print("       ^ Set temperature to 21°C")
        print(f'  mqtt {did} {{"cmd":[{{"md":3,"tm":-1}}],"type":4,"ver":1}}')
        print("       ^ Set HVAC mode to Heat (md: 1=Off, 3=Heat)")
        print(f'  mqtt {did} {{"cmd":[{{"lk":1,"tm":-1}}],"type":4,"ver":1}}')
        print("       ^ Lock buttons (lk: 0=Unlock, 1=Lock)")
        print(f'  mqtt {did} {{"cmd":[{{"pr":1,"tm":-1}}],"type":4,"ver":1}}')
        print("       ^ Proximity mode (pr: 0=Off, 1=On)")
        print(f'  mqtt {did} {{"cmd":[{{"tm":-1,"br":{{"a_b":1,"a_br":100,"i_br":50,"a_dr":60,"i_dr":30}}}}],"type":4,"ver":1}}')
        print("       ^ Brightness (a_b=auto, a_br=active%, i_br=idle%, a_dr/i_dr=duration)")
        
        print("\n--- MQTT AC Examples (type=2 for AC-V1) ---")
        print(f'  mqtt {did} {{"cmd":[{{"sp":22,"stpt":22,"tm":-1}}],"type":2,"ver":1}}')
        print("       ^ Set AC temperature to 22°C")
        print(f'  mqtt {did} {{"cmd":[{{"md":4,"tm":-1}}],"type":2,"ver":1}}')
        print("       ^ Set AC mode (md: 1=Off, 2=Auto, 3=Heat, 4=Cool, 5=Fan, 6=Dry)")
        print(f'  mqtt {did} {{"cmd":[{{"fn":7,"tm":-1}}],"type":2,"ver":1}}')
        print("       ^ Set fan speed (fn: 1=Auto, 3=Low, 5=MedLow, 7=Med, 8=High, 12=Sleep)")
        print(f'  mqtt {did} {{"cmd":[{{"ss":3,"tm":-1}}],"type":2,"ver":1}}')
        print("       ^ Set vertical swing (ss: 3=Auto, 4-9=Position 1-6)")
        print(f'  mqtt {did} {{"cmd":[{{"ssh":3,"tm":-1}}],"type":2,"ver":1}}')
        print("       ^ Set horizontal swing (ssh: 3=Auto, 4-9=Position 1-6)")
        print(f'  mqtt {did} {{"cmd":[{{"it":1,"tm":-1}}],"type":2,"ver":1}}')
        print("       ^ Climate+ mode (it: 0=Off, 1=On - uses Mysa temp sensor)")
        
        print("\n--- Device Type Values ---")
        print("  type=1  BB-V1 (Baseboard V1)")
        print("  type=2  AC-V1 (AC Controller)")
        print("  type=3  INF-V1 (In-Floor Heating)")
        print("  type=4  BB-V2 (Baseboard V2)")
        print("  type=5  BB-V2-L (Baseboard V2 Lite)")
        print()

    async def show_state(self, device_ref):
        did = self._resolve_device(device_ref)
        if not did:
            return
        
        print(f"\nFetching state for {did}...")
        
        # Device settings
        r_dev = self.session.get(f"{mysa_stuff.BASE_URL}/devices/{did}")
        r_dev.raise_for_status()
        
        # Live state
        r_state = self.session.get(f"{mysa_stuff.BASE_URL}/devices/state")
        r_state.raise_for_status()
        states = r_state.json().get('DeviceStatesObj', r_state.json().get('DeviceStates', []))
        if isinstance(states, list):
            states = {d['Id']: d for d in states}
        
        print("\n--- Device Settings (HTTP) ---")
        print(json.dumps(r_dev.json(), indent=2))
        
        print("\n--- Live State (HTTP) ---")
        print(json.dumps(states.get(did, {}), indent=2))

    async def send_http(self, device_ref, json_str):
        did = self._resolve_device(device_ref)
        if not did:
            return
        
        try:
            payload = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            return
        
        url = f"{mysa_stuff.BASE_URL}/devices/{did}"
        print(f"\nPOST {url}")
        print(f"Body: {json.dumps(payload)}")
        
        r = self.session.post(url, json=payload)
        print(f"Response [{r.status_code}]: {r.text}")
        
        # Send MsgType 6 nudge
        await self.notify_settings_changed(did)

    async def send_mqtt_raw(self, device_ref, json_str):
        did = self._resolve_device(device_ref)
        if not did:
            return
        
        if not self.ws:
            print("MQTT not connected!")
            return
        
        try:
            body = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            return
        
        # Wrap in MsgType 44
        timestamp = int(time.time())
        wrapper = {
            "Timestamp": timestamp,
            "body": body,
            "dest": {"ref": did, "type": 1},
            "id": int(time.time() * 1000),
            "msg": 44,
            "resp": 2,
            "src": {"ref": self.user_id, "type": 100},
            "time": timestamp,
            "ver": "1.0"
        }
        
        safe_did = did.replace(":", "").lower()
        topic = f"/v1/dev/{safe_did}/in"
        json_payload = json.dumps(wrapper)
        
        print(f"\nMQTT PUBLISH {topic}")
        print(f"Body: {json.dumps(body, indent=2)}")
        
        try:
            pub_pkt = mqtt_packet.publish(topic, False, 1, False, packet_id=2, payload=json_payload.encode())
            await self.ws.send(pub_pkt)
            print("✓ Sent!")
        except Exception as e:
            print(f"✗ Send failed: {e}")
        
        await self.notify_settings_changed(did)

    async def notify_settings_changed(self, did):
        if not self.ws:
            return
        timestamp = int(time.time())
        body = {
            "Device": did.upper(),
            "EventType": 0,
            "MsgType": 6,
            "Timestamp": timestamp
        }
        safe_did = did.replace(":", "").lower()
        topic = f"/v1/dev/{safe_did}/in"
        try:
            pub_pkt = mqtt_packet.publish(topic, False, 1, False, packet_id=3, payload=json.dumps(body).encode())
            await self.ws.send(pub_pkt)
        except Exception:
            pass  # Notification is best-effort

    def _resolve_device(self, ref):
        """Resolve device by number or ID."""
        try:
            num = int(ref)
            devices_list = list(self.devices.keys())
            if 1 <= num <= len(devices_list):
                return devices_list[num - 1]
        except ValueError:
            pass
        
        clean = ref.replace(":", "").lower()
        for did in self.devices:
            if did.replace(":", "").lower() == clean:
                return did
        
        print(f"Device '{ref}' not found")
        return None

    async def mqtt_loop(self):
        def parse_one(data):
            if not isinstance(data, bytearray):
                data = bytearray(data)
            msgs = []
            mqtt_packet.parse(data, msgs)
            return msgs[0] if msgs else None

        while True:
            try:
                self._user_obj.check_token()
                cred = self._user_obj.get_credentials(identity_pool_id=mysa_stuff.IDENTITY_POOL_ID)
                signed_url = mysa_stuff.sigv4_sign_mqtt_url(cred)
                ws_url = urlparse(signed_url)._replace(scheme='wss').geturl()
                
                ssl_context = ssl.create_default_context()
                headers = {'user-agent': 'okhttp/4.11.0'}
                
                async with websockets.connect(ws_url, subprotocols=['mqtt'],
                                              ssl=ssl_context, additional_headers=headers,
                                              ping_interval=None) as ws:
                    self.ws = ws
                    print("⚡ MQTT Connected!")
                    
                    await ws.send(mqtt_packet.connect(str(uuid1()), 60))
                    await ws.recv()  # Connack
                    
                    # Subscribe to all devices
                    subs = []
                    for did in self.devices:
                        safe_did = did.replace(":", "").lower()
                        subs.append(mqtt_packet.SubscriptionSpec(f'/v1/dev/{safe_did}/out', 0x01))
                        subs.append(mqtt_packet.SubscriptionSpec(f'/v1/dev/{safe_did}/in', 0x01))
                    
                    if subs:
                        await ws.send(mqtt_packet.subscribe(1, subs))
                        await ws.recv()  # Suback
                    
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                            pkt = parse_one(msg)
                            
                            if isinstance(pkt, mqtt_packet.PublishPacket) and self.sniff_mode:
                                self._print_sniff(pkt)
                            elif hasattr(pkt, 'pkt_type') and pkt.pkt_type == mqtt_packet.MQTT_PACKET_PINGRESP:
                                pass
                        except asyncio.TimeoutError:
                            await ws.send(mqtt_packet.pingreq())
                            
            except Exception as e:
                print(f"⚠ MQTT Error: {e}")
                self.ws = None
                await asyncio.sleep(5)

    def _print_sniff(self, pkt):
        topic_parts = pkt.topic.split('/')
        direction = topic_parts[-1] if topic_parts else "?"
        arrow = "→" if direction == "in" else "←"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        try:
            payload = json.loads(pkt.payload)
            msg_type = payload.get('msg') or payload.get('MsgType')
            print(f"\n[{timestamp}] [SNIFF {arrow}] MsgType {msg_type}: {json.dumps(payload, indent=2)}")
        except:
            print(f"\n[{timestamp}] [SNIFF {arrow}] {pkt.payload.decode()}")


if __name__ == "__main__":
    auth_path = os.path.expanduser("~/.mysa_debug_auth.json")
    tool = MysaDebugTool(auth_path)
    try:
        asyncio.run(tool.run())
    except KeyboardInterrupt:
        print("\n✓ Stopped")
