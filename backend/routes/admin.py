"""
Super Admin Command Center API routes for AgriSmart Connect.
Provides platform-wide KPIs, surplus management, user controls, and analytics reports.
"""

from datetime import date
from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one, get_db_cursor
    from auth_middleware import token_required, roles_required
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor
    from backend.auth_middleware import token_required, roles_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/dashboard', methods=['GET'])
@token_required
@roles_required('admin')
def get_admin_dashboard():
    """Aggregate high-level platform performance metrics and operational health."""
    try:
        # Users counts
        counts = fetch_one("""
            SELECT 
                (SELECT COUNT(*) FROM users WHERE role = 'farmer') AS total_farmers,
                (SELECT COUNT(*) FROM users WHERE role IN ('consumer', 'restaurant', 'retailer')) AS total_buyers,
                (SELECT COUNT(*) FROM hubs WHERE status = 'active') AS active_hubs;
        """)

        # Orders metrics
        orders_stat = fetch_one("""
            SELECT 
                COUNT(*) AS total_orders,
                COALESCE(SUM(CASE WHEN order_date::date = CURRENT_DATE THEN 1 ELSE 0 END), 0) AS today_orders,
                COALESCE(SUM(total_amount), 0) AS total_sales,
                COALESCE(SUM(CASE WHEN order_status = 'delivered' THEN total_amount ELSE 0 END), 0) AS fulfilled_sales,
                COALESCE(SUM(platform_fee), 0) AS total_platform_revenue
            FROM orders
            WHERE order_status != 'cancelled';
        """)

        # Payouts metrics
        payouts_stat = fetch_one("""
            SELECT 
                COALESCE(SUM(CASE WHEN payout_status IN ('pending', 'processing') THEN net_amount ELSE 0 END), 0) AS pending_payouts,
                COALESCE(SUM(CASE WHEN payout_status = 'paid' THEN net_amount ELSE 0 END), 0) AS disbursed_payouts
            FROM farmer_payouts;
        """)

        # Produce supply and surplus
        produce_stat = fetch_one("""
            SELECT 
                COALESCE(SUM(available_quantity_kg), 0) AS total_available_kg,
                COALESCE(SUM(reserved_quantity_kg), 0) AS total_reserved_kg,
                COALESCE(SUM(sold_quantity_kg), 0) AS total_sold_kg
            FROM farmer_produce
            WHERE status != 'cancelled';
        """)

        # Identify Surplus Produce (available supply with approaching harvest or past date without matching demand)
        surplus_items = fetch_all("""
            SELECT fp.produce_id, c.crop_name, v.variety_name,
                   fp.available_quantity_kg, fp.minimum_price_per_kg,
                   fp.harvest_date, fp_prof.farm_name, h.hub_name
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            JOIN farmer_profiles fp_prof ON fp.farmer_id = fp_prof.farmer_id
            LEFT JOIN hubs h ON fp.preferred_hub_id = h.hub_id
            WHERE fp.status = 'available'
              AND fp.available_quantity_kg > 100
              AND fp.harvest_date <= CURRENT_DATE + INTERVAL '3 days'
            ORDER BY fp.available_quantity_kg DESC
            LIMIT 5;
        """)

        return jsonify({
            'status': 'success',
            'overview': {
                **counts,
                **orders_stat,
                **payouts_stat,
                **produce_stat
            },
            'surplus_alerts': surplus_items
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@admin_bp.route('/users', methods=['GET'])
@token_required
@roles_required('admin')
def list_admin_users():
    """List all platform users with role, registration date, and status."""
    role_filter = request.args.get('role')
    query = """
        SELECT u.user_id, u.name, u.phone, u.email, u.role, u.is_active, u.created_at,
               fp.farm_name, b.business_name
        FROM users u
        LEFT JOIN farmer_profiles fp ON u.user_id = fp.user_id
        LEFT JOIN buyers b ON u.user_id = b.user_id
    """
    params = []
    if role_filter:
        query += " WHERE u.role = %s"
        params.append(role_filter)

    query += " ORDER BY u.created_at DESC;"

    try:
        users = fetch_all(query, tuple(params) if params else None)
        return jsonify({'status': 'success', 'users': users}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@admin_bp.route('/users/<int:user_id>/toggle-status', methods=['PUT'])
@token_required
@roles_required('admin')
def toggle_user_status(user_id):
    """Suspend or activate a user account."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE users
                SET is_active = NOT is_active
                WHERE user_id = %s
                RETURNING user_id, name, is_active;
            """, (user_id,))
            user = cur.fetchone()

        if not user:
            return jsonify({'error': 'Not Found', 'message': 'User not found.'}), 404

        return jsonify({
            'status': 'success',
            'message': f"User account {'activated' if user['is_active'] else 'suspended'}.",
            'user': dict(user)
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@admin_bp.route('/reports', methods=['GET'])
@token_required
@roles_required('admin')
def get_admin_reports():
    """Retrieve detailed crop sales volume and hub performance reports."""
    try:
        # Sales by crop
        crop_sales = fetch_all("""
            SELECT c.crop_name, c.category,
                   COUNT(oi.order_item_id) AS total_orders,
                   COALESCE(SUM(oi.quantity_kg), 0) AS total_kg_sold,
                   COALESCE(SUM(oi.subtotal), 0) AS total_revenue
            FROM crops c
            LEFT JOIN order_items oi ON c.crop_id = oi.crop_id
            GROUP BY c.crop_id
            ORDER BY total_kg_sold DESC;
        """)

        # Hub fulfillment stats
        hub_stats = fetch_all("""
            SELECT h.hub_id, h.hub_name, h.district, h.capacity_kg,
                   COUNT(o.order_id) AS total_orders_routed,
                   COALESCE(SUM(o.total_amount), 0) AS total_routed_amount
            FROM hubs h
            LEFT JOIN orders o ON h.hub_id = o.hub_id
            GROUP BY h.hub_id
            ORDER BY total_orders_routed DESC;
        """)

        return jsonify({
            'status': 'success',
            'crop_sales': crop_sales,
            'hub_performance': hub_stats
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@admin_bp.route('/products', methods=['GET'])
@token_required
@roles_required('admin')
def list_admin_products():
    """List all farmer products for moderation, approval, and management."""
    status_filter = request.args.get('status')
    query = """
        SELECT fp.*, c.crop_name, v.variety_name, fp_prof.farm_name,
               fp_prof.district AS farm_district, u.name AS farmer_name,
               h.hub_name
        FROM farmer_produce fp
        JOIN crops c ON fp.crop_id = c.crop_id
        LEFT JOIN varieties v ON fp.variety_id = v.variety_id
        JOIN farmer_profiles fp_prof ON fp.farmer_id = fp_prof.farmer_id
        JOIN users u ON fp_prof.user_id = u.user_id
        LEFT JOIN hubs h ON fp.preferred_hub_id = h.hub_id
    """
    params = []
    if status_filter:
        query += " WHERE fp.status = %s OR fp.moderation_status = %s"
        params.extend([status_filter, status_filter])

    query += " ORDER BY fp.created_at DESC LIMIT 50;"
    try:
        products = fetch_all(query, tuple(params) if params else None)
        return jsonify({'status': 'success', 'products': products}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@admin_bp.route('/products/<int:produce_id>/status', methods=['PUT'])
@token_required
@roles_required('admin')
def moderate_product(produce_id):
    """Admin moderate product: approve, reject, pause, activate, or archive."""
    data = request.get_json() or {}
    status = data.get('status', 'ACTIVE')
    moderation_status = data.get('moderation_status', 'APPROVED')

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE farmer_produce
                SET status = %s, moderation_status = %s
                WHERE produce_id = %s
                RETURNING produce_id, status, moderation_status;
            """, (status, moderation_status, produce_id))
            res = cur.fetchone()

        if not res:
            return jsonify({'error': 'Not Found', 'message': 'Product not found.'}), 404

        return jsonify({'status': 'success', 'message': f'Product updated to {status}', 'product': dict(res)}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@admin_bp.route('/hubs', methods=['GET'])
@token_required
@roles_required('admin')
def list_admin_hubs():
    """List all collection hubs with configuration details and operational inventory."""
    try:
        hubs = fetch_all("""
            SELECT h.*, 
                   COALESCE(h.current_inventory_kg, 0) AS current_inventory_kg,
                   COUNT(p.produce_id) AS allocated_batches_count
            FROM hubs h
            LEFT JOIN farmer_produce p ON h.hub_id = p.preferred_hub_id AND p.status IN ('available', 'ACTIVE')
            GROUP BY h.hub_id
            ORDER BY h.district ASC, h.hub_name ASC;
        """)
        return jsonify({'status': 'success', 'hubs': hubs}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@admin_bp.route('/hubs/<int:hub_id>', methods=['PUT'])
@token_required
@roles_required('admin')
def update_admin_hub(hub_id):
    """Edit hub configuration: location, capacity, delivery radius, workers, status."""
    data = request.get_json() or {}
    hub_name = data.get('hub_name')
    district = data.get('district')
    taluk = data.get('taluk')
    town = data.get('town')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    capacity_kg = data.get('capacity_kg')
    delivery_radius_km = data.get('delivery_radius_km')
    status = data.get('status')

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE hubs
                SET hub_name = COALESCE(%s, hub_name),
                    district = COALESCE(%s, district),
                    taluk = COALESCE(%s, taluk),
                    town = COALESCE(%s, town),
                    latitude = COALESCE(%s, latitude),
                    longitude = COALESCE(%s, longitude),
                    capacity_kg = COALESCE(%s, capacity_kg),
                    delivery_radius_km = COALESCE(%s, delivery_radius_km),
                    status = COALESCE(%s, status)
                WHERE hub_id = %s
                RETURNING *;
            """, (hub_name, district, taluk, town, latitude, longitude, capacity_kg, delivery_radius_km, status, hub_id))
            updated = cur.fetchone()

        if not updated:
            return jsonify({'error': 'Not Found', 'message': 'Hub not found.'}), 404

        return jsonify({'status': 'success', 'message': 'Hub configuration updated successfully.', 'hub': dict(updated)}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# ====================================================================
# DEMO PRODUCT IMAGES MANAGEMENT
# ====================================================================

@admin_bp.route('/demo-images', methods=['GET'])
@token_required
@roles_required('admin')
def list_demo_product_images():
    """List all demo products with image status, source metadata, and verification."""
    import os
    from pathlib import Path

    try:
        frontend_dir = Path(__file__).resolve().parent.parent.parent / 'frontend'

        query = """
            SELECT fp.produce_id, fp.product_name, c.crop_name, v.variety_name,
                   fp_prof.farm_name, u.name AS farmer_name, u.email AS farmer_email,
                   pi.image_id, pi.image_url, pi.storage_path, pi.is_primary,
                   pi.display_order, pi.source, pi.source_url, pi.license,
                   pi.attribution, pi.alt_text
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            JOIN farmer_profiles fp_prof ON fp.farmer_id = fp_prof.farmer_id
            JOIN users u ON fp_prof.user_id = u.user_id
            LEFT JOIN product_images pi ON fp.produce_id = pi.produce_id
            WHERE fp.is_demo = TRUE
            ORDER BY fp.produce_id ASC, pi.is_primary DESC, pi.display_order ASC;
        """
        rows = fetch_all(query)

        # Group by product
        products_map = {}
        for r in rows:
            pid = r['produce_id']
            if pid not in products_map:
                products_map[pid] = {
                    'produce_id': pid,
                    'product_name': r['product_name'] or f"Fresh {r['crop_name']}",
                    'crop_name': r['crop_name'],
                    'variety_name': r['variety_name'] or 'Standard Variety',
                    'farm_name': r['farm_name'],
                    'farmer_name': r['farmer_name'],
                    'farmer_email': r['farmer_email'],
                    'primary_image': None,
                    'images': []
                }

            if r['image_id']:
                # Check local disk existence
                img_url = r['image_url'] or ''
                local_rel = img_url.lstrip('/')
                disk_path = frontend_dir / local_rel
                is_valid = disk_path.exists() and os.path.getsize(disk_path) > 0

                img_obj = {
                    'image_id': r['image_id'],
                    'image_url': r['image_url'],
                    'storage_path': r['storage_path'],
                    'is_primary': r['is_primary'],
                    'display_order': r['display_order'],
                    'source': r['source'] or 'Local Storage',
                    'source_url': r['source_url'],
                    'license': r['license'] or 'Licensed',
                    'attribution': r['attribution'],
                    'alt_text': r['alt_text'],
                    'status': 'Valid' if is_valid else 'Broken'
                }
                products_map[pid]['images'].append(img_obj)
                if r['is_primary'] or not products_map[pid]['primary_image']:
                    products_map[pid]['primary_image'] = img_obj

        # Build flat images list for simple grid rendering
        all_images = []
        for prod in products_map.values():
            for img in prod['images']:
                all_images.append({
                    **img,
                    'produce_id': prod['produce_id'],
                    'product_name': prod['product_name'],
                    'crop_name': prod['crop_name'],
                })

        return jsonify({
            'status': 'success',
            'count': len(products_map),
            'demo_products': list(products_map.values()),
            'images': all_images
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@admin_bp.route('/demo-images/<int:image_id>/set-primary', methods=['PUT', 'POST'])
@token_required
@roles_required('admin')
def set_admin_primary_image(image_id):
    """Set specified image as primary for its demo produce."""
    try:
        # Check image exists and belongs to demo product
        img = fetch_one("""
            SELECT pi.*, fp.is_demo
            FROM product_images pi
            JOIN farmer_produce fp ON pi.produce_id = fp.produce_id
            WHERE pi.image_id = %s;
        """, (image_id,))
        if not img:
            return jsonify({'error': 'Not Found', 'message': 'Image record not found.'}), 404
        if not img['is_demo']:
            return jsonify({'error': 'Forbidden', 'message': 'Safety restriction: Cannot modify non-demo product images via this endpoint.'}), 403

        pid = img['produce_id']
        with get_db_cursor(commit=True) as cur:
            cur.execute("UPDATE product_images SET is_primary = FALSE WHERE produce_id = %s;", (pid,))
            cur.execute("UPDATE product_images SET is_primary = TRUE WHERE image_id = %s RETURNING *;", (image_id,))
            updated = cur.fetchone()

        return jsonify({'status': 'success', 'message': 'Primary image updated.', 'image': dict(updated)}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@admin_bp.route('/demo-images/<int:image_id>', methods=['DELETE'])
@token_required
@roles_required('admin')
def delete_admin_demo_image(image_id):
    """Remove a demo product image from database."""
    try:
        img = fetch_one("""
            SELECT pi.*, fp.is_demo
            FROM product_images pi
            JOIN farmer_produce fp ON pi.produce_id = fp.produce_id
            WHERE pi.image_id = %s;
        """, (image_id,))
        if not img:
            return jsonify({'error': 'Not Found', 'message': 'Image not found.'}), 404
        if not img['is_demo']:
            return jsonify({'error': 'Forbidden', 'message': 'Safety restriction: Cannot delete non-demo product images.'}), 403

        pid = img['produce_id']
        with get_db_cursor(commit=True) as cur:
            cur.execute("DELETE FROM product_images WHERE image_id = %s;", (image_id,))
            if img['is_primary']:
                cur.execute("""
                    UPDATE product_images
                    SET is_primary = TRUE
                    WHERE image_id = (SELECT image_id FROM product_images WHERE produce_id = %s ORDER BY display_order ASC LIMIT 1);
                """, (pid,))

        return jsonify({'status': 'success', 'message': 'Demo image deleted.'}), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500

