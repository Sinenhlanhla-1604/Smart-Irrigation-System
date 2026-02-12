from flask import Flask, request, jsonify, render_template, redirect, url_for
import struct
from datetime import datetime, timedelta, timezone
import json
from pages import app_pages
from auth import auth
from functools import wraps
from db import get_db_connection, save_useful_data, save_to_db

app = Flask(__name__)
app.secret_key = 'your-super-secret-key'


# Register blueprints
app.register_blueprint(app_pages)
app.register_blueprint(auth)

# ----------------------------
# Sensor Group Configuration
# ----------------------------
POWER_TEMP_DEVICES = {"1fc5622", "1fc57ca", "1fc56c3"}
PULSE_METER_DEVICES = {"1fc74ab","1fa5f9c"}
WATER_DETECT_DEVICES = {"c6e542", "c53d89", "c6d3a6", "c6da55"}
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

from datetime import datetime, timedelta

def convert_to_signed(byte_str):
    val = int(byte_str, 16)
    return val - 256 if val > 127 else val

def decode_PowerTemp(payload_hex, base_unix_time=1748265008):
    try:
        tx_flag = int(payload_hex[0:2], 16)
        is_periodic = (tx_flag & 0x10) == 0x10

        battery_voltage = round(int(payload_hex[2:4], 16) * 0.02, 2)
        status_mask = int(payload_hex[4:6], 16)
        temp_current = convert_to_signed(payload_hex[6:8])

        result = {
            'tx_flag': tx_flag,
            'is_periodic': is_periodic,
            'battery_volts': battery_voltage,
            'status_mask': status_mask,
            'temp_celsius': temp_current,
            'timestamp': datetime.utcfromtimestamp(base_unix_time).isoformat(),
            'temp_history': [],
            'alerts': []
        }

        if is_periodic:
            # Determine periodic interval in hours from tx_flag (bits 5,6,7)
            device_interval = (tx_flag >> 5) & 0x07
            interval_map = {
                0: -0.25,
                1: -0.5,
                2: -1,
                3: -2,
                4: -3,
                5: -4,
                6: -5,
                7: -6
            }
            time_period = interval_map.get(device_interval, -1)

            base_time = datetime.utcfromtimestamp(base_unix_time)
            history = []

            # Extract and timestamp the 4 historical temperature min/max pairs
            for i in range(4):
                offset = 8 + i * 4
                t_min = convert_to_signed(payload_hex[offset:offset+2])
                t_max = convert_to_signed(payload_hex[offset+2:offset+4])
                timestamp = base_time + timedelta(hours=time_period * i)
                history.append({
                    'min_temp': t_min,
                    'max_temp': t_max,
                    'timestamp': timestamp.isoformat()
                })
            result['temp_history'] = history

        else:
            # It's an alert payload
            tx_info_mask = int(payload_hex[8:10], 16)
            if (tx_flag & 0x08):
                result['alerts'].append('Temperature Alert')
            if (tx_flag & 0x04):
                result['alerts'].append('Power Alert')
            if tx_info_mask & 0x40:
                result['alerts'].append('Temperature Low Alert')

        return result

    except Exception as e:
        return {
            'battery_volts': None,
            'temp_celsius': None,
            'status_flags': [],
            'error': f'Decode error: {str(e)}'
        }


def decode_pulsemeter(payload_hex, timestamp_unix=1748265008):
    """
    Decodes PulseMeter data (12-byte periodic or 8-byte alert payload).
    Returns structured data for storage or logging.
    """
    try:
        data = bytes.fromhex(payload_hex)
        length = len(data)

        if length not in [8, 9, 12]:
            return {'error': f'Unknown PulseMeter payload length: {length} bytes', 'raw_hex': payload_hex, 'raw_bytes': data.hex()}

        txflags = data[0]
        battery_raw = data[1]
        battery_volts = round(battery_raw * 0.02, 2)

        # Decode flags into human-readable strings
        active_flags = []
        if txflags & 0b00000001: active_flags.append("Periodic Update")
        if txflags & 0b00000010: active_flags.append("Forced Transmit / Power Up")
        if txflags & 0b00000100: active_flags.append("Leak/Tamper Alert")
        if txflags & 0b00001000: active_flags.append("Leak Detected")
        if txflags & 0b00010000: active_flags.append("Tamper Detected")

        result = {
            'battery_volts': battery_volts,
            'leak_detected': "Leak Detected" in active_flags,
            'status_flags': active_flags,
            'debug_info': {
                'payload_length': length,
                'raw_hex': payload_hex,
                'txflags_binary': f'{txflags:08b}',
                'battery_raw': battery_raw
            }
        }

        if length == 12:
            # Periodic payload
            device_interval = (txflags >> 5) & 0b111
            interval_map = {
                0: -0.25,
                1: -0.5,
                2: -1,
                3: -2,
                4: -3,
                5: -4,
                6: -5,
                7: -6
            }
            timer_period = interval_map.get(device_interval, 0)

            counter0 = int.from_bytes(data[2:6], byteorder='big')
            offset1 = int.from_bytes(data[6:8], byteorder='big')
            offset2 = int.from_bytes(data[8:10], byteorder='big')
            offset3 = int.from_bytes(data[10:12], byteorder='big')

            # Use the modern datetime approach with timezone awareness
            counter0_time = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
            counter1_time = counter0_time + timedelta(hours=timer_period * 1)
            counter2_time = counter0_time + timedelta(hours=timer_period * 2)
            counter3_time = counter0_time + timedelta(hours=timer_period * 3)

            result.update({
                'pulse_count': counter0,
                'history': [
                    {'timestamp': counter0_time.isoformat(), 'value': counter0},
                    {'timestamp': counter1_time.isoformat(), 'value': counter0 - offset1},
                    {'timestamp': counter2_time.isoformat(), 'value': counter0 - offset2},
                    {'timestamp': counter3_time.isoformat(), 'value': counter0 - offset3}
                ]
            })

        elif length == 8:
            # Alert payload
            pulse_count = int.from_bytes(data[2:6], byteorder='big')
            result.update({
                'pulse_count': pulse_count
            })

        elif length == 9:
            # 9-byte payload - need to determine structure
            # For now, treat similar to 8-byte but capture extra byte
            pulse_count = int.from_bytes(data[2:6], byteorder='big')
            extra_data = data[6:9].hex()  # Last 3 bytes as hex string
            result.update({
                'pulse_count': pulse_count,
                'extra_data': extra_data,
                'payload_type': '9-byte_variant'
            })

        return result

    except Exception as e:
        return {'error': f"PulseMeter decode failed: {str(e)}"}




def decode_water_sensor(payload_hex, timestamp=None, water_threshold=150):
    try:
        # Convert payload to usable hex segments
        tx_flag = int(payload_hex[0:2], 16)
        water_detected = int(payload_hex[2:4], 16) == 1
        water_raw = int(payload_hex[4:6], 16)
        battery_hex = int(payload_hex[6:8], 16)
        battery_volts = battery_hex * 0.02
        counter_value = int(payload_hex[8:16], 16)

        # Determine if this was a state change (bit 1 = 0x02)
        is_state_change = (tx_flag & 0x02) == 0x02

        alerts = []
        if water_detected and water_raw <= water_threshold:
            alerts.append("Water detected below threshold")
        if battery_volts < 2.5:
            alerts.append("Low battery")

        return {
            'tx_flag': tx_flag,
            'is_state_change': is_state_change,
            'water_detected': water_detected,
            'water_raw_value': water_raw,
            'battery_volts': round(battery_volts, 2),
            'counter_value': counter_value,
            'alerts': alerts,
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
# Sigfox API Receiver
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
@app.route('/api/user/temperature')
def get_temperature_charts():
    period = request.args.get('period', 'Weekly')

    period_map = {
        'Daily': "1 day",
        'Weekly': "7 days",
        'Monthly': "30 days",
        'All': "365 days"
    }

    interval = period_map.get(period, "7 days")

    query = """
    SELECT
        device_id,
        DATE(received_at) AS day,
        AVG(temp_celsius) AS avg_temp,
        MAX(temp_celsius) AS max_temp,
        MIN(temp_celsius) AS min_temp
    FROM PWR_TEMP
    WHERE received_at >= NOW() - INTERVAL %s
    GROUP BY device_id, day
    ORDER BY day;
    """

    charts = {}

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (interval,))
            rows = cur.fetchall()

            for device_id, day, avg_t, max_t, min_t in rows:
                charts.setdefault(device_id, {
                    "labels": [],
                    "avg_temperatures": [],
                    "max_temperatures": [],
                    "min_temperatures": [],
                    "avg": None,
                    "max": None,
                    "min": None
                })

                charts[device_id]["labels"].append(day.strftime("%m-%d"))
                charts[device_id]["avg_temperatures"].append(round(avg_t, 1))
                charts[device_id]["max_temperatures"].append(round(max_t, 1))
                charts[device_id]["min_temperatures"].append(round(min_t, 1))

            for device_id, data in charts.items():
                data["avg"] = round(sum(data["avg_temperatures"]) / len(data["avg_temperatures"]), 1)
                data["max"] = max(data["max_temperatures"])
                data["min"] = min(data["min_temperatures"])

    return jsonify({"charts": charts})


@app.route('/api/user/usage')
def get_water_usage():
    period = request.args.get('period', 'Weekly')

    period_map = {
        'Daily': '1 day',
        'Weekly': '7 days',
        'Monthly': '30 days',
        'All': '365 days'
    }

    interval = period_map.get(period, '7 days')

    query = """
    SELECT
        DATE(received_at) AS day,
        MAX(pulse_count) - MIN(pulse_count) AS daily_usage
    FROM PULSE_DETECTOR
    WHERE received_at >= NOW() - INTERVAL %s
    GROUP BY day
    ORDER BY day;
    """

    labels = []
    values = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (interval,))
            for day, usage in cur.fetchall():
                labels.append(day.strftime('%a'))
                values.append(int(usage or 0))

    return jsonify({
        "labels": labels,
        "values": values
    })

    # Add this new route to app.py in the Data API section
@app.route('/api/user/temperature-history')
def get_temperature_history():
    period = request.args.get('period', 'Weekly')
    device_id = request.args.get('device_id')  # Optional: filter by specific device

    period_map = {
        'Daily': "1 day",
        'Weekly': "7 days",
        'Monthly': "30 days",
        'All': "365 days"
    }

    interval = period_map.get(period, "7 days")
    
    # Build the query based on whether device_id is provided
    if device_id:
        query = """
        SELECT
            device_id,
            DATE(received_at) AS day,
            DATE_TRUNC('hour', received_at) AS hour,
            AVG(temp_celsius) AS avg_temp,
            MAX(temp_celsius) AS max_temp,
            MIN(temp_celsius) AS min_temp
        FROM PWR_TEMP
        WHERE received_at >= NOW() - INTERVAL %s
            AND device_id = %s
        GROUP BY device_id, day, DATE_TRUNC('hour', received_at)
        ORDER BY hour;
        """
        params = (interval, device_id)
    else:
        query = """
        SELECT
            device_id,
            DATE(received_at) AS day,
            DATE_TRUNC('hour', received_at) AS hour,
            AVG(temp_celsius) AS avg_temp,
            MAX(temp_celsius) AS max_temp,
            MIN(temp_celsius) AS min_temp
        FROM PWR_TEMP
        WHERE received_at >= NOW() - INTERVAL %s
        GROUP BY device_id, day, DATE_TRUNC('hour', received_at)
        ORDER BY hour;
        """
        params = (interval,)

    history_data = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

            for row in rows:
                device_id, day, hour, avg_temp, max_temp, min_temp = row
                history_data.append({
                    "device_id": device_id,
                    "day": day.strftime("%Y-%m-%d"),
                    "hour": hour.strftime("%H:%M"),
                    "avg_temp": round(avg_temp, 1),
                    "max_temp": round(max_temp, 1),
                    "min_temp": round(min_temp, 1)
                })

    return jsonify({
        "period": period,
        "device_id": device_id,
        "data": history_data
    })


@app.route('/api/user/water-detection-history')
def get_water_detection_history():
    period = request.args.get('period', 'Weekly')
    device_id = request.args.get('device_id', 'all')
    
    period_map = {
        'Daily': "1 day",
        'Weekly': "7 days",
        'Monthly': "30 days",
        'All': "365 days"
    }
    
    interval = period_map.get(period, "7 days")
    
    # Base query
    if device_id != 'all':
        query = """
        SELECT 
            device_id,
            DATE(received_at) as event_date,
            TIME(received_at) as event_time,
            received_at,
            water_detected,
            water_raw_value,
            battery_volts
        FROM WATER_DETECTION 
        WHERE received_at >= NOW() - INTERVAL %s
            AND device_id = %s
        ORDER BY received_at DESC
        """
        params = (interval, device_id)
    else:
        query = """
        SELECT 
            device_id,
            DATE(received_at) as event_date,
            TIME(received_at) as event_time,
            received_at,
            water_detected,
            water_raw_value,
            battery_volts
        FROM WATER_DETECTION 
        WHERE received_at >= NOW() - INTERVAL %s
        ORDER BY received_at DESC
        """
        params = (interval,)
    
    history_data = []
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            
            for row in rows:
                device_id_row, event_date, event_time, received_at, water_detected, water_raw, battery = row
                history_data.append({
                    "device_id": device_id_row,
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": event_time.strftime("%H:%M:%S"),
                    "status": "Wet" if water_detected else "Dry",
                    "raw_value": water_raw,
                    "battery": round(float(battery), 2) if battery else None,
                    "timestamp": received_at.isoformat()
                })
    
    # Also get state change events to show when devices transition
    # ⚠️ FIXED: Changed 'receied_at' to 'received_at' in ORDER BY clause
    state_change_query = """
    SELECT 
        device_id,
        DATE(received_at) as event_date,
        TIME(received_at) as event_time,
        water_detected,
        received_at
    FROM WATER_DETECTION 
    WHERE received_at >= NOW() - INTERVAL %s
    ORDER BY device_id, received_at ASC
    """
    
    state_changes = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(state_change_query, (interval,))
            rows = cur.fetchall()
            
            # Group by device_id and find state changes
            device_events = {}
            for row in rows:
                device_id_val, event_date, event_time, water_detected, received_at = row
                
                # ⚠️ FIXED: Proper indentation - this block should be inside the loop
                if device_id_val not in device_events:
                    device_events[device_id_val] = []
                device_events[device_id_val].append({
                    "device_id": device_id_val,
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": event_time.strftime("%H:%M:%S"),
                    # ⚠️ FIXED: Changed 'water-detected' to 'water_detected' (underscore not hyphen)
                    "water_detected": water_detected,
                    "received_at": received_at
                })
            
            # Find state changes for each device
            for device, events in device_events.items():
                # Sort events by timestamp
                events.sort(key=lambda x: x['received_at'])
                
                previous_state = None
                
                for event in events:
                    current_state = event['water_detected']
                    
                    if previous_state is not None and current_state != previous_state:
                        state_changes.append({
                            "device_id": event['device_id'],
                            "date": event['date'],
                            "time": event['time'],
                            "changed_to": "Wet" if current_state else "Dry",
                            "changed_from": "Wet" if previous_state else "Dry"
                        })
                    
                    previous_state = current_state
    
    # Filter by device_id if needed
    if device_id != 'all':
        state_changes = [change for change in state_changes if change['device_id'] == device_id]
    
    # Sort state changes by date/time (most recent first)
    state_changes.sort(key=lambda x: (x['date'], x['time']), reverse=True)
    
    return jsonify({
        "period": period,
        "device_id": device_id,
        "history": history_data,
        "state_changes": state_changes
    })







# ----------------------------
# Entry Point
# ----------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
