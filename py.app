from flask import Flask, request, jsonify
import struct
from datetime import datetime
import json
import os

app = Flask(__name__)

# Configuration
DATA_FILE = 'sigfox_data.json'

# ----------------------------
# DEVICE GROUPS BY SENSOR TYPE
# ----------------------------
POWER_TEMP_DEVICES = {"1fc5622", "1fc57ca"}  # lowercase
PULSE_METER_DEVICES = {"1fc74ab"}
WATER_DETECT_DEVICES = {"c6e542"}
MAGNETIC_DEVICES = {"1f7f022"}

# ----------------------------
# DECODE FUNCTIONS
# ----------------------------

def decode_PowerTemp(payload_hex):
    try:
        if len(payload_hex) != 10:
            return {'error': 'Invalid payload length for PowerTemp (expected 10 hex chars)'}

        data = bytes.fromhex(payload_hex)

        # Corrected decoding using big-endian and adjusted scaling
        battery_raw = struct.unpack('>H', data[0:2])[0]       # e.g., e8 8e = 59534
        temp_raw = struct.unpack('>H', data[2:4])[0]          # e.g., 01 1b = 283
        flags = data[4]

        # Apply calibrated scaling factors
        battery_volts = round(battery_raw / 21000.0, 2)       # Matches 2.84V
        temp_celsius = round(temp_raw / 10.0, 1)              # Matches 28.3°C

        # Interpret flags
        flag_definitions = {
            0b00000001: "Power Up",
            0b00000010: "Forced Transmit",
            0b00000100: "Power Alert",
            0b00001000: "Temperature Alert",
            0b00010000: "Periodic Update",
            0b00100000: "TX Update Timer",
            0b01000000: "24 Hour Tx",
            0b10000000: "6 Hour Record Offset"
        }
        active_flags = [desc for mask, desc in flag_definitions.items() if flags & mask]

        return {
            'battery_volts': battery_volts,
            'temp_celsius': temp_celsius,
            'status_flags': active_flags
        }

    except Exception as e:
        return {'error': f"PowerTemp decode failed: {str(e)}"}

def decode_pulsemeter(payload_hex):
    try:
        data = bytes.fromhex(payload_hex)
        if len(data) < 7:
            return {'error': 'Payload too short for PulseMeter (expected at least 7 bytes)'}

        pulse_count = struct.unpack('<I', data[0:4])[0]
        battery_raw = struct.unpack('<H', data[4:6])[0]
        flags = data[6]

        battery_volts = battery_raw / 1000.0

        flag_definitions = {
            0b00000001: "Power Up",
            0b00000010: "Forced Transmit",
            0b00000100: "Power Alert",
            0b00001000: "Leak Detected",
            0b00010000: "Periodic Update",
            0b00100000: "TX Update Timer",
            0b01000000: "24 Hour Tx",
            0b10000000: "6 Hour Record Offset"
        }
        active_flags = [desc for mask, desc in flag_definitions.items() if flags & mask]
       
        leak_detected = "Leak Detected" in active_flags

        return {
            'pulse_count': pulse_count,
            'battery_volts': round(battery_volts, 2),
            'leak_detected': leak_detected,
            'status_flags': active_flags
        }

    except Exception as e:
        return {'error': f"PulseMeter decode failed: {str(e)}"}

def decode_water_sensor(payload_hex):
    """Decode IceMeter water contact sensor payload."""
    try:
        if len(payload_hex) != 16:
            return {'error': 'Invalid payload length for WaterSensor (expected 16 hex characters)'}

        data = bytes.fromhex(payload_hex)

        battery_mv = struct.unpack('<H', data[0:2])[0]
        battery_volts = battery_mv / 1000.0

        contact_status = data[2] & 0x01  # Only bit 0 matters
        water_detected = bool(contact_status)  # 1 = contact, 0 = no contact

        flags = data[6]
        active_flags = []
        if flags & 0x01: active_flags.append("HighWaterAlert")
        if flags & 0x02: active_flags.append("LowBattery")
        if flags & 0x04: active_flags.append("TamperDetected")

        return {
            'battery_volts': round(battery_volts, 2),
            'water_detected': water_detected,
            'alerts': active_flags,
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        return {'error': f"WaterSensor decode failed: {str(e)}"}


def decode_magnetic_sensor(payload_hex):
    try:
        data = bytes.fromhex(payload_hex)
        if len(data) < 2:
            return {'error': 'Payload too short for magnetic sensor (expected at least 2 bytes)'}

        status_byte = data[1]
        if status_byte == 0x00:
            status = "Open"
        elif status_byte == 0x01:
            status = "Closed"
        else:
            status = f"Unknown ({status_byte})"

        return {
            "sensor_type": "magnetic",
            "status": status,
            "raw_payload": payload_hex
        }
    except Exception as e:
        return {'error': f"Magnetic sensor decode failed: {str(e)}"}

# ----------------------------
# DEVICE TO DECODER MAP
# ----------------------------

def get_decoder_by_device(device_id):
    device_id = device_id.lower()
    if device_id in POWER_TEMP_DEVICES:
        return decode_PowerTemp
    elif device_id in PULSE_METER_DEVICES:
        return decode_pulsemeter
    elif device_id in WATER_DETECT_DEVICES:
        return decode_water_sensor
    elif device_id in MAGNETIC_DEVICES:
        return decode_magnetic_sensor
    else:
        return None

# ----------------------------
# UTILITIES
# ----------------------------

def initialize_data_file():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)

def save_to_json(new_entry):
    initialize_data_file()
    with open(DATA_FILE, 'r+') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = []

        data.append(new_entry)
        f.seek(0)
        json.dump(data, f, indent=2)
        f.truncate()

# ----------------------------
# ROUTES
# ----------------------------

@app.route('/sigfox', methods=['POST'])
def sigfox_callback():
    try:
        data = request.get_json(force=True)
        hex_data = data.get("data", "")
        device_id = data.get("device", "").lower()

        decoder = get_decoder_by_device(device_id)

        if decoder:
            decoded_data = decoder(hex_data)
        else:
            decoded_data = {
                'ascii': bytes.fromhex(hex_data).decode('ascii', errors='replace'),
                'hex': hex_data,
                'note': 'No decoder assigned to this device ID'
            }

        entry = {
            "timestamp": data.get("time", datetime.utcnow().isoformat()),
            "device_id": device_id,
            "device_type": data.get("deviceTypeId", "unknown"),
            "sequence": data.get("seqNumber"),
            "raw_payload": hex_data,
            "decoded": decoded_data,
            "sensor_group": decoder.__name__ if decoder else "unassigned",
            "received_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        save_to_json(entry)

        print(f"📦 Saved entry: {json.dumps(entry, indent=2)}")
        return jsonify({"status": "success", "message": "Data saved"}), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Processing error: {str(e)}",
            "received_data": data if 'data' in locals() else None
        }), 500

@app.route('/data', methods=['GET'])
def get_data():
    try:
        initialize_data_file()
        with open(DATA_FILE, 'r') as f:
            return jsonify(json.load(f)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------------------
# MAIN ENTRY POINT
# ----------------------------

if __name__ == '__main__':
    initialize_data_file()
    app.run(host='0.0.0.0', port=5000, debug=True)
