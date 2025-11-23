"""
Parser for Temperature and Humidity sensors based on a specific RF data format.
"""

def parse(data: str):
    """
    Parses a raw RF data string based on the logic from the provided
    Home Assistant template. It extracts temperature and humidity, and generates
    a composite ID from the device type and device ID in the data.

    Args:
        data: The raw RF data string from the bridge.

    Returns:
        A dictionary containing the composite ID, temperature, and humidity
        if the parsing is successful; otherwise, None.
        Example: {'id': '5-138', 'temperature': 22.5, 'humidity': 55}
    """
    # The template checks for `rf_data|length >= 100`
    if not isinstance(data, str) or len(data) < 100:
        return None

    try:
        # The template does: `rf_data.replace('81', '0').replace('82', '1').split(' ')`
        data_array = data.replace('81', '0').replace('82', '1').split(' ')

        # The template checks `data_array|length > 7 and data_array[7]|length >= 37`
        if len(data_array) <= 7 or len(data_array[7]) < 37:
            return None

        binary_data = data_array[7]

        # Extract device_type and device_id
        # `binary_data[12:15] | int(0, 2)`
        device_type = int(binary_data[12:15], 2)
        # `binary_data[5:13] | int(0, 2)`
        device_id = int(binary_data[5:13], 2)

        # Create a composite ID from device_type and device_id
        composite_id = f"{device_type}-{device_id}"

        # Extract temperature
        # `binary_data[20:29] | int(0, 2) / 10.0`
        temp_binary = binary_data[20:29]
        temp_int = int(temp_binary, 2)
        temperature = temp_int / 10.0

        # Extract humidity
        # `binary_data[29:37] | int(0, 2)`
        humidity_binary = binary_data[29:37]
        humidity = int(humidity_binary, 2)

        # Return all the parsed data
        return {
            "id": composite_id,
            "temperature": temperature,
            "humidity": humidity,
        }

    except (ValueError, IndexError, TypeError):
        # Return None if any conversion or indexing fails
        return None
    
    return None
