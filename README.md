Product Catalogue: Product_Catalogue_normalized_merged_catalog_sorted_Feb10_deduped_sameformat.json 
- List of as many Brands - Product Line - Shade List trios on the market. Scraped from Sephora, Ulta, Bluemercury, Nordstrom, Target, Amazon, DTC websites

Sample Data: brands_standardized_manually_fixed_20260220_140406_sample.json
- In this file, the brand names have been standardized already from "brand_raw_examples" to "brand_standardized".
-  "product_line_raw_examples" and "shade_raw_examples" need to be cleaned up further.
-  find brand based on brand_standardized (as already), then lookup shade in product list:
    1. if shade match found only once, then use that as shade_standardized and the product line of the list as product standardized
    2. if shade match found multiple times, use the raw product line to fuzzily find the closer match and then use that corresponding product line
    the logic is that product lines are more complicated than shades. so finding product match is harder, but using shade name, we can make this easier.

Sample data:
* Crossed-out fields are irrelevant
  
{
    "canonical_video_id": "6978042476519001349",
    "video_url": "https://www.tiktok.com/@ash.thrower/video/6978042476519001349",
    ~~"source": "combined_transcript",
    "confidence": 2,
    "brand_clean": "L'Oréal",
    "product_line_clean": "True Match Nude Hyaluronic Tinted Serum",
    "shade_clean": null,
    "brand_score": 93,
    "product_score": 90,
    "shade_score": 0,
    "shade_variant_used_for_match": null,~~
    "brand_raw_examples": "L'Oreal",
    "product_line_raw_examples": "True Match",
    "shade_raw_examples": "4.d/4.w",
    "brand_standardized": "L'Oréal Paris",
    "brand_standardized_score": 95,
    "brand_match_status": "success"
  },
