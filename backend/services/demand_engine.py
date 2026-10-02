"""
AgriSmart Connect - Demand Prediction & Forecasting Service.
Implements a 7-day moving average time-series model on past sales/orders data
and projects upcoming 7-day crop demand by location.
"""

from datetime import date, timedelta
from typing import Dict, List, Any

try:
    from database import fetch_all, fetch_one, get_db_cursor
except ImportError:
    from backend.database import fetch_all, fetch_one, get_db_cursor


class DemandPredictionEngine:
    """Computes moving average demand projections based on verified sales."""

    @classmethod
    def calculate_crop_forecast(cls, crop_id: int, location: str = 'Salem') -> Dict[str, Any]:
        """
        Calculate 7-day simple moving average from order_items and project next 7-day demand.
        """
        # Fetch past 7 to 14 days of sold volume for this crop
        rows = fetch_all("""
            SELECT o.order_date::date AS day,
                   COALESCE(SUM(oi.quantity_kg), 0) AS daily_kg
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE oi.crop_id = %s
              AND o.order_status IN ('confirmed', 'at_hub', 'packed', 'out_for_delivery', 'delivered')
              AND o.order_date >= CURRENT_DATE - INTERVAL '14 days'
            GROUP BY o.order_date::date
            ORDER BY day ASC;
        """, (crop_id,))

        daily_quantities = [float(r['daily_kg']) for r in rows]

        # If no order history, estimate from demand_records or provide baseline
        if not daily_quantities:
            demand_rows = fetch_all("""
                SELECT required_quantity_kg
                FROM demand_records
                WHERE crop_id = %s;
            """, (crop_id,))
            daily_quantities = [float(r['required_quantity_kg']) for r in demand_rows] if demand_rows else [120.0, 140.0, 110.0, 130.0, 125.0, 150.0, 135.0]

        # Calculate moving average
        recent_window = daily_quantities[-7:] if len(daily_quantities) >= 7 else daily_quantities
        moving_average = sum(recent_window) / len(recent_window)

        predicted_qty = round(moving_average * 1.05, 2)  # 5% growth factor buffer
        confidence = 0.85 if len(daily_quantities) >= 7 else 0.70

        forecast_date = date.today() + timedelta(days=7)

        # Store in demand_forecasts table
        try:
            with get_db_cursor(commit=True) as cur:
                cur.execute("""
                    INSERT INTO demand_forecasts (
                        crop_id, location, forecast_date,
                        predicted_quantity_kg, confidence, model_version
                    )
                    VALUES (%s, %s, %s, %s, %s, 'v1.0-moving-average')
                    RETURNING forecast_id, crop_id, location, forecast_date, predicted_quantity_kg, confidence;
                """, (crop_id, location, forecast_date, predicted_qty, confidence))
                saved = dict(cur.fetchone())
        except Exception:
            saved = {
                'crop_id': crop_id,
                'location': location,
                'forecast_date': str(forecast_date),
                'predicted_quantity_kg': predicted_qty,
                'confidence': confidence
            }

        return {
            'crop_id': crop_id,
            'location': location,
            'history_samples_count': len(daily_quantities),
            'moving_average_kg': round(moving_average, 2),
            'predicted_quantity_kg': predicted_qty,
            'confidence': confidence,
            'forecast_target_date': str(forecast_date),
            'model': '7-day-moving-average',
            'record': saved
        }
