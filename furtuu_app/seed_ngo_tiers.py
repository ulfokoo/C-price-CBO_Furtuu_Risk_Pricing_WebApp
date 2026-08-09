from app import create_app
from app.models import db, Product, NGOSupportItem, NGOSupportTier

app = create_app()

TIER_DATA = {
    "seed fund": [(">50%", 2.8), ("40%-50%", 2.2), ("30%-39%", 1.7), ("20%-29%", 1.1), ("0%", 0.0)],
    "seed money ngo": [(">50%", 2.8), ("40%-50%", 2.2), ("30%-39%", 1.7), ("20%-29%", 1.1), ("0%", 0.0)],
    "guarantee": [(">50%", 2.8), ("40%-50%", 2.2), ("30%-39%", 1.7), ("20%-29%", 1.1), ("0%", 0.0)],
    "insurance coverage": [(">80%", 1.1), ("65%-80%", 0.8), ("50%-64%", 0.6), ("<50%", 0.5), ("0%", 0.0)],
    "match fund": [(">85%", 4.3), ("70%-85%", 3.7), ("50%-69%", 2.8), ("30%-49%", 1.9), ("10%-29%", 1.0), ("0%", 0.0)],
    "matching fund": [(">85%", 4.3), ("70%-85%", 3.7), ("50%-69%", 2.8), ("30%-49%", 1.9), ("10%-29%", 1.0), ("0%", 0.0)],
}

with app.app_context():
    for product in Product.query.all():
        if not NGOSupportItem.query.filter_by(product_id=product.id, name="Guarantee").first():
            db.session.add(NGOSupportItem(
                product_id=product.id, name="Guarantee",
                percent=0.0, max_price_impact_pct=0.028,
                is_active=True, display_order=99,
            ))
            db.session.commit()

        for item in NGOSupportItem.query.filter_by(product_id=product.id):
            key = item.name.strip().lower()
            if key not in TIER_DATA:
                continue
            NGOSupportTier.query.filter_by(item_id=item.id).delete()
            for i, (label, pct) in enumerate(TIER_DATA[key], start=1):
                db.session.add(NGOSupportTier(
                    item_id=item.id, label=label,
                    rate_reduction=pct / 100.0, display_order=i,
                ))
            db.session.commit()
            print(f"Seeded tiers for '{item.name}' (product: {product.name})")

    print("Done.")