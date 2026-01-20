# Configuration

## Initial Setup
When adding the integration, you must provide:
- **Username**: Your Mysa account email address.
- **Password**: Your Mysa account password.

## Options Flow
To configure advanced options:
1. Go to **Settings** > **Devices & Services**.
2. Click **Configure** on the Mysa integration card.

### Available Options

#### 1. Upgraded Lite Devices
- **Description**: Select devices that are technically "Lite" models (e.g., BB-V2-0-L) but have been "magic upgraded" to Full functionality (BB-V2-0).
- **Purpose**: Ensures correct feature exposure in Home Assistant (e.g., Energy Monitoring).

#### 2. Wattage Overrides
- **Description**: Manually specify the heater wattage for each thermostat.
- **Format**: Integer (Watts, 0-5000).
- **Default**: 0
- **Purpose**: Used for energy calculation if the device does not report it or to correct inaccurate readings. This is critical for accurate "Power" and "Energy" sensors on generic heaters.

#### 3. Estimated Max Current
- **Description**: Global override for max current (Amps) logic.
- **Default**: 0 (Auto/Device-reported)

#### 4. Simulated Energy
- **Description**: Toggle to enable simulated energy monitoring.
- **Default**: Disabled
- **Purpose**: If your device doesn't support hardware energy monitoring, this calculates estimated energy usage based on `Study Duty` (Usage %) and `Wattage`.
