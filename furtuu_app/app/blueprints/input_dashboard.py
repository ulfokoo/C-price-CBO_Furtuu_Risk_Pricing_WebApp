from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required

from app import db
from app.models import Product, SubParameter
from app import calculations as calc

input_bp = Blueprint("input", __name__)


@input_bp.route("/input", methods=["GET"])
@login_required
def input_dashboard():
    product_id = request.args.get("product_id", type=int)
    products = Product.query.order_by(Product.name).all()
    product = None
    result = None
    pricing_result = None
    if product_id:
        product = Product.query.get_or_404(product_id)
        result = calc.compute_scorecard(product)
        if product.pricing_input:
            pricing_result = calc.compute_pricing(product)
    elif products:
        product = products[0]
        result = calc.compute_scorecard(product)
        if product.pricing_input:
            pricing_result = calc.compute_pricing(product)

    return render_template(
        "input/dashboard.html",
        products=products,
        product=product,
        result=result,
        pricing_result=pricing_result,
    )


@input_bp.route("/input/<int:product_id>/submit", methods=["POST"])
@login_required
def submit_assessment(product_id):
    product = Product.query.get_or_404(product_id)
    for cat in product.categories:
        for sp in cat.sub_parameters:
            field = f"sp_{sp.id}"
            if field in request.form:
                val = request.form.get(field, type=int)
                sp.selected_option_id = val if val else None
    db.session.commit()
    flash("Assessment results updated. Scores recalculated.", "success")
    return redirect(url_for("input.input_dashboard", product_id=product.id))


@input_bp.route("/input/<int:product_id>/pricing-selection", methods=["POST"])
@login_required
def submit_pricing_selection(product_id):
    product = Product.query.get_or_404(product_id)
    pin = product.pricing_input
    if pin:
        rwa_id = request.form.get("rwa_option_id", type=int)
        repay_id = request.form.get("repayment_schedule_id", type=int)
        loan_amount = request.form.get("loan_amount", type=float)
        if rwa_id:
            pin.rwa_option_id = rwa_id
        if repay_id:
            pin.repayment_schedule_id = repay_id
        if loan_amount is not None:
            pin.loan_amount = loan_amount
        db.session.commit()
        flash("Pricing selections updated.", "success")
    return redirect(url_for("input.input_dashboard", product_id=product.id))
