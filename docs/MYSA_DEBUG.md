# Mysa Debug Tool

A command-line utility for testing and debugging Mysa device communication. Useful for development, troubleshooting, and understanding the Mysa protocol.

## Requirements

- Python 3.8+
- Dependencies: `websockets`, `requests`, `boto3`
- Optional: `prompt_toolkit` (for better input experience)

```bash
pip install websockets requests boto3 prompt_toolkit
```

## Running the Tool

From the repository root:

```bash
cd tools
python mysa_debug.py
```

On first run, you'll be prompted for your Mysa account credentials. These are saved to `~/.mysa_debug_auth.json` for future sessions.

## Commands

| Command                  | Description                              |
|:-------------------------|:-----------------------------------------|
| `ls`                     | List all devices                         |
| `state <DID>`            | Show raw device state (HTTP)             |
| `http <DID> <JSON>`      | Send HTTP POST to device settings        |
| `mqtt <DID> <JSON>`      | Send MQTT command (auto-wrapped)         |
| `sniff`                  | Toggle MQTT sniffer mode                 |
| `examples`               | Show example commands                    |
| `help` or `?`            | Show command help                        |
| `q` or `quit`            | Exit                                     |

### Device Reference

You can reference devices by:
- **Number**: `1`, `2`, `3` (from the `ls` list)
- **Device ID**: Full MAC address (with or without colons)

## HTTP Examples

HTTP commands modify device settings via the cloud API:

```bash
# Lock the thermostat buttons
http 1 {"ButtonState": 1}

# Unlock buttons
http 1 {"ButtonState": 0}

# Enable Eco Mode (note: inverted - "0" means ON)
http 1 {"ecoMode": "0"}

# Set display brightness
http 1 {"MinBrightness": 20}
http 1 {"MaxBrightness": 100}

# Enable auto brightness
http 1 {"AutoBrightness": true}

# Enable proximity wake
http 1 {"ProximityMode": true}

# Change temperature unit
http 1 {"Format": "celsius"}

# Rename device
http 1 {"Name": "Office Thermostat"}
```

## MQTT Examples

MQTT commands are sent directly to devices for real-time control. Commands are automatically wrapped in the MsgType 44 envelope.

### Heating Thermostats (BB-V1, BB-V2, BB-V2-L, INF-V1)

```bash
# Set temperature to 21°C (use type=4 for BB-V2)
mqtt 1 {"cmd":[{"sp":21,"stpt":21,"a_sp":21,"tm":-1}],"type":4,"ver":1}

# Set HVAC mode to Heat
mqtt 1 {"cmd":[{"md":3,"tm":-1}],"type":4,"ver":1}

# Set HVAC mode to Off
mqtt 1 {"cmd":[{"md":1,"tm":-1}],"type":4,"ver":1}

# Lock buttons
mqtt 1 {"cmd":[{"lk":1,"tm":-1}],"type":4,"ver":1}

# Enable proximity mode
mqtt 1 {"cmd":[{"pr":1,"tm":-1}],"type":4,"ver":1}

# Set brightness (a_b=auto, a_br=active%, i_br=idle%)
mqtt 1 {"cmd":[{"tm":-1,"br":{"a_b":1,"a_br":100,"i_br":50,"a_dr":60,"i_dr":30}}],"type":4,"ver":1}
```

### AC Controllers (AC-V1)

```bash
# Set temperature to 22°C
mqtt 1 {"cmd":[{"sp":22,"stpt":22,"tm":-1}],"type":2,"ver":1}

# Set mode to Cool
mqtt 1 {"cmd":[{"md":4,"tm":-1}],"type":2,"ver":1}

# Set fan speed to Medium
mqtt 1 {"cmd":[{"fn":7,"tm":-1}],"type":2,"ver":1}

# Set vertical swing to Auto
mqtt 1 {"cmd":[{"ss":3,"tm":-1}],"type":2,"ver":1}

# Set horizontal swing to Center
mqtt 1 {"cmd":[{"ssh":6,"tm":-1}],"type":2,"ver":1}

# Enable Climate+ mode (thermostatic control)
mqtt 1 {"cmd":[{"it":1,"tm":-1}],"type":2,"ver":1}
```

## Device Type Values

| Type | Model   | Description          |
|:-----|:--------|:---------------------|
| 1    | BB-V1   | Baseboard V1         |
| 2    | AC-V1   | AC Controller        |
| 3    | INF-V1  | In-Floor Heating     |
| 4    | BB-V2   | Baseboard V2         |
| 5    | BB-V2-L | Baseboard V2 Lite    |

## Sniff Mode

Enable sniff mode to see all MQTT messages in real-time:

```
CMD> sniff
Sniff Mode: ON
```

Output shows:
- `→` Messages TO device (commands)
- `←` Messages FROM device (state updates)

Example output:
```
[2024-01-15 10:30:45.123] [SNIFF ←] MsgType 40: {
  "msg": 40,
  "body": {
    "state": {
      "sp": 21.0,
      "md": 3,
      "Temperature": {"v": 20.5},
      "Humidity": {"v": 45}
    }
  }
}
```

## Viewing Raw State

Use `state` to see the full device data from the HTTP API:

```
CMD> state 1

--- Device Settings (HTTP) ---
{
  "Id": "AA:BB:CC:DD:EE:FF",
  "Name": "Living Room",
  "Model": "BB-V2-0",
  "ButtonState": 0,
  "AutoBrightness": true,
  ...
}

--- Live State (HTTP) ---
{
  "Temperature": {"v": 21.5},
  "Humidity": {"v": 42},
  "SetPoint": {"v": 22.0},
  ...
}
```

## Tips

1. **Use sniff mode first**: Before sending commands, enable sniff mode and interact with the Mysa app to see what commands it sends.

2. **Check your type value**: Different device models require different type values. Using the wrong type will have no effect.

3. **Commands are additive**: You can combine multiple fields in one command:
   ```bash
   mqtt 1 {"cmd":[{"sp":21,"md":3,"tm":-1}],"type":4,"ver":1}
   ```

4. **tm=-1 for permanent**: The `tm` field sets a timer. Use -1 for permanent changes.

5. **HTTP + MQTT sync**: Some settings work best when sent via both HTTP (cloud sync) and MQTT (instant device update). The debug tool sends HTTP commands directly, but MQTT commands also trigger a settings-changed notification.
