import json
from datetime import datetime
from openai import OpenAI
import os
import time

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

OUTPUT_FOLDER = "/product_standardization_output"
CHECKPOINT_FILE = f"{OUTPUT_FOLDER}/checkpoint.json"

def load_files(data_file, catalog_file):
    """Load both JSON files"""
    with open(data_file, 'r') as f:
        data = json.load(f)
    
    with open(catalog_file, 'r') as f:
        catalog = json.load(f)
    
    return data, catalog

def normalize_shade(shade):
    """Normalize shade string"""
    if not shade:
        return ""
    shade_str = str(shade).strip()
    shade_str = shade_str.replace("No.", "").replace("no.", "").replace("#", "").strip()
    return shade_str

def extract_shade_number(shade):
    """Extract the main number from a shade"""
    import re
    shade_str = str(shade).strip()
    match = re.search(r'^\d+\.?\d*', shade_str)
    if match:
        return match.group()
    return None

def ai_match_product(raw_product, brand, raw_shade, catalog):
    """Use OpenAI to match product line to catalog, validate with shade"""
    if not raw_product or raw_product == "" or not brand:
        if not brand:
            return None, 0, "no_brand"
        return None, 0, "empty_input"
    
    # Get products for this brand
    products_list = [p for p in catalog['products'] if p['brand'] == brand]
    
    if not products_list:
        return None, 0, "brand_has_no_products"
    
    # If we have a shade, filter products that have this shade
    if raw_shade and raw_shade != "":
        raw_normalized = normalize_shade(raw_shade)
        raw_number = extract_shade_number(raw_normalized)
        
        # Find products that have matching shades
        valid_products = []
        for p in products_list:
            for shade in p['shades']:
                shade_normalized = normalize_shade(shade)
                shade_number = extract_shade_number(shade_normalized)
                
                # Check if shade matches
                if shade_normalized.lower() == raw_normalized.lower():
                    valid_products.append(p['product_line'])
                    break
                # Or if numbers match
                elif raw_number and shade_number and raw_number == shade_number:
                    valid_products.append(p['product_line'])
                    break
        
        # If we found products with matching shades, use only those
        if valid_products:
            products_to_match = valid_products
        else:
            # No shade match, use all products
            products_to_match = [p['product_line'] for p in products_list]
    else:
        products_to_match = [p['product_line'] for p in products_list]
    
    prompt = f"""You are matching beauty product names. Given a raw product name, find the best match from the catalog.

Raw product: "{raw_product}"
Brand: "{brand}"

Match to one of these products (case-sensitive, use exact spelling):
{chr(10).join(products_to_match)}

Rules:
- "yummy skin" matches "Yummy Skin Soothing Serum Skin Tint Foundation..."
- "Gel Grip Gel" matches "Hydro Grip 12-Hour Hydrating Gel Skin Tint"
- Shortened product names match full product names
- Focus on key identifying words
- Return the EXACT product name from the list above
- Only return "NONE" if there's truly no reasonable match

Answer with just the exact product name or NONE:"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        time.sleep(0.1)
        
        match = response.choices[0].message.content.strip()
        
        if match == "NONE":
            return None, 0, "ai_returned_none"
        
        if match not in products_to_match:
            return None, 0, "ai_hallucinated"
        
        return match, 90, "success"
        
    except Exception as e:
        print(f"   ⚠️  AI error for product '{raw_product}': {e}")
        return None, 0, "api_error"

def get_item_key(item):
    """Generate unique key for an item"""
    vid_id = item.get('canonical_video_id', '')
    brand = item.get('brand_raw_examples', '')
    product = item.get('product_line_raw_examples', '')
    shade = item.get('shade_raw_examples', '')
    return f"{vid_id}|{brand}|{product}|{shade}"

def standardize_products(data_file, catalog_file):
    """Standardize products (requires brand_standardized field) with checkpoint support"""
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    print("📂 Loading files...")
    data, catalog = load_files(data_file, catalog_file)
    
    print(f"✅ Loaded {len(data)} items")
    print(f"✅ Catalog has {len(catalog['products'])} products")
    print()
    
    # Load checkpoint if exists
    processed_keys = set()
    standardized = []
    output_file = None
    non_match_file = None
    
    if os.path.exists(CHECKPOINT_FILE):
        print(f"Found checkpoint file - loading previous progress...")
        with open(CHECKPOINT_FILE, 'r') as f:
            checkpoint = json.load(f)
            
            # Get output file path from checkpoint
            output_files = checkpoint.get('output_files', {})
            output_file = output_files.get('standardized')
            non_match_file = output_files.get('non_matches')
            
            # Load existing data
            if output_file and os.path.exists(output_file):
                with open(output_file, 'r') as sf:
                    standardized = json.load(sf)
                # Extract processed keys
                processed_keys = set([get_item_key(item) for item in standardized])
                print(f"  Loaded {len(standardized)} existing standardized items")
        
        print(f"Resuming from {len(processed_keys)} already processed items\n")
    
    # Create new output file if we don't have one from checkpoint
    if output_file is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"{OUTPUT_FOLDER}/products_standardized_{timestamp}.json"
        non_match_file = f"{OUTPUT_FOLDER}/products_not_found_{timestamp}.json"
        print(f"Starting new session: {timestamp}\n")
    
    # Filter out already processed items
    items_to_process = [item for item in data if get_item_key(item) not in processed_keys]
    
    print(f"Will process {len(items_to_process)} new items out of {len(data)} total\n")
    
    if len(items_to_process) == 0:
        print("All items already processed!")
        return standardized
    
    print("🔄 Standardizing products...")
    
    ai_calls = 0
    errors = 0
    skipped = 0
    
    def save_all_files():
        """Save all output files immediately"""
        # Save standardized items
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(standardized, f, indent=2, ensure_ascii=False)
        
        # Collect and save non-matches
        non_match_products = {}
        for item in standardized:
            if item.get('brand_standardized') and not item.get('product_line_standardized'):
                brand = item.get('brand_standardized')
                raw_product = item.get('product_line_raw_examples', '').strip()
                raw_shade = item.get('shade_raw_examples', '').strip()
                status = item.get('product_match_status', 'unknown')
                
                if raw_product:  # Only count if there was a product to match
                    key = (brand, raw_product, raw_shade, status)
                    non_match_products[key] = non_match_products.get(key, 0) + 1
        
        if non_match_products:
            non_match_list = [
                {
                    "brand": brand,
                    "product_raw": prod,
                    "shade_raw": shade,
                    "reason": status,
                    "count": count,
                    "product_line_standardized": None
                }
                for (brand, prod, shade, status), count in sorted(non_match_products.items(), key=lambda x: x[1], reverse=True)
            ]
            with open(non_match_file, 'w', encoding='utf-8') as f:
                json.dump(non_match_list, f, indent=2, ensure_ascii=False)
        
        # Save checkpoint
        checkpoint_data = {
            'output_files': {
                'standardized': output_file,
                'non_matches': non_match_file
            },
            'last_updated': datetime.now().isoformat()
        }
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
    
    for i, item in enumerate(items_to_process, start=1):
        total_processed = len(processed_keys) + i
        
        # Get the standardized brand from previous step
        brand_match = item.get('brand_standardized')
        raw_product = item.get('product_line_raw_examples', '').strip()
        raw_shade = item.get('shade_raw_examples', '').strip()
        
        print(f"[{total_processed}/{len(data)}] Processing: {brand_match or '(no brand)'} | {raw_product[:30]}")
        
        # Only match product if we have a brand
        if brand_match and raw_product:
            try:
                product_match, product_score, match_status = ai_match_product(raw_product, brand_match, raw_shade, catalog)
                ai_calls += 1
            except Exception as e:
                print(f"   ⚠️  Error on product '{raw_product}': {e}")
                product_match, product_score, match_status = None, 0, "exception"
                errors += 1
        else:
            product_match, product_score, match_status = None, 0, "no_brand" if not brand_match else "empty_input"
            if not brand_match:
                skipped += 1
        
        # Create new item with product standardized
        new_item = {
            **item,  # Keep everything including brand_standardized
            'product_line_standardized': product_match,
            'product_standardized_score': product_score,
            'product_match_status': match_status
        }
        
        standardized.append(new_item)
        processed_keys.add(get_item_key(item))
        
        # Save after each item
        print(f"  💾 Writing to disk...")
        save_all_files()
        
        if i % 50 == 0:
            print(f"\n📊 Progress: {total_processed}/{len(data)} (AI calls: {ai_calls}, Errors: {errors}, Skipped: {skipped})\n")
    
    print()
    print(f"✅ Done!")
    print()
    
    # Stats
    product_matches = sum(1 for item in standardized if item.get('product_line_standardized'))
    items_with_brands = sum(1 for item in standardized if item.get('brand_standardized'))
    
    print("📊 Final Summary:")
    print(f"   Total AI calls made: {ai_calls}")
    print(f"   Errors encountered: {errors}")
    print(f"   Skipped (no brand): {skipped}")
    print(f"   Product matches: {product_matches}/{items_with_brands} items with brands ({round(product_matches/items_with_brands*100) if items_with_brands else 0}%)")
    
    # Collect unique non-matches with reasons
    non_match_products = {}
    for item in standardized:
        if item.get('brand_standardized') and not item.get('product_line_standardized'):
            brand = item.get('brand_standardized')
            raw_product = item.get('product_line_raw_examples', '').strip()
            raw_shade = item.get('shade_raw_examples', '').strip()
            status = item.get('product_match_status', 'unknown')
            
            if raw_product:  # Only count if there was a product to match
                key = (brand, raw_product, raw_shade, status)
                non_match_products[key] = non_match_products.get(key, 0) + 1
    
    if non_match_products:
        # Group by status
        not_in_catalog = [(brand, prod, shade, count) for (brand, prod, shade, status), count in non_match_products.items() if status == 'ai_returned_none']
        hallucinated = [(brand, prod, shade, count) for (brand, prod, shade, status), count in non_match_products.items() if status == 'ai_hallucinated']
        other = [(brand, prod, shade, count) for (brand, prod, shade, status), count in non_match_products.items() if status not in ['ai_returned_none', 'ai_hallucinated']]
        
        print()
        print(f"🔍 Products not found ({len(non_match_products)} unique):")
        
        if not_in_catalog:
            print(f"\n   NOT IN CATALOG ({len(not_in_catalog)}):")
            for brand, prod, shade, count in sorted(not_in_catalog, key=lambda x: x[3], reverse=True)[:10]:
                shade_info = f" | Shade: {shade}" if shade else ""
                print(f"      {brand} | {prod}{shade_info} ({count}x)")
        
        if hallucinated:
            print(f"\n   AI HALLUCINATED ({len(hallucinated)}):")
            for brand, prod, shade, count in sorted(hallucinated, key=lambda x: x[3], reverse=True)[:10]:
                shade_info = f" | Shade: {shade}" if shade else ""
                print(f"      {brand} | {prod}{shade_info} ({count}x)")
        
        if other:
            print(f"\n   OTHER ERRORS ({len(other)}):")
            for brand, prod, shade, count in sorted(other, key=lambda x: x[3], reverse=True)[:10]:
                shade_info = f" | Shade: {shade}" if shade else ""
                print(f"      {brand} | {prod}{shade_info} ({count}x)")
        
        print(f"\n📁 Saved detailed list to: {non_match_file}")
    
    print(f"\n📁 Saved standardized products to: {output_file}")
    
    return standardized

if __name__ == "__main__":
    # Use the output from brands_standardized script as input
    data_file = "json file"
    catalog_file = "catalog file"
    
    standardize_products(data_file, catalog_file)