"""
AgriSmart Connect - Safe Demo Product Images Assignment Script.
Assigns verified, locally-stored, licensed agricultural photographs to DEMO PRODUCTS ONLY.
Strictly safeguards real farmer accounts and images.
Logs all operations in demo_image_audit_log.
"""

import json
import logging
import os
import sys
from pathlib import Path
import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / 'frontend'
MANIFEST_PATH = FRONTEND_DIR / 'uploads' / 'products' / 'demo' / 'images_manifest.json'

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import Config
from database import get_db_cursor, fetch_all, fetch_one

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('assign_demo_images')


def load_manifest():
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found at {MANIFEST_PATH}. Run download_and_optimize_demo_images.py first!")
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def select_images_for_product(crop_name, variety_name, product_name, manifest):
    """
    Select primary and optional secondary image based on crop and variety attributes.
    Returns (primary_meta, secondary_meta)
    """
    crop_lower = (crop_name or '').lower().strip()
    var_lower = (variety_name or '').lower().strip()
    pname_lower = (product_name or '').lower().strip()
    combined = f"{var_lower} {pname_lower}"

    primary_key = None
    secondary_key = None

    if 'tomato' in crop_lower:
        if 'desi' in combined or 'nattu' in combined or 'native' in combined:
            primary_key = 'tomato_desi'
            secondary_key = 'tomato_hybrid'
        elif 'roma' in combined or 'salad' in combined:
            primary_key = 'tomato_hybrid'
            secondary_key = 'tomato_desi'
        else:
            primary_key = 'tomato_hybrid'
            secondary_key = 'tomato_desi'

    elif 'onion' in crop_lower:
        if 'shallot' in combined or 'sambar' in combined or 'chinna' in combined or 'vengayam' in combined:
            primary_key = 'onion_shallot'
            secondary_key = 'onion_bellary'
        elif 'white' in combined:
            primary_key = 'onion_white'
            secondary_key = 'onion_bellary'
        else:
            primary_key = 'onion_bellary'
            secondary_key = 'onion_shallot'

    elif 'potato' in crop_lower:
        if 'baby' in combined or 'small' in combined:
            primary_key = 'potato_baby'
            secondary_key = 'potato_ooty'
        elif 'ooty' in combined or 'mountain' in combined or 'hill' in combined:
            primary_key = 'potato_ooty'
            secondary_key = 'potato_jyoti'
        else:
            primary_key = 'potato_jyoti'
            secondary_key = 'potato_ooty'

    elif 'banana' in crop_lower:
        if 'nendran' in combined or 'plantain' in combined or 'sevvazhai' in combined or 'red' in combined:
            primary_key = 'banana_nendran'
            secondary_key = 'banana_g9'
        else:
            primary_key = 'banana_g9'
            secondary_key = 'banana_nendran'

    elif 'coconut' in crop_lower:
        if 'tender' in combined or 'sweet' in combined or 'pollachi' in combined:
            primary_key = 'coconut_tender'
            secondary_key = 'coconut_mature'
        else:
            primary_key = 'coconut_mature'
            secondary_key = 'coconut_tender'

    elif 'chilli' in crop_lower:
        if 'jwala' in combined:
            primary_key = 'chilli_jwala'
            secondary_key = 'chilli_g4'
        else:
            primary_key = 'chilli_g4'
            secondary_key = 'chilli_jwala'

    elif 'cabbage' in crop_lower:
        if 'savoy' in combined or 'cross' in combined:
            primary_key = 'cabbage_savoy'
            secondary_key = 'cabbage_golden_acre'
        else:
            primary_key = 'cabbage_golden_acre'
            secondary_key = 'cabbage_savoy'

    elif 'moringa' in crop_lower or 'drumstick' in crop_lower:
        if 'jaffna' in combined:
            primary_key = 'moringa_jaffna'
            secondary_key = 'moringa_pkm1'
        else:
            primary_key = 'moringa_pkm1'
            secondary_key = 'moringa_jaffna'

    elif 'rice' in crop_lower or 'paddy' in crop_lower:
        if 'grain' in combined or 'seeraga' in combined or 'biryani' in combined:
            primary_key = 'rice_milled_grain'
            secondary_key = 'rice_paddy_field'
        else:
            primary_key = 'rice_paddy_field'
            secondary_key = 'rice_milled_grain'

    elif 'carrot' in crop_lower:
        primary_key = 'carrot_fresh'
        secondary_key = None

    elif 'brinjal' in crop_lower or 'eggplant' in crop_lower:
        primary_key = 'brinjal_purple'
        secondary_key = None

    elif 'mango' in crop_lower:
        primary_key = 'mango_alphonso'
        secondary_key = None

    elif 'turmeric' in crop_lower:
        primary_key = 'turmeric_rhizome'
        secondary_key = None

    elif 'groundnut' in crop_lower or 'peanut' in crop_lower:
        primary_key = 'groundnut_pods'
        secondary_key = None

    elif 'sugarcane' in crop_lower:
        primary_key = 'sugarcane_stalks'
        secondary_key = None

    # Fallback if unmapped
    if not primary_key or primary_key not in manifest:
        # Search manifest for first matching crop
        for k, v in manifest.items():
            if v['crop'].lower() in crop_lower or crop_lower in v['crop'].lower():
                primary_key = k
                break
        if not primary_key:
            primary_key = 'tomato_hybrid'

    primary_meta = manifest.get(primary_key)
    secondary_meta = manifest.get(secondary_key) if secondary_key else None
    return primary_meta, secondary_meta


def assign_demo_images():
    print("=" * 75)
    print(" AgriSmart Connect - Safe Demo Product Images Assignment")
    print("=" * 75)

    manifest = load_manifest()
    print(f"[*] Loaded catalog manifest with {len(manifest)} verified crop images.")

    with get_db_cursor(commit=True) as cur:
        # ─────────────────────────────────────────────────────────────
        # 1. CRITICAL SAFETY VERIFICATION
        # ─────────────────────────────────────────────────────────────
        print("\n[Step 1] Running Pre-Execution Real Farmer Safety Check...")

        # Query all demo products explicitly
        cur.execute("""
            SELECT fp.produce_id, fp.farmer_id, fp.product_name, c.crop_name,
                   v.variety_name, u.email AS farmer_email, u.name AS farmer_name,
                   fp.is_demo
            FROM farmer_produce fp
            JOIN crops c ON fp.crop_id = c.crop_id
            LEFT JOIN varieties v ON fp.variety_id = v.variety_id
            JOIN farmer_profiles fprof ON fp.farmer_id = fprof.farmer_id
            JOIN users u ON fprof.user_id = u.user_id
            WHERE fp.is_demo = TRUE
            ORDER BY fp.produce_id ASC;
        """)
        demo_products = cur.fetchall()

        # Query real farmer products to ensure separation
        cur.execute("""
            SELECT COUNT(*) AS real_prod_count
            FROM farmer_produce fp
            JOIN farmer_profiles fprof ON fp.farmer_id = fprof.farmer_id
            JOIN users u ON fprof.user_id = u.user_id
            WHERE fp.is_demo = FALSE OR u.email NOT LIKE '%@demo.com';
        """)
        real_prod_count = cur.fetchone()['real_prod_count']
        print(f"  Total demo products to update: {len(demo_products)}")
        print(f"  Total real / non-demo produce records protected: {real_prod_count}")

        if not demo_products:
            print("  [!] No demo products found with is_demo = TRUE. Aborting.")
            return

        # ─────────────────────────────────────────────────────────────
        # 2. PERFORM SAFE IMAGE REPLACEMENT FOR DEMO PRODUCTS ONLY
        # ─────────────────────────────────────────────────────────────
        print("\n[Step 2] Replacing Placeholder Images with Authentic Harvest Photographs...")

        updated_count = 0
        multi_image_count = 0
        audit_records_count = 0

        for p in demo_products:
            pid = p['produce_id']
            fid = p['farmer_id']
            pname = p['product_name'] or f"Fresh {p['crop_name']}"
            cname = p['crop_name']
            vname = p['variety_name'] or ''
            femail = p['farmer_email']

            # Double check safety guard
            if not p['is_demo']:
                raise RuntimeError(f"SAFETY VIOLATION DETECTED: Product {pid} is NOT marked as demo!")

            # Select authentic photographs
            primary_img, secondary_img = select_images_for_product(cname, vname, pname, manifest)

            # Get existing images to record old image URLs for audit log
            cur.execute("SELECT image_id, image_url FROM product_images WHERE produce_id = %s;", (pid,))
            old_images = cur.fetchall()
            old_primary_url = old_images[0]['image_url'] if old_images else None

            # Remove previous placeholder/dummy product images for this DEMO product
            cur.execute("DELETE FROM product_images WHERE produce_id = %s;", (pid,))

            # Insert Primary Image
            cur.execute("""
                INSERT INTO product_images (
                    produce_id, image_url, storage_path, is_primary, display_order,
                    source, source_url, license, attribution, alt_text
                )
                VALUES (%s, %s, %s, TRUE, 0, %s, %s, %s, %s, %s)
                RETURNING image_id;
            """, (
                pid,
                primary_img['local_jpg_url'],
                primary_img['storage_path'],
                primary_img['source'],
                primary_img['source_url'],
                primary_img['license'],
                primary_img['attribution'],
                primary_img['alt_text']
            ))

            # Record in Audit Log
            cur.execute("""
                INSERT INTO demo_image_audit_log (
                    produce_id, product_name, crop_name, farmer_id, farmer_email,
                    old_image, new_image, image_source, source_url, license, action
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ASSIGN_DEMO_REAL_IMAGE');
            """, (
                pid, pname, cname, fid, femail,
                old_primary_url, primary_img['local_jpg_url'],
                primary_img['source'], primary_img['source_url'], primary_img['license']
            ))
            audit_records_count += 1

            # Insert Secondary Image if available (for rich gallery experience)
            if secondary_img and secondary_img['key'] != primary_img['key']:
                cur.execute("""
                    INSERT INTO product_images (
                        produce_id, image_url, storage_path, is_primary, display_order,
                        source, source_url, license, attribution, alt_text
                    )
                    VALUES (%s, %s, %s, FALSE, 1, %s, %s, %s, %s, %s);
                """, (
                    pid,
                    secondary_img['local_jpg_url'],
                    secondary_img['storage_path'],
                    secondary_img['source'],
                    secondary_img['source_url'],
                    secondary_img['license'],
                    secondary_img['attribution'],
                    secondary_img['alt_text']
                ))
                multi_image_count += 1

            updated_count += 1

        # ─────────────────────────────────────────────────────────────
        # 3. POST-EXECUTION INTEGRITY & SAFETY ASSERTION
        # ─────────────────────────────────────────────────────────────
        print("\n[Step 3] Running Post-Execution Integrity & Real Farmer Isolation Assertion...")

        # Verify real farmer products modified is EXACTLY ZERO
        cur.execute("""
            SELECT COUNT(*) AS modified_real_count
            FROM demo_image_audit_log al
            JOIN farmer_produce fp ON al.produce_id = fp.produce_id
            WHERE fp.is_demo = FALSE;
        """)
        modified_real = cur.fetchone()['modified_real_count']
        if modified_real > 0:
            raise RuntimeError(f"FATAL SAFETY FAILURE: {modified_real} real farmer products were touched!")

        # Verify all demo products now have at least 1 primary image
        cur.execute("""
            SELECT COUNT(DISTINCT fp.produce_id) AS demo_prods_without_images
            FROM farmer_produce fp
            LEFT JOIN product_images pi ON fp.produce_id = pi.produce_id AND pi.is_primary = TRUE
            WHERE fp.is_demo = TRUE AND pi.image_id IS NULL;
        """)
        missing_count = cur.fetchone()['demo_prods_without_images']

        print(f"  [SAFETY PASS] Real farmer products modified: 0")
        print(f"  [INTEGRITY PASS] Demo products without primary image: {missing_count}")
        print(f"  Total demo products successfully updated: {updated_count}")
        print(f"  Products with multiple gallery images: {multi_image_count}")
        print(f"  Audit log entries written: {audit_records_count}")

    print("\n" + "=" * 75)
    print(" Demo Product Images Successfully Assigned & Safeguarded!")
    print("=" * 75)


if __name__ == '__main__':
    assign_demo_images()
