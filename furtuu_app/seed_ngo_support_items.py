from app import create_app
from app.models import db, Product, NGOSupportItem

app = create_app()

with app.app_context():
    product = Product.query.filter(Product.name.like("Furtuu%")).first()
    if not product:
        print("Product not found.")
    else:
        NGOSupportItem.query.filter_by(product_id=product.id).delete()

        items = [
            ("Matching Fund", 10.0),
            ("Seed Money NGO", 10.0),
            ("Insurance Coverage", 5.0),
        ]
        for i, (name, pct) in enumerate(items, start=1):
            db.session.add(NGOSupportItem(
                product_id=product.id,
                name=name,
                percent=pct / 100.0,
                is_active=True,
                display_order=i,
            ))

        if product.pricing_input:
            product.pricing_input.ngo_max_price_impact_pct = 0.0655

        db.session.commit()
        print("NGO support items seeded, cap set to 6.55%.")