"""
backend/routes/hubs.py
Dynamic Multi-Hub Management and Facility Operations for AgriSmart Connect.
Provides full Tamil Nadu aggregation hub administration, live capacity monitoring,
and inter-hub transfer queues.
"""

from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
    from services.order_state_machine import canonical_status
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required
    from backend.services.order_state_machine import canonical_status

hubs_bp = Blueprint('hubs', __name__)


@hubs_bp.route('', methods=['GET'])
def get_hubs():
    """List collection hubs across Tamil Nadu with dynamic capacity and status."""
    status_filter = request.args.get('status')
    district_filter = request.args.get('district')
    try:
        sql = """
            SELECT h.hub_id, h.hub_code, h.hub_name, h.address, h.village, h.district,
                   h.city, h.pincode, h.latitude, h.longitude,
                   COALESCE(h.geofence_radius, 500.0) AS geofence_radius,
                   COALESCE(h.service_radius, 45.0) AS service_radius,
                   COALESCE(h.daily_capacity, 1000) AS daily_capacity,
                   COALESCE(h.current_capacity, 0) AS current_capacity,
                   COALESCE(h.operating_hours, '06:00 AM - 08:00 PM') AS operating_hours,
                   h.status, h.cold_storage_available, h.storage_capabilities,
                   h.supported_products, h.manager_id, u.name AS manager_name,
                   h.created_at,
                   (
                       SELECT COUNT(*) FROM orders o
                       WHERE o.hub_id = h.hub_id AND o.order_status NOT IN ('delivered', 'cancelled', 'SETTLED', 'DELIVERED', 'ORDER_CANCELLED')
                   ) AS active_orders_count
            FROM hubs h
            LEFT JOIN users u ON h.manager_id = u.user_id
            WHERE 1=1
        """
        params = []
        if status_filter:
            sql += " AND UPPER(h.status) = UPPER(%s)"
            params.append(status_filter)
        if district_filter:
            sql += " AND LOWER(h.district) LIKE LOWER(%s)"
            params.append(f"%{district_filter}%")

        sql += " ORDER BY h.hub_id ASC;"
        hubs = fetch_all(sql, tuple(params) if params else None)

        # Normalize statuses
        for h in hubs:
            h['status'] = h['status'].upper() if h.get('status') else 'ACTIVE'
            h['available_capacity'] = max(0, int(h['daily_capacity']) - int(h['current_capacity']))

        return jsonify({'status': 'success', 'count': len(hubs), 'hubs': hubs}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@hubs_bp.route('/<int:hub_id>', methods=['GET'])
def get_hub(hub_id):
    """Retrieve details for a single hub including active loads."""
    try:
        hub = fetch_one("""
            SELECT h.*, u.name AS manager_name, u.phone AS manager_phone, u.email AS manager_email
            FROM hubs h
            LEFT JOIN users u ON h.manager_id = u.user_id
            WHERE h.hub_id = %s;
        """, (hub_id,))
        if not hub:
            return jsonify({'error': 'Not Found', 'message': 'Hub not found.'}), 404

        hub['status'] = hub['status'].upper() if hub.get('status') else 'ACTIVE'
        hub['available_capacity'] = max(0, int(hub.get('daily_capacity') or 1000) - int(hub.get('current_capacity') or 0))

        # Recent shipments at this hub
        shipments = fetch_all("""
            SELECT o.order_id, o.order_status, o.total_amount, o.order_date,
                   b.business_name, u.name AS buyer_name
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            JOIN users u ON b.user_id = u.user_id
            WHERE o.hub_id = %s OR o.source_hub_id = %s OR o.destination_hub_id = %s
            ORDER BY o.order_date DESC
            LIMIT 10;
        """, (hub_id, hub_id, hub_id))

        return jsonify({'status': 'success', 'hub': hub, 'recent_shipments': shipments}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@hubs_bp.route('', methods=['POST'])
@token_required
@roles_required('admin')
def create_hub():
    """Register a new collection hub anywhere in Tamil Nadu (Admin only)."""
    data = request.get_json() or {}
    hub_name = data.get('hub_name', '').strip()
    address = data.get('address', '').strip()
    district = data.get('district', '').strip()
    city = data.get('city', district).strip()
    village = data.get('village', '').strip()
    pincode = data.get('pincode', '').strip()
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    daily_capacity = int(data.get('daily_capacity') or data.get('capacity_kg') or 1000)
    operating_hours = data.get('operating_hours', '06:00 AM - 08:00 PM')
    cold_storage = bool(data.get('cold_storage_available', False))
    supported_products = data.get('supported_products', 'Vegetables, Fruits, Tubers, Spices, Grains')
    hub_code = data.get('hub_code') or f"HUB-{district[:3].upper() if len(district) >= 3 else 'TN'}-{random_code()}"
    manager_id = data.get('manager_id')

    if not all([hub_name, address, district, latitude, longitude]):
        return jsonify({'error': 'Bad Request', 'message': 'hub_name, address, district, latitude, longitude are required.'}), 400

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO hubs (
                    hub_code, hub_name, address, village, district, city, pincode,
                    latitude, longitude, capacity_kg, daily_capacity, operating_hours,
                    cold_storage_available, supported_products, status, manager_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s)
                RETURNING *;
            """, (
                hub_code, hub_name, address, village, district, city, pincode,
                latitude, longitude, daily_capacity, daily_capacity, operating_hours,
                cold_storage, supported_products, manager_id
            ))
            new_hub = dict(cur.fetchone())

        return jsonify({'status': 'success', 'message': f"Hub '{hub_name}' created successfully.", 'hub': new_hub}), 201
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@hubs_bp.route('/<int:hub_id>', methods=['PUT'])
@token_required
@roles_required('admin', 'hub_manager')
def update_hub(hub_id):
    """Update hub operational parameters, capacity, service area, and active status."""
    data = request.get_json() or {}
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("SELECT * FROM hubs WHERE hub_id = %s FOR UPDATE;", (hub_id,))
            hub = cur.fetchone()
            if not hub:
                return jsonify({'error': 'Not Found', 'message': 'Hub not found.'}), 404

            # Update fields
            fields = []
            values = []

            for col in ['hub_name', 'address', 'district', 'city', 'pincode', 'operating_hours', 'supported_products']:
                if col in data:
                    fields.append(f"{col} = %s")
                    values.append(data[col])

            if 'status' in data:
                raw_st = data['status'].upper()
                if raw_st in ('ACTIVE', 'INACTIVE', 'FULL', 'TEMPORARILY_CLOSED'):
                    fields.append("status = %s")
                    values.append(raw_st)

            if 'daily_capacity' in data:
                fields.append("daily_capacity = %s")
                values.append(int(data['daily_capacity']))

            if 'service_radius' in data:
                fields.append("service_radius = %s")
                values.append(float(data['service_radius']))

            if 'geofence_radius' in data:
                fields.append("geofence_radius = %s")
                values.append(float(data['geofence_radius']))

            if 'cold_storage_available' in data:
                fields.append("cold_storage_available = %s")
                values.append(bool(data['cold_storage_available']))

            if 'manager_id' in data:
                fields.append("manager_id = %s")
                values.append(data['manager_id'])

            if not fields:
                return jsonify({'status': 'success', 'message': 'No changes detected.'}), 200

            fields.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE hubs SET {', '.join(fields)} WHERE hub_id = %s RETURNING *;"
            values.append(hub_id)

            cur.execute(sql, tuple(values))
            updated = dict(cur.fetchone())

        return jsonify({'status': 'success', 'message': 'Hub updated successfully.', 'hub': updated}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@hubs_bp.route('/<int:hub_id>/shipments', methods=['GET'])
@token_required
@roles_required('hub_operator', 'hub_staff', 'hub_manager', 'admin')
def get_hub_shipments(hub_id):
    """
    Retrieve operational shipments segmented for Hub Dashboard:
    - incoming: Harvests arriving from farmers
    - awaiting_qc: Arrived at hub, pending quality grading
    - accepted: QC passed, staged for dispatch or transfer
    - rejected: QC failed / rejected
    - outgoing_transfers: Leaving this hub to destination hub
    - incoming_transfers: Inbound from other hubs
    - ready_last_mile: Final hub, ready for driver delivery
    - completed: Delivered
    """
    try:
        # Incoming harvests & orders currently routed through this hub
        orders = fetch_all("""
            SELECT o.*, b.business_name, u.name AS buyer_name, u.phone AS buyer_phone,
                   h_src.hub_name AS source_hub_name, h_dst.hub_name AS dest_hub_name,
                   d.status AS delivery_status, d.tracking_reference,
                   u_dp.name AS driver_name
            FROM orders o
            JOIN buyers b ON o.buyer_id = b.buyer_id
            JOIN users u ON b.user_id = u.user_id
            LEFT JOIN hubs h_src ON o.source_hub_id = h_src.hub_id
            LEFT JOIN hubs h_dst ON o.destination_hub_id = h_dst.hub_id
            LEFT JOIN deliveries d ON o.order_id = d.order_id
            LEFT JOIN users u_dp ON d.delivery_partner_id = u_dp.user_id
            WHERE o.hub_id = %s OR o.source_hub_id = %s OR o.destination_hub_id = %s
            ORDER BY o.order_date DESC;
        """, (hub_id, hub_id, hub_id))

        incoming = []
        awaiting_qc = []
        accepted = []
        rejected = []
        outgoing_transfers = []
        incoming_transfers = []
        ready_last_mile = []
        completed = []

        for o in orders:
            st = canonical_status(o['order_status'])
            is_source = (o.get('source_hub_id') == hub_id)
            is_dest = (o.get('destination_hub_id') == hub_id)

            if st in ('READY_FOR_PICKUP', 'PICKUP_ASSIGNED', 'PICKED_UP', 'IN_TRANSIT_TO_HUB'):
                incoming.append(o)
            elif st in ('ARRIVED_AT_HUB', 'HUB_QC'):
                awaiting_qc.append(o)
            elif st in ('HUB_ACCEPTED',):
                accepted.append(o)
            elif st in ('HUB_REJECTED', 'QC_FAILED'):
                rejected.append(o)
            elif st in ('HUB_TRANSFER_REQUIRED', 'IN_TRANSIT_TO_NEXT_HUB'):
                if is_source:
                    outgoing_transfers.append(o)
                if is_dest:
                    incoming_transfers.append(o)
            elif st in ('ARRIVED_AT_NEXT_HUB', 'ASSIGNED_TO_DELIVERY'):
                ready_last_mile.append(o)
            elif st in ('OUT_FOR_DELIVERY', 'DELIVERED', 'SETTLED'):
                completed.append(o)

        return jsonify({
            'status': 'success',
            'hub_id': hub_id,
            'queues': {
                'incoming': incoming,
                'awaiting_qc': awaiting_qc,
                'accepted': accepted,
                'rejected': rejected,
                'outgoing_transfers': outgoing_transfers,
                'incoming_transfers': incoming_transfers,
                'ready_last_mile': ready_last_mile,
                'completed': completed
            }
        }), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@hubs_bp.route('/<int:hub_id>/transfers', methods=['GET'])
@token_required
@roles_required('hub_operator', 'hub_staff', 'hub_manager', 'delivery_partner', 'admin')
def get_hub_transfers(hub_id):
    """Retrieve all inter-hub transfers involving this facility."""
    try:
        transfers = fetch_all("""
            SELECT ht.*, o.delivery_address, o.total_amount,
                   h1.hub_name AS src_hub_name, h2.hub_name AS dst_hub_name,
                   u.name AS driver_name, u.phone AS driver_phone
            FROM hub_transfers ht
            JOIN orders o ON ht.order_id = o.order_id
            JOIN hubs h1 ON ht.source_hub_id = h1.hub_id
            JOIN hubs h2 ON ht.destination_hub_id = h2.hub_id
            LEFT JOIN users u ON ht.delivery_partner_id = u.user_id
            WHERE ht.source_hub_id = %s OR ht.destination_hub_id = %s
            ORDER BY ht.created_at DESC;
        """, (hub_id, hub_id))
        return jsonify({'status': 'success', 'transfers': transfers}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


def random_code():
    import random
    return f"{random.randint(10, 99)}"
