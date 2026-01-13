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
import getpass
from datetime import datetime

# Add custom_components directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
mysa_path = os.path.join(parent_dir, 'custom_components', 'mysa')
sys.path.insert(0, mysa_path)

try:
    from mysa_auth import (
        login, auther,
        REGION, IDENTITY_POOL_ID, CLIENT_HEADERS, BASE_URL,
    )
    from mysa_mqtt import (
        refresh_and_sign_url, MqttConnection,
    )
    from const import MQTT_PING_INTERVAL
    import mqtt
    import boto3
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
        self.username = None
        self.password = None
        self.sniff_mode = False
        self.sniff_filter = None  # Filter by device ID (None = all)

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
        bsess = boto3.session.Session(region_name=REGION)
        
        # Try saved credentials
        if os.path.exists(self.auth_path):
            try:
                with open(self.auth_path, 'r') as f:
                    saved = json.load(f)
                print(f"Using saved credentials from {self.auth_path}")
                self.username = saved['username']
                self.password = saved['password']
                self._user_obj = login(self.username, self.password, bsess=bsess)
                self.session = requests.Session()
                self.session.auth = auther(self._user_obj)
                self.session.headers.update(CLIENT_HEADERS)
                
                # Get user ID
                r = self.session.get(f"{BASE_URL}/users")
                r.raise_for_status()
                self.user_id = r.json().get("User", {}).get("Id", self._user_obj.id_claims['cognito:username'])
                print(f"✓ Authenticated as {self.user_id[:8]}...")
                return True
            except Exception as e:
                print(f"Saved auth failed: {e}")
        
        # Manual login
        self.username = input("Mysa Email: ").strip()
        self.password = getpass.getpass("Mysa Password: ").strip()
        
        try:
            self._user_obj = login(self.username, self.password, bsess=bsess)
            self.session = requests.Session()
            self.session.auth = auther(self._user_obj)
            self.session.headers.update(CLIENT_HEADERS)
            
            r = self.session.get(f"{BASE_URL}/users")
            r.raise_for_status()
            self.user_id = r.json().get("User", {}).get("Id", self._user_obj.id_claims['cognito:username'])
            
            # Save credentials
            with open(self.auth_path, 'w') as f:
                json.dump({'username': self.username, 'password': self.password}, f)
            os.chmod(self.auth_path, 0o600)
            print(f"✓ Authenticated and saved to {self.auth_path}")
            return True
        except Exception as e:
            print(f"✗ Auth failed: {e}")
            return False

    async def fetch_devices(self):
        print("Fetching devices...")
        r = self.session.get(f"{BASE_URL}/devices")
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
                elif cmd in ('ls', 'list'):
                    self.list_devices()
                elif cmd == 'sniff':
                    if len(parts) > 1:
                         # Filter mode
                         target = self._resolve_device(parts[1])
                         if target:
                             self.sniff_mode = True
                             self.sniff_filter = target
                             print(f"Sniff Mode: ON (Filtered to {target})")
                         else:
                             print(f"Invalid device ref: {parts[1]}")
                    else:
                        # Toggle global
                        if self.sniff_mode and self.sniff_filter:
                            # If filtered, clear filter but keep sniff on (or toggle off? context dependent)
                            # User expectation: 'sniff' toggles.
                            self.sniff_mode = False
                            self.sniff_filter = None
                            print("Sniff Mode: OFF")
                        else:
                            self.sniff_mode = not self.sniff_mode
                            self.sniff_filter = None
                            print(f"Sniff Mode: {'ON' if self.sniff_mode else 'OFF'}")
                elif cmd in ('examples', 'ex'):
                    self.show_examples()
                elif cmd in ('help', '?'):
                    self.print_help()
                elif cmd == 'advanced':
                    await self.advanced_menu()
                elif cmd == 'homes':
                    await self.show_homes()
                elif cmd == 'users':
                    await self.show_users()
                elif cmd == 'http' and len(parts) >= 3:
                    await self.send_http(parts[1], parts[2])
                elif cmd == 'mqtt' and len(parts) >= 3:
                    await self.send_mqtt_raw(parts[1], parts[2])
                elif cmd == 'state' and len(parts) >= 2:
                    await self.show_state(parts[1])
                else:
                    print("Unknown command. Type 'help' or 'ex' for available commands.")
            except Exception as e:
                print(f"Error: {e}")

    def print_help(self):
        """Print available commands."""
        print("\n--- Mysa Debug Tool Help ---")
        
        print("\n[ Basic Commands ]")
        print("  list, ls          List devices")
        print("  help, ?           Show this help")
        print("  examples, ex      Show command examples")
        print("  quit, exit        Exit tool")
        
        print("\n[ Device Information ]")
        print("  state <ID>        Show full device state (HTTP + MQTT)")
        print("  homes             Show /homes API response (Zones, ERate)")
        print("  users             Show /users API response (User Info, Devices)")
        print("  sniff [ID]        Toggle MQTT sniffing (Optional: Filter by ID)")

        print("\n[ Device Control ]")
        print("  http <ID> <JSON>  Send HTTP command directly")
        print("  mqtt <ID> <JSON>  Send MQTT command directly")
        
        print("\n[ Advanced ]")
        print("  advanced          Open advanced menu (Conversions, Dangerous Ops)")
        print("    ↳ Convert BB-V2-0-L (Lite) -> BB-V2-0 (Full)")
        print("    ↳ Killer Ping (Reboot to pairing)")
        print()

    async def show_homes(self):
        """Fetch and display /homes API response."""
        print("\nFetching /homes...")
        try:
            r = self.session.get(f"{BASE_URL}/homes")
            r.raise_for_status()
            data = r.json()
            print("\n--- /homes Response ---")
            print(json.dumps(data, indent=2))
            
            # Extract and highlight HOME_UUIDs and Zones
            homes = data.get('Homes', data.get('homes', []))
            if homes:
                print("\n--- Homes & Zones ---")
                for i, home in enumerate(homes, 1):
                    home_id = home.get('Id', home.get('id', home.get('HomeId', 'Unknown')))
                    home_name = home.get('Name', home.get('name', 'Unnamed'))
                    erate = home.get('ERate', 'N/A')
                    print(f"\n  {i}. 🏠 {home_name}")
                    print(f"     Home UUID: {home_id}")
                    print(f"     ERate: ${erate}/kWh")
                    
                    # Display zones
                    zones = home.get('Zones', [])
                    if zones:
                        print("     Zones:")
                        for zone in zones:
                            zone_id = zone.get('Id', 'Unknown')
                            zone_name = zone.get('Name', 'Unnamed')
                            print(f"       • {zone_name}: {zone_id}")
        except Exception as e:
            print(f"Failed to fetch /homes: {e}")

    async def show_users(self):
        """Fetch and display /users API response."""
        print("\nFetching /users...")
        try:
            r = self.session.get(f"{BASE_URL}/users")
            r.raise_for_status()
            data = r.json()
            print("\n--- /users Response ---")
            print(json.dumps(data, indent=2))
            
            # Extract key user info
            user = data.get('User', data.get('user', {}))
            if user:
                cognito = user.get('CognitoAttrs', {})
                print("\n--- User Info ---")
                print(f"  User ID: {user.get('Id', 'Unknown')}")
                print(f"  Email: {cognito.get('email', 'Unknown')}")
                print(f"  Name: {cognito.get('name', cognito.get('given_name', '') + ' ' + cognito.get('family_name', ''))}")
                print(f"  Language: {user.get('LanguagePreference', 'Unknown')}")
                print(f"  Primary Home: {user.get('PrimaryHome', 'Unknown')}")
                print(f"  ERate: ${user.get('ERate', 'N/A')}/kWh")
                print(f"  App Version: {user.get('LastAppVersion', 'Unknown')}")
                
                # DevicesPaired summary
                paired = user.get('DevicesPaired', {}).get('State', {})
                if paired:
                    print("\n--- Paired Devices ---")
                    for category, devices in paired.items():
                        if devices:
                            print(f"  {category}:")
                            for did, info in devices.items():
                                dtype = info.get('deviceType', 'Unknown')
                                print(f"    • {did}: {dtype}")
        except Exception as e:
            print(f"Failed to fetch /users: {e}")

    async def advanced_menu(self):
        """Show advanced operations menu."""
        print("\n" + "="*60)
        print("              ⚠️  ADVANCED OPERATIONS ⚠️")
        print("="*60)
        print("\n⚠️  WARNING: These operations modify device firmware settings.")
        print("   They may void your warranty, brick your device, or cause")
        print("   other unexpected behavior. We are NOT responsible for any")
        print("   issues that may arise from using these features.")
        print("\n   USE AT YOUR OWN RISK!\n")
        print("-"*60)
        print("Options:")
        print("  1. Convert BB-V2-0-L to BB-V2-0 (Lite to Full)")
        print("  2. Killer Ping - Restart device into pairing mode")
        print("  0. Cancel / Go back")
        print("-"*60)
        
        choice = input("\nSelect option: ").strip()
        
        if choice == '1':
            await self.convert_lite_to_full()
        elif choice == '2':
            await self.killer_ping()
        elif choice == '0':
            print("Cancelled.")
        else:
            print("Invalid option.")

    async def convert_lite_to_full(self):
        """Convert a BB-V2-0-L (Lite) device to BB-V2-0 (Full) model."""
        print("\n" + "="*60)
        print("        BB-V2-0-L → BB-V2-0 CONVERSION")
        print("="*60)
        
        # List Lite devices only
        lite_devices = [(did, d) for did, d in self.devices.items() 
                        if 'BB-V2-0-L' in d.get('Model', '') or 'V2-0-L' in d.get('Model', '')]
        
        if not lite_devices:
            print("\n❌ No devices found compatible with the magic upgrade.")
            print("   This feature only works with BB-V2-0-L (Lite) thermostats.")
            return
        
        print("\nDetected BB-V2-0-L (Lite) devices:")
        for i, (did, d) in enumerate(lite_devices, 1):
            print(f"  {i}. {d.get('Name', 'Unnamed')} ({did}) - {d.get('Model')}")
        
        print("\n⚠️  This will change the device's Model to 'BB-V2-0'.")
        print("   This unlocks V2 features but may cause issues.")
        print("   You will need to power-cycle the thermostat after.\n")
        
        device_ref = input("Enter device number or ID (or 'cancel'): ").strip()
        if device_ref.lower() in ('cancel', 'c', ''):
            print("Cancelled.")
            return
        
        did = self._resolve_device(device_ref)
        if not did:
            return
        
        device = self.devices.get(did, {})
        old_model = device.get('Model', 'Unknown')
        
        print(f"\n🎯 Target: {device.get('Name', 'Unknown')} ({did})")
        print(f"   Current Model: {old_model}")
        print(f"   New Model: BB-V2-0")
        
        confirm = input("\n⚠️  Type 'YES I UNDERSTAND' to proceed: ").strip()
        if confirm != 'YES I UNDERSTAND':
            print("Confirmation failed. Cancelled.")
            return
        
        # Send the conversion request
        print("\nSending model change request...")
        url = f"{BASE_URL}/devices/{did}"
        try:
            r = self.session.post(url, json={'Model': 'BB-V2-0'})
            r.raise_for_status()
            
            print("\n" + "="*60)
            print("           🔓 DEVICE UNLOCKED 🔓")
            print("="*60)
            print(f"\n   Your {old_model} now identifies as BB-V2-0.")
            print("\n   \"With great power comes great heating bills.\"")
            print("\n⚠️  Please power-cycle your thermostat to complete")
            print("   the transformation.")
            print("\n   No refunds. May void warranty. YOLO.")
            print("="*60 + "\n")
            
            # Refresh devices
            await self.fetch_devices()
            
        except Exception as e:
            print(f"\n✗ Conversion failed: {e}")
            print("  The device may not support this operation.")

    async def killer_ping(self):
        """Send killer ping to restart device into pairing mode."""
        print("\n" + "="*60)
        print("           💀 KILLER PING 💀")
        print("="*60)
        print("\n⚠️  WARNING: This will RESTART the device and put it")
        print("   into PAIRING MODE. The device will disconnect from")
        print("   your network and need to be re-paired!")
        print("\n   Only use this if you need to re-pair a device.\n")
        
        self.list_devices()
        
        device_ref = input("\nEnter device number or ID (or 'cancel'): ").strip()
        if device_ref.lower() in ('cancel', 'c', ''):
            print("Cancelled.")
            return
        
        did = self._resolve_device(device_ref)
        if not did:
            return
        
        device = self.devices.get(did, {})
        print(f"\n🎯 Target: {device.get('Name', 'Unknown')} ({did})")
        print(f"   Model: {device.get('Model', 'Unknown')}")
        
        confirm = input("\n⚠️  Type 'KILL' to send killer ping: ").strip()
        if confirm != 'KILL':
            print("Confirmation failed. Cancelled.")
            return
        
        if not self.ws:
            print("\n✗ MQTT not connected. Cannot send killer ping.")
            return
        
        # Build killer ping payload
        import time as time_module
        payload = {
            "Device": did,
            "Timestamp": int(time_module.time()),
            "MsgType": 5,
            "EchoID": 1
        }
        
        print("\nSending killer ping...")
        topic = f"/v1/dev/{did.replace(':', '').lower()}/in"
        
        try:
            pub_pkt = mqtt.publish(topic, False, 1, False, packet_id=99, payload=json.dumps(payload).encode())
            await self.ws.send(pub_pkt)
            
            print("\n" + "="*60)
            print("           💀 KILLER PING SENT 💀")
            print("="*60)
            print(f"\n   Device {device.get('Name', did)} should restart shortly.")
            print("   Look for the device in pairing mode on your network.")
            print("\n   May the force be with you.")
            print("="*60 + "\n")
            
        except Exception as e:
            print(f"\n✗ Failed to send killer ping: {e}")

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
        r_dev = self.session.get(f"{BASE_URL}/devices/{did}")
        r_dev.raise_for_status()
        
        # Live state
        r_state = self.session.get(f"{BASE_URL}/devices/state")
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
        
        url = f"{BASE_URL}/devices/{did}"
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
            pub_pkt = mqtt.publish(topic, False, 1, False, packet_id=2, payload=json_payload.encode())
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
            pub_pkt = mqtt.publish(topic, False, 1, False, packet_id=3, payload=json.dumps(body).encode())
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
        """MQTT listener loop using MqttConnection context manager."""
        while True:
            try:
                # Use shared token refresh logic
                try:
                    signed_url, new_user_obj = refresh_and_sign_url(
                        self._user_obj, self.username, self.password
                    )
                    if new_user_obj is not self._user_obj:
                        self._user_obj = new_user_obj
                        print("✓ Re-authenticated successfully")
                except Exception as e:
                    print(f"⚠ Auth failed: {e}")
                    await asyncio.sleep(5)
                    continue
                
                # Use MqttConnection context manager
                async with MqttConnection(signed_url, list(self.devices.keys())) as conn:
                    self.ws = conn.websocket
                    print("⚡ MQTT Connected!")
                    
                    while conn.connected:
                        pkt = await conn.receive(timeout=MQTT_PING_INTERVAL + 5)
                        
                        if pkt is None:
                            # Timeout - send ping
                            await conn.send_ping()
                        elif isinstance(pkt, mqtt.PublishPacket) and self.sniff_mode:
                            self._print_sniff(pkt)
                        elif hasattr(pkt, 'pkt_type') and pkt.pkt_type == mqtt.MQTT_PACKET_PINGRESP:
                            pass
                            
            except Exception as e:
                print(f"⚠ MQTT Error: {e}")
                self.ws = None
                await asyncio.sleep(5)

    def _print_sniff(self, pkt):
        topic_parts = pkt.topic.split('/')
        
        # Filter logic
        if self.sniff_filter:
            did = "unknown"
            if len(topic_parts) >= 4:
                did = topic_parts[3]
            if did.lower() != self.sniff_filter.replace(":", "").lower():
                return

        direction = topic_parts[-1] if topic_parts else "?"
        arrow = "→" if direction == "in" else "←"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        try:
            payload = json.loads(pkt.payload)
            msg_type = payload.get('msg') or payload.get('MsgType')
            print(f"\n[{timestamp}] [SNIFF {arrow}] MsgType {msg_type}: {json.dumps(payload, indent=2)}")
        except:
            print(f"\n[{timestamp}] [SNIFF {arrow}] {pkt.payload.decode(errors='ignore')}")


if __name__ == "__main__":
    auth_path = os.path.expanduser("~/.mysa_debug_auth.json")
    tool = MysaDebugTool(auth_path)
    try:
        asyncio.run(tool.run())
    except KeyboardInterrupt:
        print("\n✓ Stopped")
