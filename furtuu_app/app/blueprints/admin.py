from functools import wraps
import json

from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import (
    Product, ScoreCategory, SubParameter, ScoringOption, PricingInput,
    CostOfFundSource, RWAOption, RepaymentSchedule, OperationalCostComponent, PDGrade,
    NGOSupportItem, NGOSupportTier, ProjectionScenario, ProjectionExtraField,
    EligibilityCriterion, ProductFeature, ProductFeatureCategory, ProductFeatureValue,
)
from app import calculations as calc

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboards.home"))
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Products (value chains) — "New Product Dashboard"
# ---------------------------------------------------------------------------
@admin_bp.route("/products")
@login_required
@admin_required
def products():
    all_products = Product.query.order_by(Product.name).all()
    return render_template("admin/products.html", products=all_products)


@admin_bp.route("/products/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        clone_from_id = request.form.get("clone_from_id", type=int)

        if not name:
            flash("Product name is required.", "danger")
            return redirect(url_for("admin.new_product"))
        if Product.query.filter_by(name=name).first():
            flash("A product with that name already exists.", "danger")
            return redirect(url_for("admin.new_product"))

        product = Product(name=name, description=description)
        db.session.add(product)
        db.session.flush()

        if clone_from_id:
            _clone_product_structure(Product.query.get(clone_from_id), product)
        else:
            _create_blank_product_structure(product)

        db.session.commit()
        flash(f"Product '{name}' created. It now appears in the Input Dashboard dropdown.", "success")
        return redirect(url_for("admin.edit_product", product_id=product.id))

    templates = Product.query.order_by(Product.name).all()
    return render_template("admin/new_product.html", templates=templates)


def _create_blank_product_structure(product):
    """Minimal starter structure for a brand-new value chain."""
    cat = ScoreCategory(product_id=product.id, name="New Category (0%)", display_order=1)
    db.session.add(cat)
    db.session.flush()
    sp = SubParameter(category_id=cat.id, name="New Sub-Parameter", weight=0.0, display_order=1)
    db.session.add(sp)
    db.session.flush()
    opt = ScoringOption(sub_parameter_id=sp.id, label="Strong", score=100, display_order=1)
    db.session.add(opt)

    for i, (label, rwa) in enumerate([("Retail Exposure- meeting NBE criteria", 0.75),
                                       ("Non-Regulatory Retail", 1.0)]):
        db.session.add(RWAOption(product_id=product.id, label=label, rwa_value=rwa, display_order=i))
    rs = RepaymentSchedule(product_id=product.id, label="12 months", tenure_months=12, rate=0.01,
                            display_order=1)
    db.session.add(rs)
    for i, (name, val) in enumerate([("Tech", 0.015), ("Commission", 0.0037), ("Miscellaneous", 0.01)]):
        db.session.add(OperationalCostComponent(product_id=product.id, name=name, value=val,
                                                  display_order=i))
    for i, (name, bal, rate) in enumerate([("Savings Deposit", 1000000.0, 0.07),
                                            ("Fixed Time Deposit", 500000.0, 0.1256)]):
        db.session.add(CostOfFundSource(product_id=product.id, name=name, balance=bal, annual_rate=rate,
                                          display_order=i))
    db.session.flush()
    _seed_pd_grades(product)
    pin = PricingInput(product_id=product.id, rwa_option_id=product.rwa_options[0].id,
                        repayment_schedule_id=rs.id)
    db.session.add(pin)


def _seed_pd_grades(product):
    grade_defs = [
        (1, "Exceptionally Low Risk", "AAA-AA", "100 - 90", 90, 0.05, 0.0005, 0.01, False),
        (2, "Very Low Risk", "A", "89 - 80", 80, 0.10, 0.001, 0.015, False),
        (3, "Low Risk", "BBB+", "79 - 70", 70, 0.25, 0.003, 0.02, False),
        (4, "Moderate Risk", "BBB", "69 - 60", 60, 0.75, 0.01, 0.025, False),
        (5, "Potential Risk", "BB", "59 - 50", 50, 2.0, 0.05, 0.03, False),
        (6, "High Risk", "B+", "49 - 40", 40, 4.5, 0.15, 0.035, False),
        (7, "Very High Risk", "B-", "39 - 30", 30, 8.0, 0.40, 0.04, False),
        (8, "Default", "CCC-D", "< 30", 0, 15.0, 1.0, 0.045, True),
    ]
    for num, iname, sp_band, rng, minscore, midpd, upper, stress, is_def in grade_defs:
        db.session.add(PDGrade(
            product_id=product.id, grade_number=num, grade_label=f"Grade {num}",
            internal_grade_name=iname, sp_band=sp_band, score_range_label=rng,
            min_score=minscore, mid_pd=midpd, upper_bound_pd=upper,
            stress_agri_digital=stress, is_default_grade=is_def,
        ))


def _clone_product_structure(src, product):
    """Deep-copy every editable table from src into the newly created product."""
    cat_map = {}
    for cat in src.categories:
        new_cat = ScoreCategory(product_id=product.id, name=cat.name, display_order=cat.display_order)
        db.session.add(new_cat)
        db.session.flush()
        cat_map[cat.id] = new_cat
        for sp in cat.sub_parameters:
            new_sp = SubParameter(category_id=new_cat.id, name=sp.name, weight=sp.weight,
                                    display_order=sp.display_order)
            db.session.add(new_sp)
            db.session.flush()
            first_opt_id = None
            for opt in sp.options:
                new_opt = ScoringOption(sub_parameter_id=new_sp.id, label=opt.label, score=opt.score,
                                          display_order=opt.display_order)
                db.session.add(new_opt)
                db.session.flush()
                if first_opt_id is None:
                    first_opt_id = new_opt.id
            new_sp.selected_option_id = first_opt_id

    rwa_map = {}
    for r in src.rwa_options:
        nr = RWAOption(product_id=product.id, label=r.label, rwa_value=r.rwa_value,
                        display_order=r.display_order)
        db.session.add(nr)
        db.session.flush()
        rwa_map[r.id] = nr

    repay_map = {}
    for r in src.repayment_schedules:
        nr = RepaymentSchedule(product_id=product.id, label=r.label, tenure_months=r.tenure_months,
                                 rate=r.rate, display_order=r.display_order)
        db.session.add(nr)
        db.session.flush()
        repay_map[r.id] = nr

    for c in src.op_cost_components:
        db.session.add(OperationalCostComponent(product_id=product.id, name=c.name, value=c.value,
                                                   display_order=c.display_order))

    for c in src.cost_of_fund_sources:
        db.session.add(CostOfFundSource(product_id=product.id, name=c.name, balance=c.balance,
                                          annual_rate=c.annual_rate, display_order=c.display_order))

    for g in src.pd_grades:
        db.session.add(PDGrade(
            product_id=product.id, grade_number=g.grade_number, grade_label=g.grade_label,
            internal_grade_name=g.internal_grade_name, sp_band=g.sp_band,
            score_range_label=g.score_range_label, min_score=g.min_score, mid_pd=g.mid_pd,
            upper_bound_pd=g.upper_bound_pd, stress_agri_digital=g.stress_agri_digital,
            is_default_grade=g.is_default_grade,
        ))

    db.session.flush()
    src_pin = src.pricing_input
    if src_pin:
        new_rwa_id = rwa_map.get(src_pin.rwa_option_id).id if src_pin.rwa_option_id in rwa_map else None
        new_repay_id = repay_map.get(src_pin.repayment_schedule_id).id if src_pin.repayment_schedule_id in repay_map else None
        db.session.add(PricingInput(
            product_id=product.id, cost_of_capital=src_pin.cost_of_capital,
            target_return_on_rwa=src_pin.target_return_on_rwa,
            liquidity_premium=src_pin.liquidity_premium, loan_amount=src_pin.loan_amount,
            rwa_option_id=new_rwa_id, loss_given_default=src_pin.loss_given_default,
            exposure_at_default=src_pin.exposure_at_default, repayment_schedule_id=new_repay_id,
            expected_access_fee_pct=src_pin.expected_access_fee_pct,
        ))


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if name:
            existing = Product.query.filter(Product.name == name, Product.id != product.id).first()
            if existing:
                flash("Another product already uses that name.", "danger")
            else:
                product.name = name
                product.description = description
                db.session.commit()
                flash("Product details updated across every dashboard for this sector.", "success")
        return redirect(url_for("admin.edit_product", product_id=product.id))
    return render_template("admin/edit_product.html", product=product)


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Product and all of its data were deleted.", "info")
    return redirect(url_for("admin.products"))


# ---------------------------------------------------------------------------
# Scorecard structure: categories / sub-parameters / scoring options
# ---------------------------------------------------------------------------
@admin_bp.route("/products/<int:product_id>/scorecard-builder")
@login_required
@admin_required
def scorecard_builder(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("admin/scorecard_builder.html", product=product)


@admin_bp.route("/products/<int:product_id>/categories/add", methods=["POST"])
@login_required
@admin_required
def add_category(product_id):
    product = Product.query.get_or_404(product_id)
    name = request.form.get("name", "").strip()
    if name:
        order = len(product.categories) + 1
        db.session.add(ScoreCategory(product_id=product.id, name=name, display_order=order))
        db.session.commit()
        flash(f"Category '{name}' added.", "success")
    return redirect(url_for("admin.scorecard_builder", product_id=product.id))


@admin_bp.route("/categories/<int:cat_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_category(cat_id):
    cat = ScoreCategory.query.get_or_404(cat_id)
    name = request.form.get("name", "").strip()
    if name:
        cat.name = name
        db.session.commit()
        flash("Category updated.", "success")
    return redirect(url_for("admin.scorecard_builder", product_id=cat.product_id))


@admin_bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_category(cat_id):
    cat = ScoreCategory.query.get_or_404(cat_id)
    product_id = cat.product_id
    db.session.delete(cat)
    db.session.commit()
    flash("Category and its sub-parameters deleted.", "info")
    return redirect(url_for("admin.scorecard_builder", product_id=product_id))


@admin_bp.route("/categories/<int:cat_id>/sub-parameters/add", methods=["POST"])
@login_required
@admin_required
def add_sub_parameter(cat_id):
    cat = ScoreCategory.query.get_or_404(cat_id)
    name = request.form.get("name", "").strip()
    weight = request.form.get("weight", type=float) or 0.0
    if name:
        order = len(cat.sub_parameters) + 1
        sp = SubParameter(category_id=cat.id, name=name, weight=weight / 100.0, display_order=order)
        db.session.add(sp)
        db.session.commit()
        flash(f"Sub-parameter '{name}' added.", "success")
    return redirect(url_for("admin.scorecard_builder", product_id=cat.product_id))


@admin_bp.route("/sub-parameters/<int:sp_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_sub_parameter(sp_id):
    sp = SubParameter.query.get_or_404(sp_id)
    name = request.form.get("name", "").strip()
    weight = request.form.get("weight", type=float)
    new_category_id = request.form.get("category_id", type=int)
    if name:
        sp.name = name
    if weight is not None:
        sp.weight = weight / 100.0
    if new_category_id and new_category_id != sp.category_id:
        # Reassign to a different category — must stay within the same product.
        target_cat = ScoreCategory.query.get(new_category_id)
        if target_cat and target_cat.product_id == sp.category.product_id:
            sp.category_id = new_category_id
    db.session.commit()
    flash("Sub-parameter updated.", "success")
    return redirect(url_for("admin.scorecard_builder", product_id=sp.category.product_id))


@admin_bp.route("/sub-parameters/<int:sp_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_sub_parameter(sp_id):
    sp = SubParameter.query.get_or_404(sp_id)
    product_id = sp.category.product_id
    db.session.delete(sp)
    db.session.commit()
    flash("Sub-parameter deleted.", "info")
    return redirect(url_for("admin.scorecard_builder", product_id=product_id))


@admin_bp.route("/sub-parameters/<int:sp_id>/options/add", methods=["POST"])
@login_required
@admin_required
def add_scoring_option(sp_id):
    sp = SubParameter.query.get_or_404(sp_id)
    label = request.form.get("label", "").strip()
    score = request.form.get("score", type=float)
    if label and score is not None:
        order = len(sp.options) + 1
        db.session.add(ScoringOption(sub_parameter_id=sp.id, label=label, score=score,
                                       display_order=order))
        db.session.commit()
        flash(f"Scoring attribute '{label}' added.", "success")
    return redirect(url_for("admin.scorecard_builder", product_id=sp.category.product_id))


@admin_bp.route("/sub-parameters/<int:sp_id>/options/save-all", methods=["POST"])
@login_required
@admin_required
def edit_scoring_options_bulk(sp_id):
    sp = SubParameter.query.get_or_404(sp_id)
    for opt in sp.options:
        label = request.form.get(f"label_{opt.id}", "").strip()
        score = request.form.get(f"score_{opt.id}", type=float)
        if label:
            opt.label = label
        if score is not None:
            opt.score = score
    db.session.commit()
    flash("Scoring attributes updated.", "success")
    return redirect(url_for("admin.scorecard_builder", product_id=sp.category.product_id))

@admin_bp.route("/options/<int:opt_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_scoring_option(opt_id):
    opt = ScoringOption.query.get_or_404(opt_id)
    product_id = opt.sub_parameter.category.product_id
    sp = opt.sub_parameter
    if sp.selected_option_id == opt.id:
        sp.selected_option_id = None
    db.session.delete(opt)
    db.session.commit()
    flash("Scoring attribute deleted.", "info")
    return redirect(url_for("admin.scorecard_builder", product_id=product_id))


# ---------------------------------------------------------------------------
# Pricing inputs
# ---------------------------------------------------------------------------
@admin_bp.route("/products/<int:product_id>/pricing-inputs", methods=["GET", "POST"])
@login_required
@admin_required
def pricing_inputs(product_id):
    product = Product.query.get_or_404(product_id)
    pin = product.pricing_input
    if request.method == "POST":
        if pin is None:
            pin = PricingInput(product_id=product.id)
            db.session.add(pin)
        pin.cost_of_capital = (request.form.get("cost_of_capital", type=float) or 0) / 100.0
        pin.target_return_on_rwa = (request.form.get("target_return_on_rwa", type=float) or 0) / 100.0
        pin.liquidity_premium = (request.form.get("liquidity_premium", type=float) or 0) / 100.0
        pin.loan_amount = request.form.get("loan_amount", type=float) or 0
        pin.rwa_option_id = request.form.get("rwa_option_id", type=int)
        pin.loss_given_default = (request.form.get("loss_given_default", type=float) or 0) / 100.0
        pin.exposure_at_default = (request.form.get("exposure_at_default", type=float) or 0) / 100.0
        pin.repayment_schedule_id = request.form.get("repayment_schedule_id", type=int)
        pin.expected_access_fee_pct = (request.form.get("expected_access_fee_pct", type=float) or 0) / 100.0
        db.session.commit()
        flash("Pricing inputs updated.", "success")
        return redirect(url_for("admin.pricing_inputs", product_id=product.id))
    return render_template("admin/pricing_inputs.html", product=product, pin=pin)



@admin_bp.route("/products/<int:product_id>/debug-pricing")
@login_required
@admin_required
def debug_pricing(product_id):
    product = Product.query.get_or_404(product_id)
    pin = product.pricing_input
    data = {
        "product_id": product.id,
        "product_name": product.name,
        "has_pricing_input": pin is not None,
    }
    if pin:
        data.update({
            "pricing_input_id": pin.id,
            "pricing_input_product_id": pin.product_id,
            "cost_of_capital": pin.cost_of_capital,
            "target_return_on_rwa": pin.target_return_on_rwa,
            "loan_amount": pin.loan_amount,
            "rwa_option_id": pin.rwa_option_id,
            "repayment_schedule_id": pin.repayment_schedule_id,
            "loss_given_default": pin.loss_given_default,
            "exposure_at_default": pin.exposure_at_default,
        })
    try:
        from app import calculations as calc
        result = calc.compute_pricing(product)
        data["compute_pricing_result"] = "SUCCESS" if result is not None else "RETURNED NONE"
    except Exception as e:
        data["compute_pricing_result"] = f"EXCEPTION: {type(e).__name__}: {e}"

    import inspect
    from app import calculations as calc
    data["compute_pricing_source"] = inspect.getsource(calc.compute_pricing)

    from app.models import PricingInput
    fresh_pin = PricingInput.query.filter_by(product_id=product.id).first()
    data["fresh_query_pricing_input_found"] = fresh_pin is not None

    pin_again = product.pricing_input
    data["pricing_input_second_access"] = pin_again is not None

    return jsonify(data)

# ---------------------------------------------------------------------------
# Cost of Fund sources
# ---------------------------------------------------------------------------
@admin_bp.route("/products/<int:product_id>/cost-of-fund", methods=["GET", "POST"])
@login_required
@admin_required
def cost_of_fund_admin(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        balance = request.form.get("balance", type=float) or 0
        rate = (request.form.get("annual_rate", type=float) or 0) / 100.0
        if name:
            order = len(product.cost_of_fund_sources) + 1
            db.session.add(CostOfFundSource(product_id=product.id, name=name, balance=balance,
                                              annual_rate=rate, display_order=order))
            db.session.commit()
            flash(f"Funding source '{name}' added.", "success")
        return redirect(url_for("admin.cost_of_fund_admin", product_id=product.id))
    return render_template("admin/cost_of_fund.html", product=product)


@admin_bp.route("/cost-of-fund/<int:src_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_cost_of_fund_source(src_id):
    src = CostOfFundSource.query.get_or_404(src_id)
    name = request.form.get("name", "").strip()
    balance = request.form.get("balance", type=float)
    rate = request.form.get("annual_rate", type=float)
    if name:
        src.name = name
    if balance is not None:
        src.balance = balance
    if rate is not None:
        src.annual_rate = rate / 100.0
    db.session.commit()
    flash("Funding source updated.", "success")
    return redirect(url_for("admin.cost_of_fund_admin", product_id=src.product_id))


@admin_bp.route("/cost-of-fund/<int:src_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_cost_of_fund_source(src_id):
    src = CostOfFundSource.query.get_or_404(src_id)
    product_id = src.product_id
    db.session.delete(src)
    db.session.commit()
    flash("Funding source deleted.", "info")
    return redirect(url_for("admin.cost_of_fund_admin", product_id=product_id))


# ---------------------------------------------------------------------------
# Reference tables: RWA options, repayment schedules, operational cost
# ---------------------------------------------------------------------------
@admin_bp.route("/products/<int:product_id>/reference", methods=["GET"])
@login_required
@admin_required
def reference_admin(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("admin/reference.html", product=product)


@admin_bp.route("/products/<int:product_id>/rwa-options/add", methods=["POST"])
@login_required
@admin_required
def add_rwa_option(product_id):
    product = Product.query.get_or_404(product_id)
    label = request.form.get("label", "").strip()
    value = request.form.get("rwa_value", type=float)
    if label and value is not None:
        db.session.add(RWAOption(product_id=product.id, label=label, rwa_value=value / 100.0,
                                   display_order=len(product.rwa_options) + 1))
        db.session.commit()
        flash("RWA option added.", "success")
    return redirect(url_for("admin.reference_admin", product_id=product.id))


@admin_bp.route("/rwa-options/<int:rwa_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_rwa_option(rwa_id):
    r = RWAOption.query.get_or_404(rwa_id)
    label = request.form.get("label", "").strip()
    value = request.form.get("rwa_value", type=float)
    if label:
        r.label = label
    if value is not None:
        r.rwa_value = value / 100.0
    db.session.commit()
    flash("RWA option updated.", "success")
    return redirect(url_for("admin.reference_admin", product_id=r.product_id))


@admin_bp.route("/rwa-options/<int:rwa_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_rwa_option(rwa_id):
    r = RWAOption.query.get_or_404(rwa_id)
    product_id = r.product_id
    db.session.delete(r)
    db.session.commit()
    flash("RWA option deleted.", "info")
    return redirect(url_for("admin.reference_admin", product_id=product_id))


@admin_bp.route("/products/<int:product_id>/repayment-schedules/add", methods=["POST"])
@login_required
@admin_required
def add_repayment_schedule(product_id):
    product = Product.query.get_or_404(product_id)
    label = request.form.get("label", "").strip()
    months = request.form.get("tenure_months", type=float)
    rate = request.form.get("rate", type=float)
    if label and months is not None and rate is not None:
        db.session.add(RepaymentSchedule(product_id=product.id, label=label, tenure_months=months,
                                           rate=rate / 100.0, display_order=len(product.repayment_schedules) + 1))
        db.session.commit()
        flash("Repayment schedule added.", "success")
    return redirect(url_for("admin.reference_admin", product_id=product.id))


@admin_bp.route("/repayment-schedules/<int:rs_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_repayment_schedule(rs_id):
    rs = RepaymentSchedule.query.get_or_404(rs_id)
    label = request.form.get("label", "").strip()
    months = request.form.get("tenure_months", type=float)
    rate = request.form.get("rate", type=float)
    if label:
        rs.label = label
    if months is not None:
        rs.tenure_months = months
    if rate is not None:
        rs.rate = rate / 100.0
    db.session.commit()
    flash("Repayment schedule updated.", "success")
    return redirect(url_for("admin.reference_admin", product_id=rs.product_id))


@admin_bp.route("/repayment-schedules/<int:rs_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_repayment_schedule(rs_id):
    rs = RepaymentSchedule.query.get_or_404(rs_id)
    product_id = rs.product_id

    pin = rs.product.pricing_input if rs.product else None
    if pin and pin.repayment_schedule_id == rs.id:
        pin.repayment_schedule_id = None

    db.session.delete(rs)
    db.session.commit()
    flash("Repayment schedule deleted.", "info")
    return redirect(url_for("admin.reference_admin", product_id=product_id))


@admin_bp.route("/products/<int:product_id>/op-cost/add", methods=["POST"])
@login_required
@admin_required
def add_op_cost_component(product_id):
    product = Product.query.get_or_404(product_id)
    name = request.form.get("name", "").strip()
    value = request.form.get("value", type=float)
    if name and value is not None:
        db.session.add(OperationalCostComponent(product_id=product.id, name=name, value=value / 100.0,
                                                   display_order=len(product.op_cost_components) + 1))
        db.session.commit()
        flash("Operational cost component added.", "success")
    return redirect(url_for("admin.reference_admin", product_id=product.id))


@admin_bp.route("/op-cost/<int:oc_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_op_cost_component(oc_id):
    oc = OperationalCostComponent.query.get_or_404(oc_id)
    name = request.form.get("name", "").strip()
    value = request.form.get("value", type=float)
    if name:
        oc.name = name
    if value is not None:
        oc.value = value / 100.0
    db.session.commit()
    flash("Operational cost component updated.", "success")
    return redirect(url_for("admin.reference_admin", product_id=oc.product_id))


@admin_bp.route("/op-cost/<int:oc_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_op_cost_component(oc_id):
    oc = OperationalCostComponent.query.get_or_404(oc_id)
    product_id = oc.product_id
    db.session.delete(oc)
    db.session.commit()
    flash("Operational cost component deleted.", "info")
    return redirect(url_for("admin.reference_admin", product_id=product_id))


# ---------------------------------------------------------------------------
# PD Grades
# ---------------------------------------------------------------------------
@admin_bp.route("/products/<int:product_id>/pd-grades", methods=["GET"])
@login_required
@admin_required
def pd_grades_admin(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("admin/pd_grades.html", product=product)


@admin_bp.route("/products/<int:product_id>/ngo-support", methods=["GET"])
@login_required
@admin_required
def ngo_support_admin(product_id):
    from app.calculations import compute_ngo_support
    product = Product.query.get_or_404(product_id)
    result = compute_ngo_support(product)
    return render_template("admin/ngo_support.html", product=product, result=result)


@admin_bp.route("/products/<int:product_id>/ngo-support/save-cap", methods=["POST"])
@login_required
@admin_required
def save_ngo_cap(product_id):
    product = Product.query.get_or_404(product_id)
    pin = product.pricing_input
    if pin is None:
        pin = PricingInput(product_id=product.id)
        db.session.add(pin)
    pin.ngo_max_price_impact_pct = (request.form.get("ngo_max_price_impact_pct", type=float) or 0) / 100.0
    db.session.commit()
    flash("NGO cap updated.", "success")
    return redirect(url_for("admin.ngo_support_admin", product_id=product.id))


@admin_bp.route("/ngo-items/<int:item_id>/tiers/add", methods=["POST"])
@login_required
@admin_required
def add_ngo_tier(item_id):
    item = NGOSupportItem.query.get_or_404(item_id)
    label = request.form.get("label", "").strip()
    rate_reduction = request.form.get("rate_reduction", type=float)
    if label and rate_reduction is not None:
        order = len(item.tiers) + 1
        db.session.add(NGOSupportTier(item_id=item.id, label=label,
                                        rate_reduction=rate_reduction / 100.0,
                                        display_order=order))
        db.session.commit()
        flash(f"Range '{label}' added to {item.name}.", "success")
    return redirect(url_for("admin.ngo_support_admin", product_id=item.product_id))


@admin_bp.route("/ngo-tiers/<int:tier_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_ngo_tier(tier_id):
    tier = NGOSupportTier.query.get_or_404(tier_id)
    item = NGOSupportItem.query.get_or_404(tier.item_id)
    label = request.form.get("label", "").strip()
    rate_reduction = request.form.get("rate_reduction", type=float)
    if label:
        tier.label = label
    if rate_reduction is not None:
        tier.rate_reduction = rate_reduction / 100.0
    db.session.commit()
    flash("Range updated.", "success")
    return redirect(url_for("admin.ngo_support_admin", product_id=item.product_id))


@admin_bp.route("/ngo-tiers/<int:tier_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_ngo_tier(tier_id):
    tier = NGOSupportTier.query.get_or_404(tier_id)
    item = NGOSupportItem.query.get_or_404(tier.item_id)
    product_id = item.product_id
    if item.selected_tier_id == tier.id:
        item.selected_tier_id = None
    db.session.delete(tier)
    db.session.commit()
    flash("Range deleted.", "info")
    return redirect(url_for("admin.ngo_support_admin", product_id=product_id))


@admin_bp.route("/pd-grades/<int:grade_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_pd_grade(grade_id):
    g = PDGrade.query.get_or_404(grade_id)
    g.grade_label = request.form.get("grade_label", g.grade_label).strip()
    g.internal_grade_name = request.form.get("internal_grade_name", "").strip()
    g.sp_band = request.form.get("sp_band", "").strip()
    g.score_range_label = request.form.get("score_range_label", "").strip()
    min_score = request.form.get("min_score", type=float)
    mid_pd = request.form.get("mid_pd", type=float)
    upper = request.form.get("upper_bound_pd", type=float)
    stress = request.form.get("stress_agri_digital", type=float)
    if min_score is not None:
        g.min_score = min_score
    if mid_pd is not None:
        g.mid_pd = mid_pd
    if upper is not None:
        g.upper_bound_pd = upper / 100.0
    if stress is not None:
        g.stress_agri_digital = stress / 100.0
    g.is_default_grade = bool(request.form.get("is_default_grade"))
    db.session.commit()
    flash("PD grade updated.", "success")
    return redirect(url_for("admin.pd_grades_admin", product_id=g.product_id))


# ---------------------------------------------------------------------------
# Projection (per-crop / per-segment profitability projection)
# ---------------------------------------------------------------------------
_PROJECTION_PCT_FIELDS = [
    "monthly_interest_rate", "annual_cost_of_fund_pct", "cost_of_lmd_pct",
    "misc_cost_pct", "access_fee_pct", "rms_fee_pct", "disaster_risk_pct",
    "income_tax_pct", "provision_pct", "provision_status_pct",
]
_PROJECTION_NUM_FIELDS = ["number_of_farmers", "ticket_size", "loan_tenure_months"]


@admin_bp.route("/products/projection/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_projection():
    products = Product.query.order_by(Product.name).all()

    if request.method == "POST":
        product_id = request.form.get("product_id", type=int)
        crop_name = request.form.get("crop_name", "").strip()
        year_label = request.form.get("year_label", "Y1").strip() or "Y1"

        product = Product.query.get(product_id)
        if not product:
            flash("Please choose a valid product.", "danger")
            return redirect(url_for("admin.new_projection"))
        if not crop_name:
            flash("Crop / segment name is required.", "danger")
            return redirect(url_for("admin.new_projection"))

        sc = ProjectionScenario(
            product_id=product.id,
            crop_name=crop_name,
            year_label=year_label,
            display_order=len(product.projection_scenarios) + 1,
        )
        
        db.session.add(sc)
        db.session.commit()
        flash(f"Projection '{crop_name}' created.", "success")
        return redirect(url_for("admin.projection_admin", product_id=product.id))

    return render_template("admin/new_projection.html", products=products)


@admin_bp.route("/products/<int:product_id>/projection")
@login_required
@admin_required
def projection_admin(product_id):
    product = Product.query.get_or_404(product_id)
    result = calc.compute_projection_summary(product)
    return render_template("admin/projection.html", product=product, result=result)



def _parse_extra_fields(form):
    labels = form.getlist("extra_field_label[]")
    values = form.getlist("extra_field_value[]")
    return json.dumps([
        {"label": l.strip(), "value": v.strip()}
        for l, v in zip(labels, values) if l.strip()
    ])
@admin_bp.route("/products/<int:product_id>/projection/add", methods=["POST"])
@login_required
@admin_required
def add_projection(product_id):
    product = Product.query.get_or_404(product_id)
    crop_name = request.form.get("crop_name", "").strip()
    if not crop_name:
        flash("Crop / segment name is required.", "danger")
        return redirect(url_for("admin.projection_admin", product_id=product_id))

    sc = ProjectionScenario(
        product_id=product.id,
        crop_name=crop_name,
        year_label=(request.form.get("year_label", "Y1").strip() or "Y1"),
        display_order=len(product.projection_scenarios) + 1,
    )
    for field in _PROJECTION_NUM_FIELDS:
        val = request.form.get(field, type=float)
        if val is not None:
            setattr(sc, field, val)
    for field in _PROJECTION_PCT_FIELDS:
        val = request.form.get(field, type=float)
        if val is not None:
            setattr(sc, field, val / 100.0)
    db.session.add(sc)
    db.session.commit()
    flash(f"Projection '{crop_name}' added.", "success")
    return redirect(url_for("admin.projection_admin", product_id=product_id))


@admin_bp.route("/projection/<int:scenario_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_projection(scenario_id):
    sc = ProjectionScenario.query.get_or_404(scenario_id)
    crop_name = request.form.get("crop_name", "").strip()
    if crop_name:
        sc.crop_name = crop_name
    year_label = request.form.get("year_label", "").strip()
    if year_label:
        sc.year_label = year_label
    for field in _PROJECTION_NUM_FIELDS:
        val = request.form.get(field, type=float)
        if val is not None:
            setattr(sc, field, val)
    for field in _PROJECTION_PCT_FIELDS:
        val = request.form.get(field, type=float)
        if val is not None:
            setattr(sc, field, val / 100.0)
    db.session.commit()
    flash(f"Projection '{sc.crop_name}' updated.", "success")
    return redirect(url_for("admin.projection_admin", product_id=sc.product_id))


@admin_bp.route("/projection/<int:scenario_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_projection(scenario_id):
    sc = ProjectionScenario.query.get_or_404(scenario_id)
    product_id = sc.product_id
    name = sc.crop_name
    db.session.delete(sc)
    db.session.commit()
    flash(f"Projection '{name}' deleted.", "success")
    return redirect(url_for("admin.projection_admin", product_id=product_id))


@admin_bp.route("/projection/<int:scenario_id>/extra-field/add", methods=["POST"])
@login_required
@admin_required
def add_projection_extra_field(scenario_id):
    sc = ProjectionScenario.query.get_or_404(scenario_id)
    field_name = request.form.get("field_name", "").strip()
    field_value = request.form.get("field_value", type=float)
    if not field_name:
        flash("Field name is required.", "danger")
        return redirect(url_for("admin.projection_admin", product_id=sc.product_id))

    ef = ProjectionExtraField(
        scenario_id=sc.id,
        field_name=field_name,
        field_value=field_value if field_value is not None else 0.0,
        display_order=len(sc.extra_fields) + 1,
    )
    db.session.add(ef)
    db.session.commit()
    flash(f"Field '{field_name}' added to {sc.crop_name}.", "success")
    return redirect(url_for("admin.projection_admin", product_id=sc.product_id))


@admin_bp.route("/projection/extra-field/<int:field_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_projection_extra_field(field_id):
    ef = ProjectionExtraField.query.get_or_404(field_id)
    field_name = request.form.get("field_name", "").strip()
    field_value = request.form.get("field_value", type=float)
    if field_name:
        ef.field_name = field_name
    if field_value is not None:
        ef.field_value = field_value
    db.session.commit()
    flash(f"Field '{ef.field_name}' updated.", "success")
    return redirect(url_for("admin.projection_admin", product_id=ef.scenario.product_id))


@admin_bp.route("/projection/extra-field/<int:field_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_projection_extra_field(field_id):
    ef = ProjectionExtraField.query.get_or_404(field_id)
    product_id = ef.scenario.product_id
    name = ef.field_name
    db.session.delete(ef)
    db.session.commit()
    flash(f"Field '{name}' removed.", "info")
    return redirect(url_for("admin.projection_admin", product_id=product_id))




@admin_bp.route("/products/eligibility/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_eligibility():
    products = Product.query.order_by(Product.name).all()

    if request.method == "POST":
        product_id = request.form.get("product_id", type=int)
        clone_from_id = request.form.get("clone_from_id", type=int)

        product = Product.query.get(product_id)
        if not product:
            flash("Please choose a valid product.", "danger")
            return redirect(url_for("admin.new_eligibility"))

        if clone_from_id:
            source = Product.query.get(clone_from_id)
            if not source or source.id == product.id:
                flash("Please choose a valid product to clone from.", "danger")
                return redirect(url_for("admin.new_eligibility"))
            _clone_eligibility_structure(source, product)
            db.session.commit()
            flash(f"Cloned eligibility & product features from '{source.name}' into '{product.name}'.", "success")
            return redirect(url_for("admin.eligibility_admin", product_id=product.id))

        criterion = request.form.get("criterion", "").strip()
        requirement = request.form.get("requirement", "").strip()
        if not criterion or not requirement:
            flash("Criterion and requirement are both required.", "danger")
            return redirect(url_for("admin.new_eligibility"))

        db.session.add(EligibilityCriterion(
            product_id=product.id, criterion=criterion, requirement=requirement,
            is_mandatory=bool(request.form.get("is_mandatory")),
            display_order=len(product.eligibility_criteria) + 1,
        ))
        db.session.commit()
        flash(f"Eligibility criterion '{criterion}' created.", "success")
        return redirect(url_for("admin.eligibility_admin", product_id=product.id))

    return render_template("admin/new_eligibility.html", products=products)

# ---------------------------------------------------------------------------
# Eligibility (criteria) + Product Features
# ---------------------------------------------------------------------------
@admin_bp.route("/products/<int:product_id>/eligibility")
@login_required
@admin_required
def eligibility_admin(product_id):
    product = Product.query.get_or_404(product_id)
    other_products = Product.query.filter(Product.id != product_id).order_by(Product.name).all()
    return render_template("admin/eligibility.html", product=product, other_products=other_products)


def _clone_eligibility_structure(source, product):
    """Deep-copy eligibility criteria + feature categories/features/values from source into product."""
    for c in source.eligibility_criteria:
        db.session.add(EligibilityCriterion(
            product_id=product.id,
            criterion=c.criterion,
            requirement=c.requirement,
            is_mandatory=c.is_mandatory,
            display_order=c.display_order,
        ))

    for cat in source.feature_categories:
        new_cat = ProductFeatureCategory(
            product_id=product.id, name=cat.name, display_order=cat.display_order,
        )
        db.session.add(new_cat)
        db.session.flush()  # assign new_cat.id

        for f in cat.features:
            new_f = ProductFeature(
                product_id=product.id, category_id=new_cat.id,
                feature=f.feature, value=f.value, display_order=f.display_order,
            )
            db.session.add(new_f)
            db.session.flush()
            for v in f.values:
                db.session.add(ProductFeatureValue(
                    feature_id=new_f.id, value=v.value, display_order=v.display_order,
                ))

    for f in source.product_features:
        if f.category_id is None:
            new_f = ProductFeature(
                product_id=product.id, category_id=None,
                feature=f.feature, value=f.value, display_order=f.display_order,
            )
            db.session.add(new_f)
            db.session.flush()
            for v in f.values:
                db.session.add(ProductFeatureValue(
                    feature_id=new_f.id, value=v.value, display_order=v.display_order,
                ))


@admin_bp.route("/products/<int:product_id>/eligibility/clone", methods=["POST"])
@login_required
@admin_required
def clone_eligibility(product_id):
    product = Product.query.get_or_404(product_id)
    source_id = request.form.get("source_product_id", type=int)
    source = Product.query.get(source_id)

    if not source or source.id == product.id:
        flash("Please choose a valid product to clone from.", "danger")
        return redirect(url_for("admin.eligibility_admin", product_id=product.id))

    _clone_eligibility_structure(source, product)
    db.session.commit()
    flash(f"Cloned eligibility & product features from '{source.name}' into '{product.name}'.", "success")
    return redirect(url_for("admin.eligibility_admin", product_id=product.id))


@admin_bp.route("/products/<int:product_id>/eligibility/add", methods=["POST"])
@login_required
@admin_required
def add_eligibility(product_id):
    product = Product.query.get_or_404(product_id)
    criterion = request.form.get("criterion", "").strip()
    requirement = request.form.get("requirement", "").strip()
    if criterion:
        db.session.add(EligibilityCriterion(
            product_id=product.id, criterion=criterion, requirement=requirement,
            is_mandatory=bool(request.form.get("is_mandatory")),
            display_order=len(product.eligibility_criteria) + 1,
        ))
        db.session.commit()
        flash(f"Eligibility criterion '{criterion}' added.", "success")
    else:
        flash("Criterion name is required.", "danger")
    return redirect(url_for("admin.eligibility_admin", product_id=product_id))


@admin_bp.route("/eligibility/<int:criterion_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_eligibility(criterion_id):
    c = EligibilityCriterion.query.get_or_404(criterion_id)
    criterion = request.form.get("criterion", "").strip()
    requirement = request.form.get("requirement", "").strip()
    if criterion:
        c.criterion = criterion
    if requirement:
        c.requirement = requirement
    c.is_mandatory = bool(request.form.get("is_mandatory"))
    db.session.commit()
    flash("Eligibility criterion updated.", "success")
    return redirect(url_for("admin.eligibility_admin", product_id=c.product_id))



@admin_bp.route("/products/<int:product_id>/eligibility/reorder", methods=["POST"])
@login_required
@admin_required
def reorder_eligibility(product_id):
    data = request.get_json(silent=True) or {}
    ordered_ids = data.get("order", [])
    for index, criterion_id in enumerate(ordered_ids):
        c = EligibilityCriterion.query.get(criterion_id)
        if c and c.product_id == product_id:
            c.display_order = index
    db.session.commit()
    return jsonify({"status": "ok"})


@admin_bp.route("/products/<int:product_id>/feature-categories/reorder", methods=["POST"])
@login_required
@admin_required
def reorder_feature_categories(product_id):
    data = request.get_json(silent=True) or {}
    ordered_ids = data.get("order", [])
    for index, cat_id in enumerate(ordered_ids):
        c = ProductFeatureCategory.query.get(cat_id)
        if c and c.product_id == product_id:
            c.display_order = index
    db.session.commit()
    return jsonify({"status": "ok"})


@admin_bp.route("/feature-categories/<int:category_id>/features/reorder", methods=["POST"])
@login_required
@admin_required
def reorder_features(category_id):
    data = request.get_json(silent=True) or {}
    ordered_ids = data.get("order", [])
    for index, feature_id in enumerate(ordered_ids):
        f = ProductFeature.query.get(feature_id)
        if f and f.category_id == category_id:
            f.display_order = index
    db.session.commit()
    return jsonify({"status": "ok"})


@admin_bp.route("/eligibility/<int:criterion_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_eligibility(criterion_id):
    c = EligibilityCriterion.query.get_or_404(criterion_id)
    product_id = c.product_id
    db.session.delete(c)
    db.session.commit()
    flash("Eligibility criterion deleted.", "info")
    return redirect(url_for("admin.eligibility_admin", product_id=product_id))


@admin_bp.route("/products/<int:product_id>/feature-categories/add", methods=["POST"])
@login_required
@admin_required
def add_feature_category(product_id):
    product = Product.query.get_or_404(product_id)
    name = request.form.get("name", "").strip()
    if name:
        db.session.add(ProductFeatureCategory(
            product_id=product.id, name=name,
            display_order=len(product.feature_categories) + 1,
        ))
        db.session.commit()
        flash(f"Category '{name}' added.", "success")
    return redirect(url_for("admin.eligibility_admin", product_id=product_id))


@admin_bp.route("/feature-categories/<int:category_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_feature_category(category_id):
    c = ProductFeatureCategory.query.get_or_404(category_id)
    name = request.form.get("name", "").strip()
    if name:
        c.name = name
        db.session.commit()
        flash("Category updated.", "success")
    return redirect(url_for("admin.eligibility_admin", product_id=c.product_id))


@admin_bp.route("/feature-categories/<int:category_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_feature_category(category_id):
    c = ProductFeatureCategory.query.get_or_404(category_id)
    product_id = c.product_id
    db.session.delete(c)
    db.session.commit()
    flash("Category and its features deleted.", "info")
    return redirect(url_for("admin.eligibility_admin", product_id=product_id))


@admin_bp.route("/products/<int:product_id>/features/add", methods=["POST"])
@login_required
@admin_required
def add_feature(product_id):
    product = Product.query.get_or_404(product_id)
    feature = request.form.get("feature", "").strip()
    category_id = request.form.get("category_id", "").strip()
    if feature:
        db.session.add(ProductFeature(
            product_id=product.id, feature=feature, value="",
            category_id=int(category_id) if category_id else None,
            display_order=len(product.product_features) + 1,
        ))
        db.session.commit()
        flash(f"Feature '{feature}' added.", "success")
    return redirect(url_for("admin.eligibility_admin", product_id=product_id))


@admin_bp.route("/features/<int:feature_id>/values/add", methods=["POST"])
@login_required
@admin_required
def add_feature_value(feature_id):
    f = ProductFeature.query.get_or_404(feature_id)
    value = request.form.get("value", "").strip()
    if value:
        db.session.add(ProductFeatureValue(
            feature_id=f.id, value=value,
            display_order=len(f.values) + 1,
        ))
        db.session.commit()
    return redirect(url_for("admin.eligibility_admin", product_id=f.product_id))


@admin_bp.route("/feature-values/<int:value_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_feature_value(value_id):
    v = ProductFeatureValue.query.get_or_404(value_id)
    value = request.form.get("value", "").strip()
    if value:
        v.value = value
        db.session.commit()
    return redirect(url_for("admin.eligibility_admin", product_id=v.feature.product_id))


@admin_bp.route("/features/<int:feature_id>/values/save-all", methods=["POST"])
@login_required
@admin_required
def edit_feature_values_bulk(feature_id):
    f = ProductFeature.query.get_or_404(feature_id)
    for v in f.values:
        value = request.form.get(f"value_{v.id}", "").strip()
        if value:
            v.value = value
    db.session.commit()
    flash("Values updated.", "success")
    return redirect(url_for("admin.eligibility_admin", product_id=f.product_id))


@admin_bp.route("/feature-values/<int:value_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_feature_value(value_id):
    v = ProductFeatureValue.query.get_or_404(value_id)
    f = v.feature
    product_id = f.product_id
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for("admin.eligibility_admin", product_id=product_id))


@admin_bp.route("/features/<int:feature_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_feature(feature_id):
    f = ProductFeature.query.get_or_404(feature_id)
    feature = request.form.get("feature", "").strip()
    value = request.form.get("value", "").strip()
    if feature:
        f.feature = feature
    f.value = value
    db.session.commit()
    flash("Feature updated.", "success")
    return redirect(url_for("admin.eligibility_admin", product_id=f.product_id))


@admin_bp.route("/features/<int:feature_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_feature(feature_id):
    f = ProductFeature.query.get_or_404(feature_id)
    product_id = f.product_id
    db.session.delete(f)
    db.session.commit()
    flash("Feature deleted.", "info")
    return redirect(url_for("admin.eligibility_admin", product_id=product_id))