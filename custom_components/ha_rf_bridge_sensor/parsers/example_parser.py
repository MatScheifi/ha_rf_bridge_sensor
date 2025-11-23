"""
Example parser for RF Bridge data.
"""

def parse(data: str):
    """
    Parses a raw RF data string and extracts sensor values.

    The data is expected to be in a specific hex format.
    - The first 4 characters are the device ID.
    - The next 4 characters are the temperature.
    - The next 2 characters are the humidity.

    Args:
        data: The raw RF data string (e.g., "A1B201F43C").

    Returns:
        A dictionary with the parsed data if successful, otherwise None.
        Example: {'id': 'A1B2', 'temperature': 25.0, 'humidity': 60}
    """
    if not isinstance(data, str) or len(data) < 10:
        return None

    try:
        device_id = data[0:4]
        
        temp_hex = data[4:8]
        temperature = int(temp_hex, 16) / 10.0

        # Make sure temperature is within a reasonable range
        if not -50 < temperature < 150:
            return None

        humidity_hex = data[8:10]
        humidity = int(humidity_hex, 16)

        # Make sure humidity is within a reasonable range
        if not 0 <= humidity <= 100:
            return None

        return {
            "id": device_id,
            "temperature": temperature,
            "humidity": humidity,
        }
    except (ValueError, TypeError):
        # This will catch errors if the hex conversion fails
        return None
