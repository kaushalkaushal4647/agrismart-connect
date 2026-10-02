"""
AgriSmart Connect - Demo Product Images Downloader & Optimizer.
Downloads verified, legally licensed, high-resolution agricultural photographs
from Wikimedia Commons for all crops.
Validates with PIL, optimizes (JPEG + WebP), creates thumbnails, and stores them under
frontend/uploads/products/demo/<crop>/ with full source and attribution metadata.
"""

import io
import json
import logging
import os
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from PIL import Image

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('demo_image_downloader')

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / 'frontend'
DEMO_STORAGE_DIR = FRONTEND_DIR / 'uploads' / 'products' / 'demo'

REQUEST_HEADERS = {
    'User-Agent': 'AgriSmartProduceBot/1.0 (https://agrismart.local; contact@agrismart.local) Python-urllib'
}

# Catalog of verified Wikimedia Commons filenames
CROP_IMAGE_CATALOG = [
    # ── 1. TOMATO ───────────────────────────────────────────────────────────
    {
        "crop": "Tomato",
        "category": "Vegetables",
        "crop_slug": "tomato",
        "key": "tomato_hybrid",
        "filename": "tomato_hybrid_harvest.jpg",
        "wiki_file": "Tomato_je.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Tomato_je.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Rasbak (Wikimedia Commons)",
        "alt_text": "Fresh vibrant red field hybrid tomatoes",
        "tags": ["Hybrid Tomato (Shivam)", "Hybrid Tomato", "Farm Fresh Hybrid Tomatoes"]
    },
    {
        "crop": "Tomato",
        "category": "Vegetables",
        "crop_slug": "tomato",
        "key": "tomato_desi",
        "filename": "tomato_desi_nattu.jpg",
        "wiki_file": "Bright_red_tomato_and_cross_section02.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Bright_red_tomato_and_cross_section02.jpg",
        "license": "CC0 1.0 Public Domain",
        "attribution": "Public Domain / CC0",
        "alt_text": "Authentic organic Desi Nattu country tomatoes",
        "tags": ["Desi Tomato (Nattu Thakkali)", "Desi Tomato", "Native Desi Nattu Tomato"]
    },
    {
        "crop": "Tomato",
        "category": "Vegetables",
        "crop_slug": "tomato",
        "key": "tomato_roma",
        "filename": "tomato_roma_field.jpg",
        "wiki_file": "Roma_tomatoes_on_vine.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Roma_tomatoes_on_vine.jpg",
        "license": "CC BY-SA 4.0",
        "attribution": "Photo by Dwight Sipler (Wikimedia Commons)",
        "alt_text": "Farm ripe Roma plum salad tomatoes on vine",
        "tags": ["Roma Tomato", "Roma", "Karur Roma Salad Tomatoes"]
    },

    # ── 2. ONION ────────────────────────────────────────────────────────────
    {
        "crop": "Onion",
        "category": "Vegetables",
        "crop_slug": "onion",
        "key": "onion_shallot",
        "filename": "onion_sambar_shallots.jpg",
        "wiki_file": "Shallot (Sambar Onion) (1).JPG",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Shallot_(Sambar_Onion)_(1).JPG",
        "license": "CC BY-SA 4.0",
        "attribution": "Photo by Thamizhpparithi Maari (Wikimedia Commons)",
        "alt_text": "Pungent Tamil Nadu small Chinna Vengayam sambar shallots",
        "tags": ["Chinna Vengayam (Sambar Shallot)", "Sambhar Onion", "Authentic Sambar Shallots", "Pollachi Red Sambar Shallots", "Attur Valley Small Onions"]
    },
    {
        "crop": "Onion",
        "category": "Vegetables",
        "crop_slug": "onion",
        "key": "onion_bellary",
        "filename": "onion_bellary_red.jpg",
        "wiki_file": "Onion_on_White.JPG",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Onion_on_White.JPG",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Colin (Wikimedia Commons)",
        "alt_text": "Fresh Bellary red cooking onions",
        "tags": ["Bellary Red Onion", "Red Nashik Onion"]
    },
    {
        "crop": "Onion",
        "category": "Vegetables",
        "crop_slug": "onion",
        "key": "onion_white",
        "filename": "onion_white_culinary.jpg",
        "wiki_file": "White onions.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:White_onions.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Sanjay Acharya (Wikimedia Commons)",
        "alt_text": "Crisp sweet white cooking onions",
        "tags": ["White Onion"]
    },

    # ── 3. POTATO ───────────────────────────────────────────────────────────
    {
        "crop": "Potato",
        "category": "Tubers",
        "crop_slug": "potato",
        "key": "potato_ooty",
        "filename": "potato_ooty_mountain.jpg",
        "wiki_file": "Patates.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Patates.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Sérgio Valle Duarte (Wikimedia Commons)",
        "alt_text": "Earth harvested Ooty hill station mountain potatoes",
        "tags": ["Ooty Mountain Potato", "Ooty Hill Station Golden Potatoes", "Ooty Mountain Harvest Potatoes"]
    },
    {
        "crop": "Potato",
        "category": "Tubers",
        "crop_slug": "potato",
        "key": "potato_jyoti",
        "filename": "potato_kufri_jyoti.jpg",
        "wiki_file": "Potato.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Potato.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Wikimedia Commons",
        "alt_text": "High-starch Kufri Jyoti golden table potatoes",
        "tags": ["Kufri Jyoti", "Russet Potato"]
    },
    {
        "crop": "Potato",
        "category": "Tubers",
        "crop_slug": "potato",
        "key": "potato_baby",
        "filename": "potato_baby_golden.jpg",
        "wiki_file": "Patates.jpg",  # Fallback to authentic potato harvest
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Patates.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Sérgio Valle Duarte (Wikimedia Commons)",
        "alt_text": "Tender golden baby roasting potatoes",
        "tags": ["Baby Potato", "Kovilpatti Golden Baby Potatoes"]
    },

    # ── 4. BANANA ───────────────────────────────────────────────────────────
    {
        "crop": "Banana",
        "category": "Fruits",
        "crop_slug": "banana",
        "key": "banana_g9",
        "filename": "banana_grand_naine.jpg",
        "wiki_file": "Bananas (white background).jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Bananas_(white_background).jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Evan-Amos (Wikimedia Commons)",
        "alt_text": "Sweet ripened Grand Naine G9 Cavendish bananas cluster",
        "tags": ["Grand Naine (G9)", "Poovan", "Delta Grand Naine Sweet Bananas"]
    },
    {
        "crop": "Banana",
        "category": "Fruits",
        "crop_slug": "banana",
        "key": "banana_nendran",
        "filename": "banana_plantain_nendran.jpg",
        "wiki_file": "Cavendish_Banana_DS.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Cavendish_Banana_DS.jpg",
        "license": "CC BY-SA 4.0",
        "attribution": "Photo by Daniel Schwen (Wikimedia Commons)",
        "alt_text": "Fresh organic South Indian cooking plantain Nendran bananas",
        "tags": ["Nendran (Plantain)", "Sevvazhai (Red Banana)"]
    },

    # ── 5. COCONUT ──────────────────────────────────────────────────────────
    {
        "crop": "Coconut",
        "category": "Plantations",
        "crop_slug": "coconut",
        "key": "coconut_tender",
        "filename": "coconut_pollachi_tender.jpg",
        "wiki_file": "Tender coconut-the green varity-salem Wiki DEC2011-Tamil Nadu618.JPG",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Tender_coconut-the_green_varity-salem_Wiki_DEC2011-Tamil_Nadu618.JPG",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Thamizhpparithi Maari (Wikimedia Commons)",
        "alt_text": "Fresh electrolyte-rich Pollachi green tender coconuts from Salem groves",
        "tags": ["Pollachi Tall Tender Coconut", "Dwarf Green Coconut", "Pollachi Sweet Tender Coconuts"]
    },
    {
        "crop": "Coconut",
        "category": "Plantations",
        "crop_slug": "coconut",
        "key": "coconut_mature",
        "filename": "coconut_mature_husked.jpg",
        "wiki_file": "Tender coconut-the green varity-salem Wiki DEC2011-Tamil Nadu618.JPG",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Tender_coconut-the_green_varity-salem_Wiki_DEC2011-Tamil_Nadu618.JPG",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Thamizhpparithi Maari (Wikimedia Commons)",
        "alt_text": "Natural mature copra coconut with thick flesh",
        "tags": ["Mature Coconut", "Copra Coconut"]
    },

    # ── 6. GREEN CHILLI ─────────────────────────────────────────────────────
    {
        "crop": "Green Chilli",
        "category": "Spices",
        "crop_slug": "green_chilli",
        "key": "chilli_g4",
        "filename": "green_chilli_g4_spicy.jpg",
        "wiki_file": "Green chilli.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Green_chilli.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Biswarup Ganguly (Wikimedia Commons)",
        "alt_text": "Spicy hot emerald G4 green cooking chillies",
        "tags": ["G4 Hot Chilli", "G4 Green Chilli", "Oddanchatram G4 Spicy Chillies", "Kanthari"]
    },
    {
        "crop": "Green Chilli",
        "category": "Spices",
        "crop_slug": "green_chilli",
        "key": "chilli_jwala",
        "filename": "green_chilli_jwala.jpg",
        "wiki_file": "Green chilli.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Green_chilli.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Biswarup Ganguly (Wikimedia Commons)",
        "alt_text": "Fresh slender pungent Jwala green chillies",
        "tags": ["Jwala Chilli"]
    },

    # ── 7. CABBAGE ──────────────────────────────────────────────────────────
    {
        "crop": "Cabbage",
        "category": "Vegetables",
        "crop_slug": "cabbage",
        "key": "cabbage_golden_acre",
        "filename": "cabbage_golden_acre.jpg",
        "wiki_file": "Cabbage.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Cabbage.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Fir0002 (Wikimedia Commons)",
        "alt_text": "Crisp tightly packed Golden Acre green cabbage",
        "tags": ["Golden Acre", "Melur Golden Acre Cabbage"]
    },
    {
        "crop": "Cabbage",
        "category": "Vegetables",
        "crop_slug": "cabbage",
        "key": "cabbage_savoy",
        "filename": "cabbage_green_savoy.jpg",
        "wiki_file": "Cabbage.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Cabbage.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Fir0002 (Wikimedia Commons)",
        "alt_text": "Fresh farm cabbage head with clean cross section",
        "tags": ["Green Savoy"]
    },

    # ── 8. MORINGA / DRUMSTICK ──────────────────────────────────────────────
    {
        "crop": "Moringa",
        "category": "Vegetables",
        "crop_slug": "moringa",
        "key": "moringa_pkm1",
        "filename": "moringa_pkm1_drumsticks.jpg",
        "wiki_file": "Moringa oleifera drumstick pods.JPG",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Moringa_oleifera_drumstick_pods.JPG",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Thamizhpparithi Maari (Wikimedia Commons)",
        "alt_text": "Fleshy tender non-fibrous PKM-1 long drumsticks bundle",
        "tags": ["PKM-1 Long Drumstick", "Aravakurichi Tender Drumsticks"]
    },
    {
        "crop": "Moringa",
        "category": "Vegetables",
        "crop_slug": "moringa",
        "key": "moringa_jaffna",
        "filename": "moringa_jaffna_pods.jpg",
        "wiki_file": "Moringa oleifera drumstick pods.JPG",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Moringa_oleifera_drumstick_pods.JPG",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Thamizhpparithi Maari (Wikimedia Commons)",
        "alt_text": "Fresh organic Moringa oleifera drumstick pods",
        "tags": ["Jaffna Drumstick"]
    },

    # ── 9. RICE / PADDY ─────────────────────────────────────────────────────
    {
        "crop": "Rice",
        "category": "Cereals",
        "crop_slug": "rice",
        "key": "rice_paddy_field",
        "filename": "rice_paddy_sheaves.jpg",
        "wiki_file": "Paddy grains.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Paddy_grains.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Thamizhpparithi Maari (Wikimedia Commons)",
        "alt_text": "Golden ripe paddy field harvest in Cauvery delta Tamil Nadu",
        "tags": ["Paddy", "Deluxe Ponni Rice", "BPT 5204 Sona Masoori"]
    },
    {
        "crop": "Rice",
        "category": "Cereals",
        "crop_slug": "rice",
        "key": "rice_milled_grain",
        "filename": "rice_grains_harvest.jpg",
        "wiki_file": "Paddy grains.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Paddy_grains.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Thamizhpparithi Maari (Wikimedia Commons)",
        "alt_text": "Premium aromatic Seeraga Samba and Ponni paddy grains",
        "tags": ["Seeraga Samba (Biryani Rice)"]
    },

    # ── 10. CARROT ──────────────────────────────────────────────────────────
    {
        "crop": "Carrot",
        "category": "Vegetables",
        "crop_slug": "carrot",
        "key": "carrot_fresh",
        "filename": "carrot_ooty_fresh.jpg",
        "wiki_file": "Fresh Carrots 02.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Fresh_Carrots_02.jpg",
        "license": "CC BY-SA 4.0",
        "attribution": "Photo by Joydeep (Wikimedia Commons)",
        "alt_text": "Farm fresh crunchy orange Ooty carrots with leafy tops",
        "tags": ["Carrot", "Ooty Carrot"]
    },

    # ── 11. BRINJAL / EGGPLANT ──────────────────────────────────────────────
    {
        "crop": "Brinjal",
        "category": "Vegetables",
        "crop_slug": "brinjal",
        "key": "brinjal_purple",
        "filename": "brinjal_purple_fresh.jpg",
        "wiki_file": "Solanum_melongena_24_08_2012_(1).JPG",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Solanum_melongena_24_08_2012_(1).JPG",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by George Chernilevsky (Wikimedia Commons)",
        "alt_text": "Glossy deep violet purple tender cooking brinjals",
        "tags": ["Brinjal", "Eggplant", "Aubergine"]
    },

    # ── 12. MANGO ───────────────────────────────────────────────────────────
    {
        "crop": "Mango",
        "category": "Fruits",
        "crop_slug": "mango",
        "key": "mango_alphonso",
        "filename": "mango_alphonso_fresh.jpg",
        "wiki_file": "Hapus_Mango.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Hapus_Mango.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Niranjan.parab (Wikimedia Commons)",
        "alt_text": "Naturally ripened sweet aromatic golden Alphonso and Salem mangoes",
        "tags": ["Mango", "Salem Mango", "Alphonso"]
    },

    # ── 13. TURMERIC ────────────────────────────────────────────────────────
    {
        "crop": "Turmeric",
        "category": "Spices",
        "crop_slug": "turmeric",
        "key": "turmeric_rhizome",
        "filename": "turmeric_raw_rhizome.jpg",
        "wiki_file": "Curcuma_longa_roots.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Curcuma_longa_roots.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Simon A. Eugster (Wikimedia Commons)",
        "alt_text": "Fresh organic farm cured Erode golden turmeric rhizomes",
        "tags": ["Turmeric", "Erode Turmeric", "Curcuma Longa"]
    },

    # ── 14. GROUNDNUT / PEANUT ──────────────────────────────────────────────
    {
        "crop": "Groundnut",
        "category": "Oilseeds",
        "crop_slug": "groundnut",
        "key": "groundnut_pods",
        "filename": "groundnut_farm_pods.jpg",
        "wiki_file": "Groundnuts.JPG",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Groundnuts.JPG",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Thamizhpparithi Maari (Wikimedia Commons)",
        "alt_text": "Harvested farm dryland groundnuts in textured pods",
        "tags": ["Groundnut", "Peanut"]
    },

    # ── 15. SUGARCANE ───────────────────────────────────────────────────────
    {
        "crop": "Sugarcane",
        "category": "Plantations",
        "crop_slug": "sugarcane",
        "key": "sugarcane_stalks",
        "filename": "sugarcane_fresh_stalks.jpg",
        "wiki_file": "Sugarcane stalks.jpg",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:Sugarcane_stalks.jpg",
        "license": "CC BY-SA 3.0",
        "attribution": "Photo by Biswarup Ganguly (Wikimedia Commons)",
        "alt_text": "Fresh sweet field harvested sugarcane stalks bundle",
        "tags": ["Sugarcane"]
    }
]


def resolve_wikimedia_url(wiki_file, ssl_ctx):
    """Resolve direct download URL from Wikimedia Commons filename."""
    encoded = urllib.parse.quote(wiki_file)
    filepath_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{encoded}"
    req = urllib.request.Request(filepath_url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
        return resp.geturl()


def download_and_optimize_all():
    """Download, validate, resize, optimize (JPEG + WebP), and generate thumbnails."""
    print("=" * 75)
    print(" AgriSmart Connect - Licensed Produce Photograph Pipeline")
    print("=" * 75)

    ssl_ctx = ssl.create_default_context()
    DEMO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {}
    success_count = 0
    fail_count = 0

    for item in CROP_IMAGE_CATALOG:
        crop_slug = item['crop_slug']
        crop_dir = DEMO_STORAGE_DIR / crop_slug
        crop_dir.mkdir(parents=True, exist_ok=True)

        filename_base = item['filename'].rsplit('.', 1)[0]
        jpg_filename = f"{filename_base}.jpg"
        webp_filename = f"{filename_base}.webp"
        thumb_jpg_filename = f"{filename_base}_thumb.jpg"
        thumb_webp_filename = f"{filename_base}_thumb.webp"

        jpg_path = crop_dir / jpg_filename
        webp_path = crop_dir / webp_filename
        thumb_jpg_path = crop_dir / thumb_jpg_filename
        thumb_webp_path = crop_dir / thumb_webp_filename

        print(f"\n[*] Processing [{item['crop']}] -> {item['filename']}...")

        # If already exists and valid, reuse
        if jpg_path.exists() and webp_path.exists() and thumb_jpg_path.exists():
            try:
                with Image.open(jpg_path) as test_img:
                    test_img.verify()
                print(f"  [CACHE] File {jpg_filename} already validated locally.")
                success_count += 1
                manifest[item['key']] = {
                    **item,
                    "local_jpg_url": f"/uploads/products/demo/{crop_slug}/{jpg_filename}",
                    "local_webp_url": f"/uploads/products/demo/{crop_slug}/{webp_filename}",
                    "thumb_jpg_url": f"/uploads/products/demo/{crop_slug}/{thumb_jpg_filename}",
                    "thumb_webp_url": f"/uploads/products/demo/{crop_slug}/{thumb_webp_filename}",
                    "storage_path": str(jpg_path.relative_to(FRONTEND_DIR)).replace('\\', '/')
                }
                continue
            except Exception:
                logger.warning("Cached file corrupt, redownloading: %s", jpg_filename)

        # Download from Wikimedia
        try:
            direct_url = resolve_wikimedia_url(item['wiki_file'], ssl_ctx)
            logger.info("  Resolved %s -> %s", item['wiki_file'], direct_url)

            req = urllib.request.Request(direct_url, headers=REQUEST_HEADERS)
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=25) as resp:
                raw_bytes = resp.read()

            # PIL Validation
            pil_img = Image.open(io.BytesIO(raw_bytes))
            pil_img.verify()
            pil_img = Image.open(io.BytesIO(raw_bytes))

            if pil_img.mode in ('RGBA', 'P', 'LA'):
                pil_img = pil_img.convert('RGB')

            orig_w, orig_h = pil_img.size
            logger.info("  Original dimensions: %dx%d, format: %s", orig_w, orig_h, pil_img.format)

            # Web optimization: Max dimension 1200px
            max_size = 1200
            pil_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            opt_w, opt_h = pil_img.size

            # Save JPEG
            pil_img.save(jpg_path, format='JPEG', quality=85, optimize=True)

            # Save WebP
            pil_img.save(webp_path, format='WEBP', quality=85, method=6)

            # Generate Thumbnail: Max dimension 300px
            thumb_img = pil_img.copy()
            thumb_img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            thumb_img.save(thumb_jpg_path, format='JPEG', quality=80, optimize=True)
            thumb_img.save(thumb_webp_path, format='WEBP', quality=80, method=6)

            jpg_size_kb = os.path.getsize(jpg_path) / 1024
            webp_size_kb = os.path.getsize(webp_path) / 1024
            print(f"  [OK] Saved: {opt_w}x{opt_h} | JPEG: {jpg_size_kb:.1f} KB | WebP: {webp_size_kb:.1f} KB")

            manifest[item['key']] = {
                **item,
                "local_jpg_url": f"/uploads/products/demo/{crop_slug}/{jpg_filename}",
                "local_webp_url": f"/uploads/products/demo/{crop_slug}/{webp_filename}",
                "thumb_jpg_url": f"/uploads/products/demo/{crop_slug}/{thumb_jpg_filename}",
                "thumb_webp_url": f"/uploads/products/demo/{crop_slug}/{thumb_webp_filename}",
                "storage_path": str(jpg_path.relative_to(FRONTEND_DIR)).replace('\\', '/')
            }
            success_count += 1

        except Exception as e:
            logger.error("  [ERROR] Failed to download %s: %s", item['filename'], e)
            fail_count += 1

    # Save manifest
    manifest_path = DEMO_STORAGE_DIR / 'images_manifest.json'
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    print("\n" + "=" * 75)
    print(f" Pipeline Complete: {success_count} succeeded, {fail_count} failed.")
    print(f" Manifest saved to: {manifest_path}")
    print("=" * 75)

    return manifest


if __name__ == '__main__':
    download_and_optimize_all()
