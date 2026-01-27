# Configuration

## Initial Setup
When adding the integration, you must provide:
- **Username**: Your Mysa account email address.
- **Password**: Your Mysa account password.

## Energy Dashboard
To use the electricity rate provided directly by Mysa in the Energy Dashboard:

1. In the Energy Dashboard configuration, under **Electricity Grid**, click **Add Consumption Source** (or edit an existing one).
2. For **Grid consumption**, select your Mysa Energy entity (e.g., `sensor.office_energy`).
3. Under **"Select how Home Assistant should keep track of the costs of the consumed energy"**, select **"Use an entity with current price"**.
4. In the dropdown, search for an entity ending in `_electricity_rate`.
    *   **Example Name:** `sensor.office_electricity_rate`
    *   **Friendly Name:** "Office Electricity Rate"
    *   *Note: This entity comes from the Mysa integration and provides the rate configured in your Mysa cloud account.*

> [!NOTE]
> If you do not see this entity, ensure it is enabled in the device settings (it is categorized as a "Diagnostic" entity but should be enabled by default).

### Best Practices ("Individual Devices" vs "Grid Consumption")

*   **Individual Devices**: **Add your Mysa devices here.** This populates the breakdown chart, showing exactly how much energy each room/thermostat used compared to the rest of your home.
*   **Electricity Grid**: Only add your Mysa devices here if you **do not** have a whole-home energy monitor. If you have a main meter (e.g., Shelly EM, Emporia Vue, or Utility Meter), putting Mysa devices here would result in double-counting your energy usage.

## Options Flow (Mysa Integration)
To configure advanced options for the main integration:
1. Go to **Settings** > **Devices & Services**.
2. Click **Configure** on the **Mysa** integration card.

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

## Options Flow (Mysa Extended)
If you have the **Mysa Extended** integration installed, it has its own separate configuration:
1. Go to **Settings** > **Devices & Services**.
2. Click **Configure** on the **Mysa Extended** integration card.

### Available Options

#### 1. Custom Electricity Rate
- **Description**: Override the electricity rate calculated by Mysa's cloud.
- **Format**: Float (Cost per kWh, e.g., 0.15 for $0.15/kWh).
- **Default**: Empty (uses Mysa cloud rate).
- **Purpose**: Useful if Mysa's cloud rate is inaccurate or providing data in a currency that doesn't match your Home Assistant settings.
