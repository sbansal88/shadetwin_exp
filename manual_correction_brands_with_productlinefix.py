import json
from datetime import datetime
import os

CORRECTIONS_FILE = "brand_corrections_history.json"

def load_files(not_found_file, standardized_file):
    """Load both JSON files with error handling"""
    with open(not_found_file, 'r') as f:
        not_found = json.load(f)
    
    # Try to load with strict=False to handle control characters
    try:
        with open(standardized_file, 'r', encoding='utf-8') as f:
            standardized = json.load(f, strict=False)
    except json.JSONDecodeError as e:
        print(f"⚠️  Error loading standardized file: {e}")
        print("Attempting to fix control characters...")
        
        # Read and clean the file
        with open(standardized_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove invalid control characters (keep \n, \r, \t)
        import re
        content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', content)
        
        # Try parsing again
        try:
            standardized = json.loads(content)
        except json.JSONDecodeError as e2:
            print(f"❌ Still couldn't parse. Error: {e2}")
            print("Trying one more approach...")
            
            # Last resort: read line by line
            with open(standardized_file, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            standardized = json.loads(content)
    
    return not_found, standardized

def load_previous_corrections():
    """Load previously saved corrections"""
    if os.path.exists(CORRECTIONS_FILE):
        with open(CORRECTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_corrections(corrections):
    """Save corrections history"""
    with open(CORRECTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(corrections, f, indent=2, ensure_ascii=False)

def get_product_info_for_brand(standardized, raw_brand):
    """Get product line info for items with this raw brand"""
    # Find all items with this raw brand
    matching_items = [item for item in standardized 
                     if item.get('brand_raw_examples', '').strip() == raw_brand]
    
    if not matching_items:
        return None
    
    # Get unique product lines
    product_lines = set()
    for item in matching_items:
        pl = item.get('product_line_raw_examples', '').strip()
        if pl:
            product_lines.add(pl)
    
    return {
        'count': len(matching_items),
        'product_lines': sorted(product_lines) if product_lines else ['(empty)'],
        'sample_item': matching_items[0]
    }

def manual_brand_fix(not_found_file, standardized_file):
    """Manually fix brands that weren't found"""
    
    print("📂 Loading files...")
    not_found, standardized = load_files(not_found_file, standardized_file)
    
    # Load previous corrections
    previous_corrections = load_previous_corrections()
    if previous_corrections:
        print(f"📚 Loaded {len(previous_corrections)} previous corrections")
    
    print(f"✅ Loaded {len(not_found)} brands that need fixing")
    print(f"✅ Loaded {len(standardized)} standardized items")
    print()
    
    # Create mapping of raw brand -> corrected brand
    brand_mapping = {}
    product_line_updates = {}  # Track product line changes
    corrections_made = []  # Track what we corrected in this session
    
    # Sort by count (most common first)
    not_found_sorted = sorted(not_found, key=lambda x: x['count'], reverse=True)
    
    print("🔧 Manual brand & product line fixing")
    print("=" * 60)
    print("Options for each brand:")
    print("  1. Enter standardized brand name")
    print("  2. Type 'keep' to use the raw name as-is")
    print("  3. Type 'move' to move brand → product line (if product line empty)")
    print("  4. Press ENTER to skip (leave as null)")
    print("  5. Type 'quit' to save and exit")
    print("=" * 60)
    print()
    
    for i, item in enumerate(not_found_sorted, start=1):
        raw_brand = item['brand_raw']
        count = item['count']
        
        print(f"\n[{i}/{len(not_found_sorted)}] Brand: '{raw_brand}'")
        print(f"   Appears {count} times")
        print(f"   Current status: {item['reason']}")
        
        # Show product line info
        product_info = get_product_info_for_brand(standardized, raw_brand)
        if product_info:
            product_lines_str = ', '.join([f"'{pl}'" for pl in product_info['product_lines']])
            print(f"   Product lines in data: {product_lines_str}")
        # Check if we have a previous correction
        if raw_brand in previous_corrections:
            prev_correction = previous_corrections[raw_brand]
            print(f"   💡 Previous correction: '{prev_correction}'")
            use_prev = input("   Use previous correction? (y/n/quit): ").strip().lower()
            if use_prev == 'quit':
                print("\n⚠️  Stopping early. Saving progress...")
                break
            elif use_prev == 'y':
                brand_mapping[raw_brand] = prev_correction
                corrections_made.append({
                    "raw_brand": raw_brand,
                    "standardized_brand": prev_correction,
                    "count": count,
                    "source": "previous_correction"
                })
                print(f"   ✅ Will map '{raw_brand}' → '{prev_correction}'")
                continue
        
        user_input = input("   Enter brand name (or 'keep'/'move'/'quit'/ENTER): ").strip()
        
        if user_input.lower() == 'quit':
            print("\n⚠️  Stopping early. Saving progress...")
            break
        
        if user_input == "":
            print("   ⏭️  Skipped")
            continue
        
        if user_input.lower() == 'keep':
            brand_mapping[raw_brand] = raw_brand
            corrections_made.append({
                "raw_brand": raw_brand,
                "standardized_brand": raw_brand,
                "count": count,
                "source": "kept_as_is"
            })
            print(f"   ✅ Keeping '{raw_brand}' as-is")
            
        elif user_input.lower() == 'move':
            # Check if product line is empty
            if product_info and product_info['product_lines'] == ['(empty)']:
                # Product line is empty, can move
                print(f"   📦 Moving '{raw_brand}' from brand → product line")
                new_brand = input("   Enter correct brand name: ").strip()
                
                if new_brand:
                    # Store that we need to move this
                    product_line_updates[raw_brand] = {
                        'new_brand': new_brand,
                        'move_to_product_line': True
                    }
                    brand_mapping[raw_brand] = new_brand
                    corrections_made.append({
                        "raw_brand": raw_brand,
                        "standardized_brand": new_brand,
                        "action": "moved_to_product_line",
                        "count": count,
                        "source": "manual_move"
                    })
                    print(f"   ✅ Will move '{raw_brand}' to product line and set brand to '{new_brand}'")
                else:
                    print("   ⏭️  Skipped - no brand name provided")
            else:
                print(f"   ⚠️  Cannot move - product line not empty: {product_info['product_lines']}")
                print(f"   You can still correct the brand name and optionally fix product line")
                
                new_brand = input("   Enter correct brand name: ").strip()
                if new_brand:
                    brand_mapping[raw_brand] = new_brand
                    
                    # Ask if they want to fix product line too
                    fix_pl = input("   Fix product line too? (y/n): ").strip().lower()
                    if fix_pl == 'y':
                        new_pl = input("   Enter correct product line: ").strip()
                        if new_pl:
                            product_line_updates[raw_brand] = {
                                'new_brand': new_brand,
                                'new_product_line': new_pl,
                                'move_to_product_line': False
                            }
                    
                    corrections_made.append({
                        "raw_brand": raw_brand,
                        "standardized_brand": new_brand,
                        "count": count,
                        "source": "manual_entry"
                    })
                    print(f"   ✅ Will map '{raw_brand}' → '{new_brand}'")
                else:
                    print("   ⏭️  Skipped")
        else:
            brand_mapping[raw_brand] = user_input
            corrections_made.append({
                "raw_brand": raw_brand,
                "standardized_brand": user_input,
                "count": count,
                "source": "manual_entry"
            })
            print(f"   ✅ Will map '{raw_brand}' → '{user_input}'")
    
    if not brand_mapping:
        print("\n⚠️  No brands were mapped. Exiting without changes.")
        return
    
    print()
    print("=" * 60)
    print(f"📝 Applying {len(brand_mapping)} brand mappings...")
    
    # Apply mappings to standardized file
    updates_made = 0
    product_line_moves = 0
    
    for item in standardized:
        raw_brand = item.get('brand_raw_examples', '').strip()
        
        if raw_brand in brand_mapping:
            item['brand_standardized'] = brand_mapping[raw_brand]
            item['brand_standardized_score'] = 100  # Manual = 100% confidence
            item['brand_match_status'] = 'manual_fix'
            updates_made += 1
            
            # Check if we need to update product line
            if raw_brand in product_line_updates:
                pl_update = product_line_updates[raw_brand]
                
                if pl_update.get('move_to_product_line'):
                    # Move brand to product line
                    item['product_line_raw_examples'] = raw_brand
                    item['brand_raw_examples'] = pl_update['new_brand']
                    product_line_moves += 1
                    
                elif 'new_product_line' in pl_update:
                    # Just update product line
                    item['product_line_raw_examples'] = pl_update['new_product_line']
    
    print(f"✅ Updated {updates_made} items")
    if product_line_moves > 0:
        print(f"✅ Moved {product_line_moves} items: brand → product line")
    
    # Save updated standardized file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"brands_standardized_manually_fixed_{timestamp}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(standardized, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved to: {output_file}")
    
    # Update and save corrections history
    previous_corrections.update(brand_mapping)
    save_corrections(previous_corrections)
    print(f"💾 Updated corrections history: {CORRECTIONS_FILE}")
    
    # Save this session's corrections for reference
    session_corrections_file = f"brand_corrections_session_{timestamp}.json"
    with open(session_corrections_file, 'w', encoding='utf-8') as f:
        json.dump(corrections_made, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved this session's corrections to: {session_corrections_file}")
    
    print()
    print("📊 Summary:")
    print(f"   Brands mapped: {len(brand_mapping)}")
    print(f"   Items updated: {updates_made}")
    print(f"   Product line moves: {product_line_moves}")
    print(f"   Remaining unfixed brands: {len(not_found) - len(brand_mapping)}")
    print(f"   Total corrections in history: {len(previous_corrections)}")
    
    # Break down corrections by source
    kept_count = sum(1 for c in corrections_made if c.get('source') == 'kept_as_is')
    manual_count = sum(1 for c in corrections_made if c.get('source') == 'manual_entry')
    prev_count = sum(1 for c in corrections_made if c.get('source') == 'previous_correction')
    moved_count = sum(1 for c in corrections_made if c.get('source') == 'manual_move')
    
    print()
    print("📈 This session:")
    print(f"   Kept as-is: {kept_count}")
    print(f"   Manually entered: {manual_count}")
    print(f"   Moved to product line: {moved_count}")
    print(f"   Used previous correction: {prev_count}")

if __name__ == "__main__":
    # Update these paths
    not_found_file = "/Users/vishnujayaprakash/Desktop/rung/Catalogue Standardization/brand_standardization_output/brands_not_found_20260219_164406.json"
    standardized_file = "/Users/vishnujayaprakash/Desktop/rung/Catalogue Standardization/brand_standardization_output/brands_standardized_20260219_164406.json"
    
    manual_brand_fix(not_found_file, standardized_file)

'''

**New features:**

1. **Shows product line info** - Displays what product lines are associated with each raw brand
2. **'move' command** - Moves brand → product line (only if product line is empty)
3. **Product line correction** - Option to fix product line when correcting brand
4. **Tracks moves** - Shows how many items were restructured

**Example session:**
```
[1/89] Brand: 'Born This Way'
   Appears 12 times
   Current status: ai_returned_none
   Product lines in data: '(empty)'
   Enter brand name (or 'keep'/'move'/'quit'/ENTER): move
   📦 Moving 'Born This Way' from brand → product line
   Enter correct brand name: Too Faced
   ✅ Will move 'Born This Way' to product line and set brand to 'Too Faced'

[2/89] Brand: 'Fit Me'
   Appears 5 times
   Current status: ai_returned_none
   Product lines in data: 'Matte + Poreless', 'Dewy + Smooth'
   ⚠️  Cannot move - product line not empty
   You can still correct the brand name and optionally fix product line
   Enter correct brand name: Maybelline
   Fix product line too? (y/n): n
   ✅ Will map 'Fit Me' → 'Maybelline'
   '''