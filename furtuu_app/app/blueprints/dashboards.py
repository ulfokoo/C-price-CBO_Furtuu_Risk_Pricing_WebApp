from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import login_required

from app.models import Product
from app import calculations as calc
from app.models import NGOSupportItem
from app import db
from app.blueprints.admin import admin_required

dashboards_bp = Blueprint("dashboards", __name__)


def get_product_or_404(product_id):
    return Product.query.get_or_404(product_id)


@dashboards_bp.route("/")
@login_required
def home():
    products = Product.query.order_by(Product.name).all()
    return render_template("dashboards/home.html", products=products)


@dashboards_bp.route("/product/<int:product_id>/scorecard")
@login_required
def scorecard(product_id):
    product = get_product_or_404(product_id)
    result = calc.compute_scorecard(product)
    return render_template("dashboards/scorecard.html", product=product, result=result)


@dashboards_bp.route("/product/<int:product_id>/pricing")
@login_required
def pricing(product_id):
    product = get_product_or_404(product_id)
    if not product.pricing_input:
        return render_template("dashboards/pricing_missing.html", product=product)
    result = calc.compute_pricing(product)
    return render_template("dashboards/pricing.html", product=product, result=result)


@dashboards_bp.route("/product/<int:product_id>/cost-of-fund")
@login_required
def cost_of_fund(product_id):
    product = get_product_or_404(product_id)
    result = calc.compute_cost_of_fund(product)
    return render_template("dashboards/cost_of_fund.html", product=product, result=result)


@dashboards_bp.route("/product/<int:product_id>/pd-transformation")
@login_required
def pd_transformation(product_id):
    product = get_product_or_404(product_id)
    result = calc.compute_pd_transformation(product)
    return render_template("dashboards/pd_transformation.html", product=product, result=result)


@dashboards_bp.route("/product/<int:product_id>/reference")
@login_required
def reference(product_id):
    product = get_product_or_404(product_id)
    return render_template("dashboards/reference.html", product=product)


@dashboards_bp.route("/product/<int:product_id>/ngo-support")
@login_required
def ngo_support(product_id):
    product = get_product_or_404(product_id)
    result = calc.compute_ngo_support(product)
    return render_template("dashboards/ngo_support.html", product=product, result=result)


@dashboards_bp.route("/product/<int:product_id>/ngo-support/add", methods=["POST"])
@login_required
def add_ngo_support(product_id):
    from flask import request, redirect, url_for, flash
    product = get_product_or_404(product_id)
    name = request.form.get("name", "").strip()
    percent = request.form.get("percent", type=float)
    max_price_impact_pct = request.form.get("max_price_impact_pct", type=float)
    if name and percent is not None:
        db.session.add(NGOSupportItem(product_id=product.id, name=name, percent=percent / 100.0,
                                        max_price_impact_pct=(max_price_impact_pct or 0) / 100.0,
                                        display_order=len(product.ngo_support_items) + 1))
        db.session.commit()
        flash(f"NGO support item '{name}' added.", "success")
    return redirect(request.referrer or url_for("dashboards.ngo_support", product_id=product.id))


@dashboards_bp.route("/ngo-support/<int:item_id>/edit", methods=["POST"])
@login_required
def edit_ngo_support(item_id):
    from flask import request, redirect, url_for, flash
    item = NGOSupportItem.query.get_or_404(item_id)
    name = request.form.get("name", "").strip()
    percent = request.form.get("percent", type=float)
    if name:
        item.name = name
    if percent is not None:
        item.percent = percent / 100.0
    max_price_impact_pct = request.form.get("max_price_impact_pct", type=float)
    if max_price_impact_pct is not None:
        item.max_price_impact_pct = max_price_impact_pct / 100.0
    item.is_active = bool(request.form.get("is_active"))
    db.session.commit()
    flash("NGO support item updated.", "success")
    return redirect(request.referrer or url_for("dashboards.ngo_support", product_id=item.product_id))


@dashboards_bp.route("/ngo-support/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_ngo_support(item_id):
    from flask import redirect, url_for, flash
    item = NGOSupportItem.query.get_or_404(item_id)
    product_id = item.product_id
    db.session.delete(item)
    db.session.commit()
    flash("NGO support item deleted.", "info")
    return redirect(request.referrer or url_for("dashboards.ngo_support", product_id=product_id))

