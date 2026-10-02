"""
ESP32 Smart Irrigation IoT Telemetry and Pump Control routes.
Receives live soil moisture readings from field ESP32 microcontrollers,
controls relay pump triggers, and serves telemetry to farmer dashboards.
Restricted to authenticated farmers only (except /telemetry for hardware devices).
"""

from datetime import datetime
from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required

iot_bp = Blueprint('iot', __name__)

# In-memory state with database logging fallback
_iot_state = {
    'soil_moisture_pct': 58.5,
    'temperature_c': 28.2,
    'pump_status': 'OFF',
    'mode': 'AUTO',  # AUTO or MANUAL
    'auto_threshold_pct': 35.0,  # Turn pump ON if moisture drops below 35%
    'last_updated': datetime.now().isoformat(),
    'device_id': 'ESP32-AGRI-01'
}

_telemetry_history = [
    {'timestamp': '10:00', 'moisture': 65.0, 'pump': 'OFF'},
    {'timestamp': '12:00', 'moisture': 58.0, 'pump': 'OFF'},
    {'timestamp': '14:00', 'moisture': 42.0, 'pump': 'OFF'},
    {'timestamp': '16:00', 'moisture': 34.0, 'pump': 'ON'},
    {'timestamp': '18:00', 'moisture': 62.0, 'pump': 'OFF'}
]


@iot_bp.route('/telemetry', methods=['POST'])
def receive_telemetry():
    """
    Endpoint for field ESP32 hardware to post soil moisture readings over Wi-Fi.
    Intentionally left without JWT auth so physical devices can POST without a token.
    Payload: { "device_id": "...", "moisture_pct": 32.5, "temperature_c": 27.8, "pump_status": "OFF" }
    """
    data = request.get_json() or {}
    moisture = data.get('moisture_pct')
    if moisture is None:
        return jsonify({'error': 'Bad Request', 'message': 'moisture_pct is required.'}), 400

    try:
        moisture_val = float(moisture)
        _iot_state['soil_moisture_pct'] = moisture_val
        _iot_state['temperature_c'] = float(data.get('temperature_c', _iot_state['temperature_c']))
        _iot_state['last_updated'] = datetime.now().isoformat()
        if data.get('device_id'):
            _iot_state['device_id'] = data.get('device_id')

        # Automatic mode logic
        if _iot_state['mode'] == 'AUTO':
            if moisture_val < _iot_state['auto_threshold_pct']:
                _iot_state['pump_status'] = 'ON'
            elif moisture_val >= 60.0:
                _iot_state['pump_status'] = 'OFF'

        # Append to historical records
        _telemetry_history.append({
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'moisture': moisture_val,
            'pump': _iot_state['pump_status']
        })
        if len(_telemetry_history) > 30:
            _telemetry_history.pop(0)

        # Compact response without spaces ensures hardware ESP32 string matching succeeds
        # whether looking for "pump_status":"ON" or "pump_status": "ON"
        import json
        from flask import Response
        cmd_body = json.dumps({
            'status': 'success',
            'command': {
                'pump_status': _iot_state['pump_status'],
                'mode': _iot_state['mode']
            }
        }, separators=(',', ':'))

        return Response(cmd_body, mimetype='application/json'), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@iot_bp.route('/status', methods=['GET'])
@token_required
@roles_required('farmer', 'admin')
def get_irrigation_status():
    """Retrieve current field soil moisture, pump state, and history. Farmers & Admins."""
    return jsonify({
        'status': 'success',
        'live': _iot_state,
        'history': _telemetry_history
    }), 200


@iot_bp.route('/pump-control', methods=['POST'])
@token_required
@roles_required('farmer', 'admin')
def control_pump():
    """Farmer/Admin manual control to switch pump ON/OFF or toggle AUTO/MANUAL mode."""
    data = request.get_json() or {}

    new_pump = data.get('pump_status')
    new_mode = data.get('mode')
    new_threshold = data.get('threshold_pct')

    if new_pump in ('ON', 'OFF'):
        _iot_state['pump_status'] = new_pump
        # When farmer manually switches pump, automatically switch to MANUAL mode
        # unless mode was explicitly specified, preventing AUTO rules from immediately reverting it
        if not new_mode:
            _iot_state['mode'] = 'MANUAL'

    if new_mode in ('AUTO', 'MANUAL'):
        _iot_state['mode'] = new_mode

    if new_threshold is not None:
        try:
            _iot_state['auto_threshold_pct'] = float(new_threshold)
        except (ValueError, TypeError):
            pass

    _iot_state['last_updated'] = datetime.now().isoformat()

    # Record manual control event in history
    _telemetry_history.append({
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'moisture': _iot_state['soil_moisture_pct'],
        'pump': _iot_state['pump_status']
    })
    if len(_telemetry_history) > 30:
        _telemetry_history.pop(0)

    return jsonify({
        'status': 'success',
        'message': f"Irrigation updated: Pump {_iot_state['pump_status']}, Mode {_iot_state['mode']}.",
        'state': _iot_state
    }), 200
