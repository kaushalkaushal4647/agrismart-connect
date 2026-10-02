"""
Public Marketplace routes for AgriSmart Connect.
Provides search, filtering, and proximity distance calculation using the Haversine formula.
"""

import math
from flask import Blueprint, request, jsonify

try:
    from database import fetch_all, fetch_one
except ImportError:
    from backend.database import fetch_all, fetch_one

marketplace_bp = Blueprint('marketplace', __name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on the Earth in kilometers."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    r = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c, 2)


@marketplace_bp.route('', methods=['GET'])
def list_marketplace_produce():
    """
    Search and filter produce available across all registered farms.
    Supports filtering by crop, category, variety, price ceiling, district, organic status,
    quality grade, and geographic radius.
    Includes primary product images and enforces farmer privacy.
    """
    try:
        crop_id = request.args.get('crop_id', type=int)
        variety_id = request.args.get('variety_id', type=int)
        category = request.args.get('category', type=str)
        district = request.args.get('district', type=str)
        # Accept both 'organic' (from frontend filter) and 'organic_status'
        organic_status = request.args.get('organic', type=str) or request.args.get('organic_status', type=str)
        # Accept both 'grade' (from frontend filter) and 'quality_grade'
        quality_grade = request.args.get('grade', type=str) or request.args.get('quality_grade', type=str)
        max_price = request.args.get('max_price', type=float)
        min_qty = request.args.get('min_quantity', type=float)
        hub_id = request.args.get('hub_id', type=int)
        search = request.args.get('search', '').strip()
        user_lat = request.args.get('lat', type=float)
        user_lon = request.args.get('lon', type=float)
        max_distance_km = request.args.get('max_distance_km', type=float)
        sort_by = request.args.get('sort_by', 'date_asc')

        query = """
            SELECT fp.produce_id, fp.farmer_id, fp.crop_id, fp.variety_id,
                   fp.product_name, fp.category AS produce_category, fp.unit,
                   fp.min_order_quantity_kg, fp.organic_status, fp.description,
                   c.crop_name, c.category AS crop_category,
                   v.variety_name,
                   fp.available_quantity_kg, fp.minimum_price_per_kg,
                   fp.harvest_date, fp.quality_grade, fp.status,
                   fp.latitude AS produce_lat, fp.longitude AS produce_lon,
                   f_user.name AS farmer_name,
                   fp_prof.farm_name, fp_prof.village AS farm_village,
                   fp_prof.district AS farm_district,
                   h.hub_id, h.hub_name, h.district AS hub_district,
                   pi.image_url AS primary_image_url,
                   pi.source AS image_source,
                   pi.license AS image_license,
                   pi.attribution AS image_attribution,
                   pi.alt_text AS image_alt_text
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            JOIN farmer_profiles fp_prof ON fp.farmer_id = fp_prof.farmer_id
            JOIN users f_user ON fp_prof.user_id = f_user.user_id
            LEFT JOIN hubs h ON fp.preferred_hub_id = h.hub_id
            LEFT JOIN product_images pi ON fp.produce_id = pi.produce_id AND pi.is_primary = TRUE
            WHERE fp.status IN ('available', 'partially_reserved', 'ACTIVE')
              AND fp.available_quantity_kg > 0
        """
        params = []

        if crop_id:
            query += " AND fp.crop_id = %s"
            params.append(crop_id)

        if variety_id:
            query += " AND fp.variety_id = %s"
            params.append(variety_id)

        if category:
            query += " AND (LOWER(c.category) = LOWER(%s) OR LOWER(fp.category) = LOWER(%s))"
            params.extend([category, category])

        if district:
            query += " AND LOWER(fp_prof.district) = LOWER(%s)"
            params.append(district)

        if organic_status:
            query += " AND LOWER(fp.organic_status) = LOWER(%s)"
            params.append(organic_status)

        if quality_grade:
            query += " AND LOWER(fp.quality_grade) = LOWER(%s)"
            params.append(quality_grade)

        if max_price:
            query += " AND fp.minimum_price_per_kg <= %s"
            params.append(max_price)

        if min_qty:
            query += " AND fp.available_quantity_kg >= %s"
            params.append(min_qty)

        if hub_id:
            query += " AND fp.preferred_hub_id = %s"
            params.append(hub_id)

        if search:
            query += " AND (c.crop_name ILIKE %s OR v.variety_name ILIKE %s OR fp.product_name ILIKE %s OR fp_prof.district ILIKE %s)"
            term = f"%{search}%"
            params.extend([term, term, term, term])

        # Sorting
        if sort_by == 'price_asc':
            query += " ORDER BY fp.minimum_price_per_kg ASC"
        elif sort_by == 'price_desc':
            query += " ORDER BY fp.minimum_price_per_kg DESC"
        elif sort_by == 'qty_desc':
            query += " ORDER BY fp.available_quantity_kg DESC"
        else:
            query += " ORDER BY fp.harvest_date ASC, fp.created_at DESC"

        results = fetch_all(query, tuple(params) if params else None)

        # Fallback realistic photographs by crop
        crop_image_fallbacks = {
            'Tomato': '/uploads/products/demo/tomato/tomato_hybrid_harvest.jpg',
            'Potato': '/uploads/products/demo/potato/potato_kufri_jyoti.jpg',
            'Onion': '/uploads/products/demo/onion/onion_bellary_red.jpg',
            'Moringa': '/uploads/products/demo/moringa/moringa_pkm1_drumsticks.jpg',
            'Drumstick': '/uploads/products/demo/moringa/moringa_pkm1_drumsticks.jpg',
            'Banana': '/uploads/products/demo/banana/banana_grand_naine.jpg',
            'Coconut': '/uploads/products/demo/coconut/coconut_west_coast_tall.jpg',
            'Mango': '/uploads/products/demo/mango/mango_alphonso_ratnagiri.jpg',
            'Brinjal': '/uploads/products/demo/brinjal/brinjal_purple_round.jpg',
            'Carrot': '/uploads/products/demo/carrot/carrot_kuroda_nantes.jpg',
            'Green Chilli': '/uploads/products/demo/green_chilli/green_chilli_g4_spicy.jpg',
            'Chilli': '/uploads/products/demo/green_chilli/green_chilli_g4_spicy.jpg',
            'Rice': '/uploads/products/demo/rice/rice_bpt_samba_masuri.jpg',
            'Paddy': '/uploads/products/demo/rice/rice_bpt_samba_masuri.jpg',
            'Turmeric': '/uploads/products/demo/turmeric/turmeric_erode_gopichettipalayam.jpg',
            'Sugarcane': '/uploads/products/demo/sugarcane/sugarcane_co_86032.jpg',
            'Groundnut': '/uploads/products/demo/groundnut/groundnut_kadiri_6.jpg',
            'Cabbage': '/uploads/products/demo/cabbage/cabbage_golden_acre.jpg'
        }

        # Calculate distance and apply geographic distance filter if provided
        filtered_results = []
        for item in results:
            item_lat = float(item['produce_lat']) if item['produce_lat'] is not None else None
            item_lon = float(item['produce_lon']) if item['produce_lon'] is not None else None

            dist = None
            if user_lat is not None and user_lon is not None and item_lat is not None and item_lon is not None:
                dist = haversine_distance(user_lat, user_lon, item_lat, item_lon)

            item['distance_km'] = dist
            item['id'] = item.get('produce_id')
            item['price_per_kg'] = float(item.get('minimum_price_per_kg') or 0.0)
            item['available_kg'] = float(item.get('available_quantity_kg') or 0.0)

            # Assign primary image fallback if none in DB
            if not item.get('primary_image_url'):
                item['primary_image_url'] = crop_image_fallbacks.get(item.get('crop_name'), '/uploads/products/demo/tomato/tomato_hybrid_harvest.jpg')

            if max_distance_km is not None:
                if dist is not None and dist <= max_distance_km:
                    filtered_results.append(item)
            else:
                filtered_results.append(item)

        # If sorting by distance
        if sort_by == 'distance' and user_lat is not None:
            filtered_results.sort(key=lambda x: (x['distance_km'] is None, x['distance_km'] or 999999))

        return jsonify({
            'status': 'success',
            'count': len(filtered_results),
            'produce': filtered_results
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@marketplace_bp.route('/<int:produce_id>', methods=['GET'])
def get_marketplace_produce_item(produce_id):
    """
    Retrieve detailed specification and image gallery for a specific produce batch.
    Enforces privacy: never exposes farmer's private phone number.
    """
    try:
        item = fetch_one("""
            SELECT fp.produce_id, fp.farmer_id, fp.crop_id, fp.variety_id,
                   fp.product_name, fp.category AS produce_category, fp.unit,
                   fp.min_order_quantity_kg, fp.expected_quantity_kg, fp.available_quantity_kg,
                   fp.reserved_quantity_kg, fp.sold_quantity_kg, fp.minimum_price_per_kg,
                   fp.harvest_date, fp.expected_availability_date, fp.quality_grade,
                   fp.preferred_hub_id, fp.organic_status, fp.description, fp.status,
                   fp.latitude AS produce_lat, fp.longitude AS produce_lon,
                   c.crop_name, c.category AS crop_category, c.description AS crop_description,
                   v.variety_name, v.description AS variety_description,
                   fp_prof.farm_name, fp_prof.village AS farm_village,
                   fp_prof.taluk AS farm_taluk,
                   fp_prof.district AS farm_district, fp_prof.state AS farm_state,
                   f_user.name AS farmer_name,
                   h.hub_name, h.district AS hub_district, 
                   TO_CHAR(h.operating_start, 'HH24:MI:SS') AS operating_start, 
                   TO_CHAR(h.operating_end, 'HH24:MI:SS') AS operating_end
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            JOIN farmer_profiles fp_prof ON fp.farmer_id = fp_prof.farmer_id
            JOIN users f_user ON fp_prof.user_id = f_user.user_id
            LEFT JOIN hubs h ON fp.preferred_hub_id = h.hub_id
            WHERE fp.produce_id = %s;
        """, (produce_id,))

        if not item:
            return jsonify({'error': 'Not Found', 'message': 'Produce listing not found.'}), 404

        if hasattr(item.get('operating_start'), 'strftime'):
            item['operating_start'] = item['operating_start'].strftime('%H:%M:%S')
        elif item.get('operating_start') is not None:
            item['operating_start'] = str(item['operating_start'])
        if hasattr(item.get('operating_end'), 'strftime'):
            item['operating_end'] = item['operating_end'].strftime('%H:%M:%S')
        elif item.get('operating_end') is not None:
            item['operating_end'] = str(item['operating_end'])

        # Fetch image gallery
        images = fetch_all("""
            SELECT image_id, image_url, is_primary, display_order,
                   source, source_url, license, attribution, alt_text
            FROM product_images
            WHERE produce_id = %s
            ORDER BY display_order ASC, image_id ASC;
        """, (produce_id,))
        item['images'] = images

        # Aliases
        item['id'] = item['produce_id']
        item['price_per_kg'] = float(item.get('minimum_price_per_kg') or 0.0)
        item['available_kg'] = float(item.get('available_quantity_kg') or 0.0)

        return jsonify({'status': 'success', 'item': item}), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
