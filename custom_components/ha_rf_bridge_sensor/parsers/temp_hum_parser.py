"""
Parser for Temperature and Humidity sensors based on a specific RF data format.
"""

def parse(data: str):
    """
    Parses RF data with a fix for negative temperature handling (Two's Complement).
    """
    if not isinstance(data, str) or len(data) < 100:
        return None

    try:
        data_array = data.replace('81', '0').replace('82', '1').split(' ')

        if len(data_array) <= 7 or len(data_array[7]) < 37:
            return None

        binary_data = data_array[7]

        # Extract device_type and device_id
        device_type = int(binary_data[12:15], 2)
        device_id = int(binary_data[5:13], 2)
        composite_id = f"{device_type}-{device_id}"

        # --- TEMPERATURE FIX START ---
        temp_binary = binary_data[20:29]
        temp_int = int(temp_binary, 2)
        
        # Check if the 9th bit (Sign Bit) is set. 
        # In a 9-bit integer, if the value is >= 256 (1 << 8), it is negative.
        if temp_int & (1 << 8):  # Checks if the bit at index 8 (9th bit) is 1
            temp_int = temp_int - 512

        temperature = temp_int / 10.0
        # --- TEMPERATURE FIX END ---

        # Extract humidity
        humidity_binary = binary_data[29:37]
        humidity = int(humidity_binary, 2)

        return {
            "id": composite_id,
            "temperature": temperature,
            "humidity": humidity,
        }

    except (ValueError, IndexError, TypeError):
        return None
    
    return None