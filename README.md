# Home Assistant Eplucon Integration

This custom integration allows you to integrate your Eplucon devices into Home Assistant, providing access to real-time data and sensor values.

## Features

- Monitor indoor temperature, vent RPM, brine circulation pump, and more in real-time.
- Automatically update sensor data using Home Assistant's update coordinator.

## Installation

### HACS (Home Assistant Community Store)

1. Ensure you have [HACS](https://hacs.xyz/) installed in your Home Assistant instance.
2. Open HACS, go to the "Integrations" tab, and click on the "+" button to add a new repository.
3. Search for "Eplucon" and install the integration.
4. Restart Home Assistant.

### Manual Installation

1. Download the latest release from the [GitHub releases page](https://github.com/koenhendriks/ha-eplucon/releases).
2. Extract the `eplucon` folder into your `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration

### Step 1: Obtain API Token

To use this integration, you will need an API token from Eplucon. Follow these steps to get your token:

1. Log in to your Eplucon account.
2. Navigate to My Account and then the [API section](https://portaal.eplucon.nl/account/api_tokens).
3. Generate or copy your existing API token.

### Step 2: Add Integration in Home Assistant

1. Go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for "Eplucon" and select it.
3. Enter your API token and complete the setup.

### Step 3: Sensors and Entities

After successful setup, Home Assistant will automatically add the available sensors. You can find them under the **Devices & Services** section in Home Assistant.

## Available Sensors

This integration provides all available sensors that can be retrieved from the [Eplucon API](https://portaal.eplucon.nl/docs/api#/) and adds them to your Home Assistant. Some of the available sensors include:

- **Indoor Temperature** (°C)
- **Vent RPM** (RPM)
- **Brine Circulation Pump** (RPM)
- **Outdoor Temperature** (°C) - if available
- **Heating Status** - if applicable

These sensors are automatically created based on the real-time information available from your Eplucon device.

### Screenshot

![Eplucon sensors added to Home assistant](https://github.com/user-attachments/assets/9183f9fa-da81-465a-96a1-e6ff9aae3869)

## Troubleshooting

### Common Issues

- **Sensor values not updating:** Ensure that your API token is correct and the Eplucon server is accessible. Check the Home Assistant logs for any errors.
- **Missing sensors:** Verify that your device supports the sensors you're trying to add. Only sensors with real-time data will be added.

### Logs

If you encounter any issues, check the Home Assistant logs for errors related to the Eplucon integration. Logs can be found under **Settings** > **System** > **Logs**.

Make sure to enable debug logging for this integration which can be toggled under **Settings** > **Devices & Services** > **Eplucon**.

## Contributing

Contributions are welcome! If you'd like to contribute to this integration, please fork the repository and submit a pull request. Be sure to follow the existing coding style and add appropriate tests.

## Support

If you have any issues or feature requests, please open an issue on the [GitHub Issues page](https://github.com/your-repo/eplucon/issues).

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
