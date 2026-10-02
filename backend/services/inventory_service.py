"""
AgriSmart Connect - Inventory Safety & Reservation Service.
Executes atomic inventory state transitions with row-level locks (SELECT FOR UPDATE)
to prevent double selling and maintain exact accounting between available, reserved, and sold quantities.
"""

from typing import Dict, Any


def reserve_produce(cur, produce_id: int, quantity_kg: float) -> Dict[str, Any]:
    """
    Lock produce record and reserve requested quantity.
    Must be called inside an active database transaction cursor.
    """
    cur.execute("""
        SELECT produce_id, available_quantity_kg, reserved_quantity_kg, sold_quantity_kg, status
        FROM farmer_produce
        WHERE produce_id = %s
        FOR UPDATE;
    """, (produce_id,))
    produce = cur.fetchone()

    if not produce:
        raise ValueError(f"Produce batch #{produce_id} not found.")

    available = float(produce['available_quantity_kg'])
    if available < quantity_kg:
        raise ValueError(
            f"Insufficient available quantity for produce #{produce_id}. Requested: {quantity_kg} kg, Available: {available} kg."
        )

    new_available = round(available - quantity_kg, 2)
    new_reserved = round(float(produce['reserved_quantity_kg']) + quantity_kg, 2)
    new_status = 'reserved' if new_available <= 0 else 'partially_reserved'

    cur.execute("""
        UPDATE farmer_produce
        SET available_quantity_kg = %s,
            reserved_quantity_kg = %s,
            status = %s
        WHERE produce_id = %s
        RETURNING produce_id, available_quantity_kg, reserved_quantity_kg, status;
    """, (new_available, new_reserved, new_status, produce_id))

    return dict(cur.fetchone())


def release_reservation(cur, produce_id: int, quantity_kg: float) -> Dict[str, Any]:
    """
    Release previously reserved quantity back to available (e.g. on order cancellation).
    Must be called inside an active database transaction cursor.
    """
    cur.execute("""
        SELECT produce_id, available_quantity_kg, reserved_quantity_kg, status
        FROM farmer_produce
        WHERE produce_id = %s
        FOR UPDATE;
    """, (produce_id,))
    produce = cur.fetchone()

    if not produce:
        raise ValueError(f"Produce batch #{produce_id} not found.")

    reserved = float(produce['reserved_quantity_kg'])
    release_qty = min(reserved, quantity_kg)

    new_reserved = round(reserved - release_qty, 2)
    new_available = round(float(produce['available_quantity_kg']) + release_qty, 2)
    new_status = 'available' if new_reserved <= 0 else 'partially_reserved'

    cur.execute("""
        UPDATE farmer_produce
        SET available_quantity_kg = %s,
            reserved_quantity_kg = %s,
            status = %s
        WHERE produce_id = %s
        RETURNING produce_id, available_quantity_kg, reserved_quantity_kg, status;
    """, (new_available, new_reserved, new_status, produce_id))

    return dict(cur.fetchone())


def complete_sale(cur, produce_id: int, quantity_kg: float) -> Dict[str, Any]:
    """
    Transition reserved quantity to fulfilled sold quantity (on order delivery).
    Must be called inside an active database transaction cursor.
    """
    cur.execute("""
        SELECT produce_id, available_quantity_kg, reserved_quantity_kg, sold_quantity_kg, status
        FROM farmer_produce
        WHERE produce_id = %s
        FOR UPDATE;
    """, (produce_id,))
    produce = cur.fetchone()

    if not produce:
        raise ValueError(f"Produce batch #{produce_id} not found.")

    reserved = float(produce['reserved_quantity_kg'])
    sold_qty = min(reserved, quantity_kg)

    new_reserved = round(reserved - sold_qty, 2)
    new_sold = round(float(produce['sold_quantity_kg']) + sold_qty, 2)
    available = float(produce['available_quantity_kg'])

    if available <= 0 and new_reserved <= 0:
        new_status = 'sold'
    elif available > 0:
        new_status = 'available'
    else:
        new_status = 'partially_reserved'

    cur.execute("""
        UPDATE farmer_produce
        SET reserved_quantity_kg = %s,
            sold_quantity_kg = %s,
            status = %s
        WHERE produce_id = %s
        RETURNING produce_id, sold_quantity_kg, status;
    """, (new_reserved, new_sold, new_status, produce_id))

    return dict(cur.fetchone())
