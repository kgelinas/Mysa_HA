#!/usr/bin/env python3
"""
Mysa Debug Tool

Interactive command-line utility for testing and debugging Mysa device
communication via HTTP and MQTT protocols.

Includes advanced features like "Magic Upgrade" for converting Lite devices
to Full. For Home Assistant users, consider using the mysa_extended integration
instead: https://github.com/kgelinas/Mysa_HA

Usage:
    cd tools
    python mysa_debug.py

See docs/MYSA_DEBUG.md for detailed usage instructions.
"""
import asyncio
import json
import base64
import logging
import sys
import os
import time
import getpass
from datetime import datetime
import requests
import struct
from dataclasses import dataclass, field
from typing import Optional, List, Any, Union

# Add custom_components directory to path
# Add project root directory to path to allow absolute imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Mock homeassistant module for standalone execution
try:
    import homeassistant
except ImportError:
    from unittest.mock import MagicMock
    import types

    def mock_module(name):
        m = MagicMock()
        sys.modules[name] = m
        return m

    mock_module("homeassistant")
    mock_module("homeassistant.const")
    mock_module("homeassistant.exceptions")
    mock_module("homeassistant.util")
    mock_module("homeassistant.helpers")
    mock_module("homeassistant.components")
    mock_module("homeassistant.core")
    mock_module("homeassistant.config_entries")
    mock_module("homeassistant.helpers.update_coordinator")
    mock_module("homeassistant.helpers.aiohttp_client")
    mock_module("homeassistant.helpers.storage")
    mock_module("homeassistant.helpers.issue_registry")
    mock_module("homeassistant.helpers.device_registry")
    mock_module("homeassistant.helpers.template")
    mock_module("homeassistant.helpers.template.extensions")

    # Mock aiohttp and other common dependencies
    mock_module("aiohttp")
    mock_module("aiohttp.client")

    exceptions = mock_module("homeassistant.exceptions")
    exceptions.ConfigEntryAuthFailed = MagicMock

    uc = mock_module("homeassistant.helpers.update_coordinator")
    uc.DataUpdateCoordinator = MagicMock()
    uc.UpdateFailed = MagicMock

    aio = mock_module("homeassistant.helpers.aiohttp_client")
    aio.async_get_clientsession = MagicMock()

    storage = mock_module("homeassistant.helpers.storage")
    storage.Store = MagicMock()

    ir = mock_module("homeassistant.helpers.issue_registry")
    ir.IssueSeverity = MagicMock()
    ir.async_create_issue = MagicMock()
    ir.async_delete_issue = MagicMock()

    dr = mock_module("homeassistant.helpers.device_registry")
    dr.async_get = MagicMock()
    dr.DeviceInfo = MagicMock()
    dr.CONNECTION_NETWORK_MAC = "mac"

    # Mock template and extensions specifically
    tmpl = mock_module("homeassistant.helpers.template")
    ext = mock_module("homeassistant.helpers.template.extensions")
    tmpl.extensions = ext

    # Mock specific constants potentially used
    sys.modules["homeassistant.const"].Platform = MagicMock()
    sys.modules["homeassistant.const"].Platform.CLIMATE = "climate"


try:
    from custom_components.mysa.mysa_auth import (
        login, refresh_and_sign_url,
        CLIENT_HEADERS, BASE_URL,
    )
    from custom_components.mysa.mysa_mqtt import (
        MqttConnection,
    )

    from custom_components.mysa.const import MQTT_PING_INTERVAL
    from custom_components.mysa import mqtt

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



logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
_LOGGER = logging.getLogger(__name__)


# =============================================================================
# Mysa Reading Parsers (from mysotherm)
# =============================================================================

@dataclass
class MysaReading:
    """Binary structure representing one raw reading from a Mysa thermostat."""
    ts: int                 # Unix time (seconds)
    sensor_t: float         # Unit = °C
    ambient_t: float        # Unit = °C
    setpoint_t: float       # Unit = °C
    humidity: int           # Percent
    duty: int               # Percent
    on_ms: int              # Unit = 1 ms
    off_ms: int             # Unit = 1 ms
    heatsink_t: float       # Unit = °C
    free_heap: int          # Free heap
    rssi: int               # Unit = 1 dBm
    onoroff: int            # Probably boolean
    ver: int                # Version byte
    rest: Optional[bytes]   # Trailing bytes

    @classmethod
    def parse_readings(cls, readings: bytes) -> List[Any]:
        offset = 0
        if len(readings) < 26:
            return []

        # Detect version from the third byte (after CA A0)
        if readings[0:2] != b'\xca\xa0':
            return []
        ver = readings[2]

        output = []
        while offset < len(readings):
            if readings[offset:offset+2] != b'\xca\xa0':
                break
            if readings[offset+2] != ver:
                break

            offset += 3
            # <LhhhbbhhhHbb = Little-endian:
            # L(4) h(2) h(2) h(2) b(1) b(1) h(2) h(2) h(2) H(2) b(1) b(1) = 22 bytes
            sts, sens, amb, setp, hum, duty, onish, offish, heatsink, heap, rssi, onoroff = \
                struct.unpack_from('<LhhhbbhhhHbb', readings, offset)
            offset += 22

            heap *= 10
            sens /= 10; amb /= 10; setp /= 10; heatsink /= 10
            rssi = -rssi
            onish *= 100; offish *= 100

            kwargs = {
                'ts': sts, 'sensor_t': sens, 'ambient_t': amb, 'setpoint_t': setp,
                'humidity': hum, 'duty': duty, 'on_ms': onish, 'off_ms': offish,
                'heatsink_t': heatsink, 'free_heap': heap, 'rssi': rssi, 'onoroff': onoroff,
                'ver': ver
            }

            # Find rest
            next_pos = readings.find(b'\xca\xa0' + bytes([ver]), offset)
            if next_pos < 0:
                next_pos = len(readings)
            kwargs['rest'] = readings[offset:next_pos]

            known_vers: dict[int, type] = {0: MysaReadingV0, 1: MysaReadingV1, 3: MysaReadingV3}
            reading_cls = known_vers.get(ver, cls)
            reading, offset = reading_cls._make_reading(kwargs, readings, offset, next_pos)  # type: ignore[attr-defined]
            output.append(reading)
        return output

    @classmethod
    def _make_reading(cls, kwargs, readings, offset, next_pos):
        return cls(**kwargs), next_pos

    def __str__(self):
        dt = datetime.fromtimestamp(self.ts).strftime('%Y-%m-%d %H:%M:%S')
        return (f"[{dt}] temp={self.sensor_t:.1f}°C, amb={self.ambient_t:.1f}°C, "
                f"stpt={self.setpoint_t:.1f}°C, hum={self.humidity}%, duty={self.duty}%, "
                f"rssi={self.rssi}dBm")

@dataclass
class MysaReadingV0(MysaReading):
    unknown2: int

    @classmethod
    def _make_reading(cls, kwargs, readings, offset, next_pos):
        unknown2, = struct.unpack_from('<B', readings, offset)
        return cls(**kwargs, unknown2=unknown2), offset + 1

@dataclass
class MysaReadingV1(MysaReading):
    voltage: int
    unknown2: int

    @classmethod
    def _make_reading(cls, kwargs, readings, offset, next_pos):
        voltage, unknown2 = struct.unpack_from('<hB', readings, offset)
        return cls(**kwargs, voltage=voltage, unknown2=unknown2), offset + 3

@dataclass
class MysaReadingV3(MysaReading):
    voltage: int
    current: int
    always0: bytes
    unknown2: int

    @classmethod
    def _make_reading(cls, kwargs, readings, offset, next_pos):
        voltage, current, always0, unknown2 = struct.unpack_from('<hh3sB', readings, offset)
        current *= 10
        return cls(**kwargs, voltage=voltage, current=current, always0=always0, unknown2=unknown2), offset + 8

    def __str__(self):
        return super().__str__() + f", volt={self.voltage}V, curr={self.current}mA"


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
        self.ghost_devices = {}


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
        # Try saved credentials
        if os.path.exists(self.auth_path):
            try:
                with open(self.auth_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                print(f"Using saved credentials from {self.auth_path}")
                self.username = saved['username']
                self.password = saved['password']
                self._user_obj = await login(self.username, self.password)
                self.session = requests.Session()
                self.session.headers.update(CLIENT_HEADERS)
                self.session.headers['authorization'] = (
                    str(self._user_obj.id_token)
                )  # type: ignore[union-attr]

                # Get user ID
                r = self.session.get(f"{BASE_URL}/users")  # type: ignore[union-attr]
                r.raise_for_status()
                user_data = r.json().get("User", {})
                self.user_id = user_data.get(
                    "Id", self._user_obj.id_claims['cognito:username']
                )  # type: ignore[union-attr]
                print(f"✓ Authenticated as {self.user_id[:8]}...")
                return True
            except Exception as e:
                print(f"Saved auth failed: {e}")
                # For non-interactive debugging, exit here
                # return False
                # Or just proceed if you want to test prompt, but we assume
                # run_command will hang.
                # Let's detect if we are in a non-interactive shell?
                # Simplest for now: Exit if saved auth exists but fails
                print("Exiting due to auth failure (non-interactive mode)")
                return False

        # Manual login
        self.username = input("Mysa Email: ").strip()
        self.password = getpass.getpass("Mysa Password: ").strip()

        try:
            self._user_obj = await login(self.username, self.password)
            self.session = requests.Session()
            self.session.headers.update(CLIENT_HEADERS)
            self.session.headers['authorization'] = (
                str(self._user_obj.id_token)
            )  # type: ignore[union-attr]

            r = self.session.get(f"{BASE_URL}/users")  # type: ignore[union-attr]
            r.raise_for_status()
            user_data = r.json().get("User", {})
            self.user_id = user_data.get(
                "Id", self._user_obj.id_claims['cognito:username']
            )  # type: ignore[union-attr]

            # Save credentials
            with open(self.auth_path, 'w', encoding='utf-8') as f:
                json.dump({'username': self.username, 'password': self.password}, f)
            os.chmod(self.auth_path, 0o600)
            print(f"✓ Authenticated and saved to {self.auth_path}")
            return True
        except Exception as e:
            print(f"✗ Auth failed: {e}")
            return False

    async def fetch_devices(self):
        print("Fetching devices using client...")
        try:


            # We need to manually do what client.get_devices does but with our session
            r = self.session.get(f"{BASE_URL}/devices")  # type: ignore[union-attr]
            r.raise_for_status()
            data = r.json()
            dev_list = data.get('DevicesObj', data.get('Devices', []))

            all_devices = {}
            if isinstance(dev_list, list):
                all_devices = {d['Id']: d for d in dev_list}
            else:
                all_devices = dev_list

            # Fetch homes to filter ghosts
            print("Fetching homes for validation...")
            r_homes = self.session.get(f"{BASE_URL}/homes")  # type: ignore[union-attr]
            r_homes.raise_for_status()
            data_homes = r_homes.json()
            homes = data_homes.get('Homes', data_homes.get('homes', []))

            valid_device_ids = set()
            device_to_home = {}
            for home in homes:
                h_name = home.get('Name', 'Unknown Home')
                for zone in home.get('Zones', []):
                    z_name = zone.get('Name', 'Unknown Zone')
                    for d_id in zone.get('DeviceIds', []):
                        valid_device_ids.add(d_id)
                        device_to_home[d_id] = f"{h_name} > {z_name}"

            self.devices = {}
            # self.ghost_devices = {} # Removed ghost filtering

            for d_id, d in all_devices.items():
                self.devices[d_id] = d
                # Inject location info for display
                d['_location'] = device_to_home.get(d_id)

            print(f"\n✓ Found {len(self.devices)} devices")
            print()

            self.list_devices()

        except Exception as e:
            print(f"Error fetching devices: {e}")

    def list_devices(self):
        if not self.devices:
            print("No active devices found.")
        else:
            print("--- Devices ---")
            for i, (did, d) in enumerate(self.devices.items(), 1):
                model = d.get('Model', 'Unknown')
                name = d.get('Name', 'Unnamed')
                loc = d.get('_location', '')
                loc_str = f" [{loc}]" if loc else ""
                print(f"  {i}. {name} ({did}) - {model}{loc_str}")



    async def command_loop(self):
        # Create prompt session if prompt_toolkit is available
        session = PromptSession() if HAS_PROMPT_TOOLKIT else None

        self.print_help()

        while True:
            try:
                if HAS_PROMPT_TOOLKIT:
                    # prompt_toolkit keeps prompt at bottom while output scrolls above
                    with patch_stdout():
                        cmd_raw = await session.prompt_async("CMD> ")  # type: ignore[union-attr]
                else:
                    # Fallback to standard input
                    cmd_raw = await asyncio.get_event_loop().run_in_executor(None, input, "CMD> ")

                parts = cmd_raw.strip().split(maxsplit=2)
                if not parts:
                    continue

                cmd = parts[0].lower()
                if not await self._handle_command(cmd, parts):
                    return
            except Exception as e:
                print(f"Error: {e}")

    async def _handle_command(self, cmd, parts):
        """Handle parsed command."""
        if cmd in ('q', 'quit', 'exit'):
            print("Goodbye!")
            return False

        if cmd in ('ls', 'list'):
            self.list_devices()
        elif cmd == 'sniff':
            self._handle_sniff(parts)
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
        elif cmd in ('refresh', 'update') and len(parts) >= 2:
            await self.refresh_settings(parts[1])
        elif cmd == 'dump' and len(parts) >= 2:
            await self.dump_readings(parts[1])
        elif cmd == 'batch' and len(parts) >= 2:
            await self.sub_batch(parts[1])
        else:
            print("Unknown command. Type 'help' or 'ex' for available commands.")

        return True

    def _handle_sniff(self, parts):
        """Handle sniff command."""
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
                self.sniff_mode = False
                self.sniff_filter = None
                print("Sniff Mode: OFF")
            else:
                self.sniff_mode = not self.sniff_mode
                self.sniff_filter = None
                print(f"Sniff Mode: {'ON' if self.sniff_mode else 'OFF'}")

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
        print("  refresh <ID>      Force device to check cloud settings (MsgType 6)")
        print("  dump <ID>         Force device to dump readings/info (MsgType 7)")
        print("  batch <ID>        Try subscribing to /batch topic (WARNING: MAY DISCONNECT)")

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
            r = self.session.get(f"{BASE_URL}/homes")  # type: ignore[union-attr]
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
            r = self.session.get(f"{BASE_URL}/users")  # type: ignore[union-attr]
            r.raise_for_status()
            data = r.json()
            print("\n--- /users Response ---")
            print(json.dumps(data, indent=2))

            # Extract key user info
            user = data.get('User', data.get('user', {}))
            if not user:
                return

            cognito = user.get('CognitoAttrs', {})
            print("\n--- User Info ---")
            print(f"  User ID: {user.get('Id', 'Unknown')}")
            given = cognito.get('given_name', '')
            family = cognito.get('family_name', '')
            full_name = cognito.get('name', f"{given} {family}")
            print(f"  Name: {full_name}")
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
        print("   New Model: BB-V2-0")

        confirm = input("\n⚠️  Type 'YES I UNDERSTAND' to proceed: ").strip()
        if confirm != 'YES I UNDERSTAND':
            print("Confirmation failed. Cancelled.")
            return

        # Send the conversion request
        print("\nSending model change request...")
        url = f"{BASE_URL}/devices/{did}"
        try:
            r = self.session.post(url, json={'Model': 'BB-V2-0'})  # type: ignore[union-attr]
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
        payload = {
            "Device": did,
            "Timestamp": int(time.time()),
            "MsgType": 5,
            "EchoID": 1
        }

        print("\nSending killer ping...")
        topic = f"/v1/dev/{did.replace(':', '').lower()}/in"

        try:
            pub_pkt = mqtt.publish(
                topic, False, 1, False, packet_id=99, payload=json.dumps(payload).encode()
            )
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

        print("\n--- MQTT Heating Examples (type=4 for BB-V2) ---")
        print(f'  mqtt {did} {{"cmd":[{{"sp":21,"stpt":21,"a_sp":21,"tm":-1}}],"type":4,"ver":1}}')
        print("       ^ Set temperature to 21°C")
        print(f'  mqtt {did} {{"cmd":[{{"md":3,"tm":-1}}],"type":4,"ver":1}}')
        print("       ^ Set HVAC mode to Heat (md: 1=Off, 3=Heat)")
        print(f'  mqtt {did} {{"cmd":[{{"lk":1,"tm":-1}}],"type":4,"ver":1}}')
        print("       ^ Lock buttons (lk: 0=Unlock, 1=Lock)")
        print(f'  mqtt {did} {{"cmd":[{{"pr":1,"tm":-1}}],"type":4,"ver":1}}')
        print("       ^ Proximity mode (pr: 0=Off, 1=On)")
        print(f'  mqtt {did} {{"cmd":[{{"tm":-1,"br":{{"a_b":1,"a_br":100,"i_br":50,'
              f'"a_dr":60,"i_dr":30}}}}],"type":4,"ver":1}}')
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
        print(f'  mqtt {did} {{"cmd":[{{"ssh":6,"tm":-1}}],"type":2,"ver":1}}')
        print("       ^ Set horizontal swing (ssh: 3=Auto, 4-9=Position 1-6)")
        print(f'  mqtt {did} {{"cmd":[{{"it":1,"tm":-1}}],"type":2,"ver":1}}')
        print("       ^ Climate+ mode (it: 0=Off, 1=On - uses Mysa temp sensor)")

        print("\n--- Device Type Values ---")
        print("  type=1  BB-V1 (Baseboard V1)")
        print("  type=2  AC-V1 (AC Controller)")
        print("  type=3  INF-V1 (In-Floor Heating)")
        print("  type=4  BB-V2 (Baseboard V2)")
        print("  type=5  BB-V2-L (Baseboard V2 Lite)")

        print("\n--- Maintenance/Debug Commands ---")
        print(f"  refresh {did}        # Force device to check cloud settings (MsgType 6)")
        print(f"  dump {did}           # Force metadata dump: FW, IP, Serial (MsgType 7)")
        print()

    async def show_state(self, device_ref):
        did = self._resolve_device(device_ref)
        if not did:
            return

        print(f"\nFetching state for {did}...")

        # Device settings
        r_dev = self.session.get(f"{BASE_URL}/devices/{did}")  # type: ignore[union-attr]
        r_dev.raise_for_status()

        # Live state
        r_state = self.session.get(f"{BASE_URL}/devices/state")  # type: ignore[union-attr]
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
            payload = json.loads(json_str, strict=False)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            return

        url = f"{BASE_URL}/devices/{did}"
        print(f"\nPOST {url}")
        print(f"Body: {json.dumps(payload)}")

        r = self.session.post(url, json=payload)  # type: ignore[union-attr]
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
            body = json.loads(json_str, strict=False)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            return

        # Auto-detect if already wrapped
        # If the user pasted a full command from the docs ({"cmd":..., "type":...}), send it as the body of the MsgType 44 wrapper?
        # WAIT. The MsgType 44 wrapper expects "body" to be the command object.
        # The structure is: MsgType 44 -> body -> { "cmd": [...], "type": 4, "ver": 1 }
        # So send_mqtt_raw does: wrapper["body"] = body.
        # So if the user types {"cmd":...}, that becomes the body. This IS correct.

        # Structure Reference:
        # Wrapper: { "msg": 44, "body": <USER_INPUT> }
        # User Input: { "cmd": [{"sp":21}], "type": 4, "ver": 1 }

        # Let's re-verify the protocol.
        # mysa_mqtt.py (line 380 in confirm): "msg": 44, "body": payload.
        # Implementation in send_mqtt_raw matches this.

        # SO: The Code seems correct. The user inputs the INNER payload (Command), and the tool wraps it in the OUTER envelope (MsgType 44).
        # The examples show: {"cmd":...}. This is the inner payload.
        # If I type `mqtt 1 {"cmd":...}`, `body` becomes `{"cmd":...}`.
        # `wrapper["body"]` becomes `{"cmd":...}`.
        # `wrapper["msg"]` is 44.

        # This matches `realtime.py` line 380:
        # outer_payload = { ... "body": payload, ... "msg": 44 ... }

        # Conclusion: The code IS correct. The confusion was mine.
        # Double check documentation examples vs code:
        # Doc: mqtt 1 {"cmd":[{"sp":21...}],"type":4,"ver":1}
        # Code: wrapper["body"] = user_json
        # Result: { "msg": 44, "body": { "cmd": ..., "type": 4 } }
        # This IS the correct structure for Mysa commands.

        # I will leave the code as is.
        # But wait, looking at `send_mqtt_raw`, it prints:
        # print(f"Body: {json.dumps(body, indent=2)}")

        # I should just update the print message to clarify it's wrapping it.

        # Re-reading user request: "can you make sure all MQTT Examples are right in MYSA_DEBUG doc and tool help menu"
        # I cross referenced them. They match.
        # Doc Example: mqtt 1 {"cmd":[{"sp":21,"stpt":21,"a_sp":21,"tm":-1}],"type":4,"ver":1}
        # Tool Help Example: mqtt {did} {"cmd":[{"sp":21,"stpt":21,"a_sp":21,"tm":-1}],"type":4,"ver":1}
        # Wait. Tool Help (line 98 of MYSA_DEBUG.md) has "a_sp".
        # Tool Code (line 601 of mysa_debug.py) has "lk".
        # Tool Code (line 605) has "br".
        # Tool Code (line 610) has "sp".

        # The user wants them ALL right.
        # I will update `mysa_debug.py` help text to match `MYSA_DEBUG.md` more closely or ensure they are both valid valid.
        # `MYSA_DEBUG.md` generally has more examples.
        # I will update `mysa_debug.py` to match the format and content of `MYSA_DEBUG.md` where appropriate.

        # Specifically, the AC examples in `mysa_debug.py` look slightly different order but valid.

        # One discrepancy found:
        # Docs: mqtt 1 {"cmd":[{"sp":21,"stpt":21,"a_sp":21,"tm":-1}],"type":4,"ver":1}
        # Code Help: mqtt {did} {"cmd":[{"sp":22,"stpt":22,"tm":-1}],"type":2,"ver":1} (For AC)

        # For BB (Heating), Code Help starts with "Set HVAC mode to Heat".
        # Docs start with "Set temperature".

        # I will add the "Set Temperature" example to the Heating section of `mysa_debug.py` to be comprehensive.
        # Wrapper construction
        wrapper = {
            "msg": 44,
            "body": body
        }

        safe_did = did.replace(":", "").lower()
        topic = f"/v1/dev/{safe_did}/in"
        json_payload = json.dumps(wrapper)

        print(f"\nMQTT PUBLISH {topic}")
        print(f"Body: {json.dumps(body, indent=2)}")

        try:
            pub_pkt = mqtt.publish(
                topic, False, 1, False, packet_id=2, payload=json_payload.encode()
            )
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
            pub_pkt = mqtt.publish(
                topic, False, 1, False, packet_id=3, payload=json.dumps(body).encode()
            )
            await self.ws.send(pub_pkt)
        except Exception:
            pass  # Notification is best-effort

    async def refresh_settings(self, device_ref):
        """Send MsgType 6 to force device to check cloud settings."""
        did = self._resolve_device(device_ref)
        if not did:
            return

        if not self.ws:
            print("\n✗ MQTT not connected. Cannot send refresh request.")
            return

        print(f"\nRequesting settings refresh from {did} (MsgType 6)...")
        await self.notify_settings_changed(did)
        print("✓ Request sent! Device should fetch new settings from cloud.")

    async def dump_readings(self, device_ref):
        """Send MsgType 7 to fetch device metadata (FW, IP, Serial, MAC)."""
        did = self._resolve_device(device_ref)
        if not did:
            return

        if not self.ws:
            print("\n✗ MQTT not connected. Cannot send dump request.")
            return

        print(f"\nRequesting metadata dump from {did} (MsgType 7)...")

        timestamp = int(time.time())
        payload = {
            "Device": did,
            "Timestamp": timestamp,
            "MsgType": 7
        }

        safe_did = did.replace(":", "").lower()
        topic = f"/v1/dev/{safe_did}/in"

        try:
            pub_pkt = mqtt.publish(
                topic, False, 1, False, packet_id=14, payload=json.dumps(payload).encode()
            )
            await self.ws.send(pub_pkt)
            print("✓ Dump request sent! Watch for updates/logs.")
        except Exception as e:
            print(f"✗ Failed to send dump request: {e}")

    async def sub_batch(self, device_ref):
        """Try to subscribe to the /batch topic for a device (or 'all')."""
        if device_ref.lower() == 'all':
            dids = list(self.devices.keys())
        else:
            did = self._resolve_device(device_ref)
            if not did:
                return
            dids = [did]

        if not self.ws:
            print("\n✗ MQTT not connected.")
            return

        from custom_components.mysa import mqtt
        specs = []
        for did in dids:
            safe_did = did.replace(":", "").lower()
            topic = f"/v1/dev/{safe_did}/batch"
            specs.append(mqtt.SubscriptionSpec(topic, 0))
            print(f"  • {topic}")

        print(f"\n⚠️ Attempting to subscribe to {len(specs)} topics...")

        try:
            sub_pkt = mqtt.subscribe(99, specs)
            await self.ws.send(sub_pkt)
            print("✓ SUBSCRIBE packet sent. Watching for readings...")
        except Exception as e:
            print(f"✗ Failed to send subscribe: {e}")


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
                    signed_url, new_user_obj = await refresh_and_sign_url(
                        self._user_obj  # type: ignore[arg-type]
                    )
                    if new_user_obj is not self._user_obj:
                        self._user_obj = new_user_obj
                        print("✓ Re-authenticated successfully")
                except Exception as e:
                    print(f"⚠ Auth failed: {e}")
                    await asyncio.sleep(5)
                    continue

                # Use MqttConnection context manager
                async with MqttConnection(
                    signed_url, list(self.devices.keys()), include_batch=False
                ) as conn:
                    self.ws = conn.websocket
                    print("⚡ MQTT Connected!")

                    while conn.connected:
                        pkt = await conn.receive(timeout=MQTT_PING_INTERVAL + 5)

                        if pkt is None:
                            # Timeout - send ping
                            await conn.send_ping()
                        elif isinstance(pkt, mqtt.PublishPacket):
                            is_batch = pkt.topic.endswith('/batch')
                            if self.sniff_mode or is_batch:
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

            # Special handling for Batch Data (MsgType 3)
            if msg_type == 3:
                print(f"\n[{timestamp}] [SNIFF {arrow}] MsgType 3 (Batch Data):")
                print(json.dumps({k: v for k, v in payload.items() if k != 'body'}, indent=2))

                body = payload.get('body', {})
                readings_b64 = body.get('readings')
                if readings_b64:
                    try:
                        readings_raw = base64.b64decode(readings_b64)
                        parsed = MysaReading.parse_readings(readings_raw)
                        if parsed:
                            print(f"  Version: v{parsed[0].ver} ({len(parsed)} readings)")
                            for r in parsed:
                                print(f"    • {r}")
                        else:
                            # Fallback to hex if parsing failed
                            version = readings_raw[0] if readings_raw else "N/A"
                            print(f"  Readings Version: v{version} (Parse failed)")
                            print(f"  Raw Hex ({len(readings_raw)} bytes):")
                            hex_str = readings_raw.hex()
                            print(f"    {' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))}")
                    except Exception as b64_err:
                        print(f"  Error decoding/parsing readings: {b64_err}")
                else:
                    print(f"  No readings found in body: {json.dumps(body)}")
            else:
                print(f"\n[{timestamp}] [SNIFF {arrow}] MsgType {msg_type}: "
                      f"{json.dumps(payload, indent=2)}")
        except Exception:
            print(f"\n[{timestamp}] [SNIFF {arrow}] {pkt.payload.decode(errors='ignore')}")


if __name__ == "__main__":
    auth_path = os.path.expanduser("~/.mysa_debug_auth.json")
    tool = MysaDebugTool(auth_path)
    try:
        asyncio.run(tool.run())
    except KeyboardInterrupt:
        print("\n✓ Stopped")
