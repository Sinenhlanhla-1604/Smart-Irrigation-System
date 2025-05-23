from flask import Flask, request, jsonify, render_template, redirect, url_for
import struct
from datetime import datetime
import json
from pages import app_pages
from auth import auth
from functools import wraps
from db import save_useful_data, save_to_db

app = Flask(__name__)
app.secret_key = 'your-super-secret-key'


# Register blueprints
app.register_blueprint(app_pages)
app.register_blueprint(auth)

# ----------------------------
# Sensor Group Configuration
# ----------------------------
POWER_TEMP_DEVICES = {"1fc5622", "1fc57ca"}
PULSE_METER_DEVICES = {"1fc74ab","1fa5f9c"}
WATER_DETECT_DEVICES = {"c6e542", "c53d89", "c6d3a6"}
MAGNETIC_DEVICES = {"1f7f022","c52fce"}

# ----------------------------
# Home Redirect
# ----------------------------

@app.route('/')
def root():
    return redirect(url_for('pages.user_dashboard'))

# ----------------------------
# Decoders
# ----------------------------

def decode_PowerTemp(payload_hex):
    """
    Decodes PowerTemp sensor data from a 5-byte hex payload.
    Uses dynamic divisor selection to estimate temperature accurately,
    and extracts battery voltage and status flags.
    """
    try:
        data = bytes.fromhex(payload_hex)

        if len(data) != 5:
            return {
                'battery_volts': None,
                'temp_celsius': None,
                'status_flags': []
            }

        # Battery (2 bytes)
        battery_raw = struct.unpack('>H', data[0:2])[0]
        battery_volts = round(battery_raw / 20958.0, 2)

        # Temperature (2 bytes)
        temp_raw = struct.unpack('>H', data[2:4])[0]

        # Dynamic divisor selection for best temp estimate (realistic 5-50 °C range)
        best_temp = None
        best_divisor = None
        min_error = float('inf')

        for divisor in [x / 10 for x in range(200, 1001)]:  # Divisor from 20.0 to 100.0 step 0.1
            temp = temp_raw / divisor
            if 5 <= temp <= 50:  # realistic temperature range for this sensor
                rounded_temp = round(temp)
                error = abs(temp - rounded_temp)
                if error < min_error:
                    best_temp = round(temp, 1)
                    best_divisor = divisor
                    min_error = error
                    if error == 0:
                        break  # perfect match

        temp_celsius = best_temp

        # Flags (1 byte)
        flags = data[4]
        active_flags = []
        if flags & 0b00000001: active_flags.append("Power Up")
        if flags & 0b00000010: active_flags.append("Forced Transmit")
        if flags & 0b00000100: active_flags.append("Power Alert")
        if flags & 0b00001000: active_flags.append("Temperature Alert")
        if flags & 0b00010000: active_flags.append("Periodic Update")
        if flags & 0b00100000: active_flags.append("TX Update Timer")

        tx_index = (flags >> 5) & 0b00000111
        if tx_index == 7:
            active_flags.append("24 Hour Tx 6 Hour Record Offset")

        return {
            'battery_volts': battery_volts,
            'temp_celsius': temp_celsius,
            'status_flags': active_flags,
            'debug_temp_raw': temp_raw,
            'debug_best_divisor': round(best_divisor, 2) if best_divisor else None
        }

    except Exception:
        return {
            'battery_volts': None,
            'temp_celsius': None,
            'status_flags': []
        }


def decode_pulsemeter(payload_hex):
    """
    Decodes PulseMeter data (12-byte or 8-byte payload).
    Returns only required fields for database insertion.
    """
    try:
        data = bytes.fromhex(payload_hex)
        length = len(data)

        if length not in [8, 12]:
            return {'error': f'Unknown PulseMeter payload length: {length} bytes'}

        txflags = data[0]
        battery_raw = data[1]
        battery_volts = round(battery_raw * 0.02, 2)
        pulse_count = int.from_bytes(data[2:6], byteorder='big')

        # Decode flags into human-readable strings
        active_flags = []
        if txflags & 0b00000001: active_flags.append("Periodic Update")
        if txflags & 0b00000010: active_flags.append("Forced Transmit / Power Up")
        if txflags & 0b00000100: active_flags.append("Leak/Tamper Alert")
        if txflags & 0b00001000: active_flags.append("Leak Detected")
        if txflags & 0b00010000: active_flags.append("Tamper Detected")

        return {
            'pulse_count': pulse_count,
            'battery_volts': battery_volts,
            'leak_detected': "Leak Detected" in active_flags,
            'status_flags': active_flags
        }

    except Exception as e:
        return {'error': f"PulseMeter decode failed: {str(e)}"}




def decode_water_sensor(payload_hex, timestamp=None, water_threshold=100):
    try:
        if len(payload_hex) != 16:
            return {'error': 'Payload must be 16 hex characters'}

        data = bytes.fromhex(payload_hex)

        # --- Battery Voltage (calibrated) ---
        battery_raw = struct.unpack('<H', data[0:2])[0]
        battery_volts = round(battery_raw * 0.01 + 2.3, 2)

        # --- Water Detection ---
        water_raw = data[2]
        water_detected = (water_raw < water_threshold)

        # --- Config Flags ---
        config_flags = data[3]
        transmit_mode_values = ["water_detect", "no_water", "both", "unknown"]
        transmit_mode = transmit_mode_values[config_flags & 0x03]
        heartbeat_hours = (config_flags >> 2) & 0x0F
        sensitivity_values = ["low", "medium", "high", "very_high"]
        sensitivity = sensitivity_values[(config_flags >> 6) & 0x03]

        # --- RTX Value ---
        rtx_value = struct.unpack('<I', data[4:8])[0]

        return {
            'battery_volts': battery_volts,
            'water_detected': water_detected,
            'water_raw_value': water_raw,
            'alerts': [],
            'raw_payload': payload_hex,
            'timestamp': timestamp or datetime.now().isoformat()
        }

    except Exception as e:
        return {'error': f"Decode error: {str(e)}"}
    

def decode_magnetic_sensor(payload_hex):
    try:
        data = bytes.fromhex(payload_hex)
        if len(data) < 2:
            return {'error': 'Invalid magnetic sensor payload length'}
        status = "Open" if data[1] == 0x00 else "Closed" if data[1] == 0x01 else f"Unknown ({data[1]})"
        return {
            "sensor_type": "magnetic",
            "status": status,
            "raw_payload": payload_hex
        }
    except Exception as e:
        return {'error': f"Magnetic sensor decode failed: {str(e)}"}

# ----------------------------
# Decoder Dispatcher
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
    return None

# ----------------------------
# Sigfox Receiver
# ----------------------------

@app.route('/sigfox', methods=['POST'])
def sigfox_callback():
    try:
        data = request.get_json(force=True)
        hex_data = data.get("data", "")
        device_id = data.get("device", "").lower()
        decoder = get_decoder_by_device(device_id)

        decoded = decoder(hex_data) if decoder else {
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
            "decoded": decoded,
            "sensor_group": decoder.__name__ if decoder else "unassigned",
            "received_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        save_to_db(entry)
        save_useful_data(entry)

        print(f"📦 Saved entry:\n{json.dumps(entry, indent=2)}")
        return jsonify({"status": "success", "message": "Data saved"}), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Processing error: {str(e)}"
        }), 500

# ----------------------------
# Data API
# ----------------------------


# ----------------------------
# Entry Point
# ----------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
