"""One-time data fix — run once via Render Shell: `python fix_ngo_items.py`

1. Deletes the discontinued NGO support items (Input Financing, Technical
   Support, Operational Support, Grant Funding) from every product.
2. Sets every product's NGO cap to 6.55%.
3. Corrects each remaining tiered item's stored Max % to its real highest
   tier value (e.g. Matching Fund -> 4.30%, not the old 1.00% placeholder).
"""
from app import create_app
from app.models import db, Product, NGOSupportItem

app = create_app()

REMOVED_NAMES = {
    "input financing (direct to vendor)",
    "technical support",
    "operational support",
    "grant funding",
}

with app.app_context():
    removed = 0
    for item in NGOSupportItem.query.all():
        if item.name.strip().lower() in REMOVED_NAMES:
            db.session.delete(item)
            removed += 1
    db.session.commit()
    print(f"Deleted {removed} discontinued NGO support item(s).")

    capped = 0
    for product in Product.query.all():
        if product.pricing_input:
            product.pricing_input.ngo_max_price_impact_pct = 0.0655
            capped += 1
    db.session.commit()
    print(f"Set NGO cap to 6.55% for {capped} product(s).")

    fixed_max = 0
    for item in NGOSupportItem.query.all():
        if item.tiers:
            real_max = max(t.rate_reduction for t in item.tiers)
            if abs((item.max_price_impact_pct or 0) - real_max) > 0.0001:
                item.max_price_impact_pct = real_max
                fixed_max += 1
    db.session.commit()
    print(f"Corrected Max % on {fixed_max} item(s) to match their real highest tier.")

    print("Done.")