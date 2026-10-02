"""
AgriSmart Connect - Dynamic Supply-Demand Matching Engine.
Evaluates available farmer produce batches against buyer requirements using
multi-factor configurable weighted scoring and optimal multi-farmer quantity splitting.

Initial Scoring Weights:
- Crop match:        30%
- Variety match:     20%
- Harvest date sync: 20%
- Proximity/Distance:15%
- Price suitability: 15%
"""

import math
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional

try:
    from database import fetch_all, fetch_one
except ImportError:
    from backend.database import fetch_all, fetch_one


DEFAULT_WEIGHTS = {
    'crop': 0.30,
    'variety': 0.20,
    'date': 0.20,
    'distance': 0.15,
    'price': 0.15
}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometers between two GPS coordinates."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 999.0
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c, 2)


class MatchingEngine:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS

    def find_matches(
        self,
        crop_id: int,
        required_quantity_kg: float,
        required_date: date,
        variety_id: Optional[int] = None,
        max_price_per_kg: Optional[float] = None,
        buyer_lat: Optional[float] = None,
        buyer_lon: Optional[float] = None,
        hub_id: Optional[int] = None,
        max_distance_km: float = 150.0
    ) -> Dict[str, Any]:
        """
        Find and rank matching farmer supply batches, generating an optimal fulfillment plan.
        """
        if isinstance(required_date, str):
            required_date = datetime.strptime(required_date, '%Y-%m-%d').date()

        # 1. Fetch eligible available produce
        query = """
            SELECT fp.produce_id, fp.farmer_id, fp.crop_id, fp.variety_id,
                   c.crop_name, v.variety_name,
                   fp.available_quantity_kg, fp.minimum_price_per_kg,
                   fp.harvest_date, fp.quality_grade,
                   fp.latitude AS produce_lat, fp.longitude AS produce_lon,
                   fp.preferred_hub_id,
                   fp_prof.farm_name, fp_prof.village, fp_prof.district,
                   u.name AS farmer_name, u.phone AS farmer_phone,
                   h.hub_name, h.latitude AS hub_lat, h.longitude AS hub_lon
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            JOIN farmer_profiles fp_prof ON fp.farmer_id = fp_prof.farmer_id
            JOIN users u ON fp_prof.user_id = u.user_id
            LEFT JOIN hubs h ON fp.preferred_hub_id = h.hub_id
            WHERE fp.crop_id = %s
              AND fp.status IN ('available', 'partially_reserved')
              AND fp.available_quantity_kg > 0
        """
        params = [crop_id]

        if max_price_per_kg:
            query += " AND fp.minimum_price_per_kg <= %s"
            params.append(max_price_per_kg)

        candidates = fetch_all(query, tuple(params))

        if not candidates:
            return {
                'match_found': False,
                'required_quantity_kg': required_quantity_kg,
                'allocated_quantity_kg': 0.0,
                'shortfall_quantity_kg': required_quantity_kg,
                'allocated_farmers': [],
                'ranked_candidates': []
            }

        # 2. Score each candidate
        scored_candidates = []
        for c in candidates:
            item_hdate = c['harvest_date']
            if isinstance(item_hdate, str):
                item_hdate = datetime.strptime(item_hdate, '%Y-%m-%d').date()

            # Distance calculation (prefer buyer coords, fallback to hub coords)
            target_lat = buyer_lat if buyer_lat is not None else (c.get('hub_lat') or 18.5204)
            target_lon = buyer_lon if buyer_lon is not None else (c.get('hub_lon') or 73.8567)
            item_lat = float(c['produce_lat']) if c['produce_lat'] is not None else target_lat
            item_lon = float(c['produce_lon']) if c['produce_lon'] is not None else target_lon

            dist = haversine(target_lat, target_lon, item_lat, item_lon)

            # Crop Match Score (1.0 since filtered by crop)
            crop_score = 1.0

            # Variety Match Score (1.0 if identical or if buyer didn't specify, 0.4 if different)
            if not variety_id or c['variety_id'] == variety_id:
                variety_score = 1.0
            else:
                variety_score = 0.4

            # Harvest Date Score (Exponential decay based on day difference)
            # Optimal if harvest is 0 to 2 days before required_date
            days_diff = (required_date - item_hdate).days
            if 0 <= days_diff <= 2:
                date_score = 1.0
            elif -2 <= days_diff < 0:
                # Harvest slightly after required date
                date_score = 0.65
            elif 2 < days_diff <= 5:
                # Harvested up to 5 days prior (good for root vegetables / sturdy produce)
                date_score = 0.80
            else:
                date_score = max(0.1, 1.0 - (abs(days_diff) * 0.15))

            # Distance Score (1.0 if < 15km, decays linearly to 0 at max_distance_km)
            if dist <= 15.0:
                dist_score = 1.0
            elif dist > max_distance_km:
                dist_score = 0.1
            else:
                dist_score = max(0.1, 1.0 - ((dist - 15.0) / (max_distance_km - 15.0)))

            # Price Score (Cheaper farmer price gives higher score)
            item_price = float(c['minimum_price_per_kg'])
            ref_price = max_price_per_kg if max_price_per_kg else (item_price * 1.2)
            if item_price <= ref_price:
                price_score = min(1.0, 0.7 + (0.3 * ((ref_price - item_price) / (ref_price or 1))))
            else:
                price_score = max(0.2, 1.0 - ((item_price - ref_price) / ref_price))

            # Total Weighted Composite Score
            total_score = (
                (crop_score * self.weights['crop']) +
                (variety_score * self.weights['variety']) +
                (date_score * self.weights['date']) +
                (dist_score * self.weights['distance']) +
                (price_score * self.weights['price'])
            )

            c_dict = dict(c)
            c_dict['distance_km'] = dist
            c_dict['scores'] = {
                'total': round(total_score * 100, 1),
                'crop': round(crop_score * 100, 1),
                'variety': round(variety_score * 100, 1),
                'date': round(date_score * 100, 1),
                'distance': round(dist_score * 100, 1),
                'price': round(price_score * 100, 1)
            }
            scored_candidates.append(c_dict)

        # 3. Sort candidates by total composite match score descending
        scored_candidates.sort(key=lambda x: x['scores']['total'], reverse=True)

        # 4. Multi-farmer allocation algorithm to fulfill required_quantity_kg
        remaining_needed = float(required_quantity_kg)
        allocated_batches = []

        for candidate in scored_candidates:
            if remaining_needed <= 0:
                break

            avail = float(candidate['available_quantity_kg'])
            allocated_qty = min(avail, remaining_needed)

            if allocated_qty > 0:
                allocated_batches.append({
                    'produce_id': candidate['produce_id'],
                    'farmer_id': candidate['farmer_id'],
                    'farmer_name': candidate['farmer_name'],
                    'farm_name': candidate['farm_name'],
                    'crop_id': candidate['crop_id'],
                    'crop_name': candidate['crop_name'],
                    'variety_id': candidate['variety_id'],
                    'variety_name': candidate['variety_name'],
                    'allocated_quantity_kg': allocated_qty,
                    'price_per_kg': float(candidate['minimum_price_per_kg']),
                    'line_total': round(allocated_qty * float(candidate['minimum_price_per_kg']), 2),
                    'harvest_date': str(candidate['harvest_date']),
                    'quality_grade': candidate['quality_grade'],
                    'preferred_hub_id': candidate['preferred_hub_id'],
                    'hub_name': candidate['hub_name'],
                    'distance_km': candidate['distance_km'],
                    'match_score': candidate['scores']['total']
                })
                remaining_needed -= allocated_qty

        total_allocated = sum(b['allocated_quantity_kg'] for b in allocated_batches)
        subtotal = sum(b['line_total'] for b in allocated_batches)

        # Platform economics: 5% platform fee, delivery fee estimation (₹50 base + ₹2/km avg)
        avg_distance = (
            sum(b['distance_km'] for b in allocated_batches) / len(allocated_batches)
            if allocated_batches else 10.0
        )
        delivery_fee = round(50.0 + (avg_distance * 2.0), 2)
        platform_fee = round(subtotal * 0.05, 2)
        total_amount = round(subtotal + delivery_fee + platform_fee, 2)

        return {
            'match_found': len(allocated_batches) > 0,
            'required_quantity_kg': required_quantity_kg,
            'allocated_quantity_kg': total_allocated,
            'shortfall_quantity_kg': max(0.0, required_quantity_kg - total_allocated),
            'subtotal': subtotal,
            'estimated_delivery_fee': delivery_fee,
            'platform_fee': platform_fee,
            'total_amount': total_amount,
            'allocated_batches': allocated_batches,
            'ranked_candidates': scored_candidates[:10]
        }
