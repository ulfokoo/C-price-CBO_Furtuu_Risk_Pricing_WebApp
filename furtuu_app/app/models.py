from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")  # 'admin' or 'user'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


# ---------------------------------------------------------------------------
# Product / Value-chain
# ---------------------------------------------------------------------------
class Product(db.Model):
    """A loan product / value chain (Furtuu, Horticulture, Dairy, ...).

    Every editable table in the workbook is scoped to a product_id so that
    editing one product's variables never changes another product's data.
    """
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    categories = db.relationship("ScoreCategory", backref="product", cascade="all, delete-orphan",
                                  order_by="ScoreCategory.display_order")
    pricing_input = db.relationship("PricingInput", backref="product", uselist=False,
                                     cascade="all, delete-orphan")
    cost_of_fund_sources = db.relationship("CostOfFundSource", backref="product",
                                            cascade="all, delete-orphan",
                                            order_by="CostOfFundSource.display_order")
    rwa_options = db.relationship("RWAOption", backref="product", cascade="all, delete-orphan",
                                   order_by="RWAOption.display_order")
    repayment_schedules = db.relationship("RepaymentSchedule", backref="product",
                                           cascade="all, delete-orphan",
                                           order_by="RepaymentSchedule.display_order")
    op_cost_components = db.relationship("OperationalCostComponent", backref="product",
                                          cascade="all, delete-orphan",
                                          order_by="OperationalCostComponent.display_order")
    pd_grades = db.relationship("PDGrade", backref="product", cascade="all, delete-orphan",
                                 order_by="PDGrade.grade_number")
    ngo_support_items = db.relationship("NGOSupportItem", backref="product",
                                         cascade="all, delete-orphan",
                                         order_by="NGOSupportItem.display_order")
    projection_scenarios = db.relationship("ProjectionScenario", backref="product",
                                            cascade="all, delete-orphan",
                                            order_by="ProjectionScenario.display_order")
    eligibility_criteria = db.relationship("EligibilityCriterion", backref="product",
                                            cascade="all, delete-orphan",
                                            order_by="EligibilityCriterion.display_order")
    product_features = db.relationship("ProductFeature", backref="product",
                                        cascade="all, delete-orphan",
                                        order_by="ProductFeature.display_order")

    def total_category_weight(self):
        return sum(c.weight_pct() for c in self.categories)


class ScoreCategory(db.Model):
    """A main category on the scorecard sheet, e.g. 'Market & Commercial Risk (10%)'."""
    __tablename__ = "score_categories"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    display_order = db.Column(db.Integer, default=0)

    sub_parameters = db.relationship("SubParameter", backref="category", cascade="all, delete-orphan",
                                      order_by="SubParameter.display_order")

    def weight_pct(self):
        return sum(sp.weight for sp in self.sub_parameters)


class SubParameter(db.Model):
    """A row like 'Rainfall Outlook' with its weight and current selection."""
    __tablename__ = "sub_parameters"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("score_categories.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    weight = db.Column(db.Float, nullable=False, default=0.0)  # fraction e.g. 0.08 = 8%
    display_order = db.Column(db.Integer, default=0)
    # The currently selected scoring option (mirrors the Excel "Assessment Result" cell)
    selected_option_id = db.Column(db.Integer, db.ForeignKey("scoring_options.id"), nullable=True)

    options = db.relationship("ScoringOption", backref="sub_parameter",
                               cascade="all, delete-orphan",
                               order_by="ScoringOption.display_order",
                               foreign_keys="ScoringOption.sub_parameter_id")
    selected_option = db.relationship("ScoringOption", foreign_keys=[selected_option_id],
                                       post_update=True)

    def score(self):
        return self.selected_option.score if self.selected_option else 0

    def weighted_score(self):
        return self.score() * self.weight


class ScoringOption(db.Model):
    """A possible attribute value + its score, e.g. 'Favorable / Strong' -> 100."""
    __tablename__ = "scoring_options"

    id = db.Column(db.Integer, primary_key=True)
    sub_parameter_id = db.Column(db.Integer, db.ForeignKey("sub_parameters.id"), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    score = db.Column(db.Float, nullable=False, default=0.0)  # 0-100
    display_order = db.Column(db.Integer, default=0)


    


# ---------------------------------------------------------------------------
# PD Transformation (Grade -> PD table, with Agri + Digital stress uplift)
# ---------------------------------------------------------------------------
class PDGrade(db.Model):
    __tablename__ = "pd_grades"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    grade_number = db.Column(db.Integer, nullable=False)  # 1..8
    grade_label = db.Column(db.String(50), nullable=False)     # 'Grade 1'
    internal_grade_name = db.Column(db.String(80))             # 'Exceptionally Low Risk'
    sp_band = db.Column(db.String(30))                         # 'AAA-AA'
    score_range_label = db.Column(db.String(30))                # '100 - 90'
    min_score = db.Column(db.Float, default=0)
    mid_pd = db.Column(db.Float, default=0)                     # informational
    upper_bound_pd = db.Column(db.Float, default=0)             # D column
    stress_agri_digital = db.Column(db.Float, default=0)        # E column
    is_default_grade = db.Column(db.Boolean, default=False)     # Grade 8 special-cases to PD=1

    def multiplier(self):
        if self.is_default_grade or not self.upper_bound_pd:
            return None
        return (self.upper_bound_pd + self.stress_agri_digital) / self.upper_bound_pd

    def adjusted_pd(self):
        if self.is_default_grade:
            return 1.0
        m = self.multiplier()
        return self.upper_bound_pd * m if m is not None else self.upper_bound_pd

class NGOSupportItem(db.Model):
    """A line item like 'Matching Fund', 'Grant Funding', etc. Each has a
    % that, summed across all active items, reduces the final required rate.

    If the item has Tiers (see NGOSupportTier), the user picks a range from a
    dropdown (like the Excel 'NGO Impact' table) instead of typing a raw %,
    and the tier's own rate_reduction is used directly."""
    __tablename__ = "ngo_support_items"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    percent = db.Column(db.Float, nullable=False, default=0.0)  # fraction, e.g. 0.05 = 5%
    max_price_impact_pct = db.Column(db.Float, nullable=False, default=0.0)  # this item's own cap, e.g. 0.01 = 1%
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    selected_tier_id = db.Column(db.Integer, db.ForeignKey("ngo_support_tiers.id"), nullable=True)

    tiers = db.relationship("NGOSupportTier", cascade="all, delete-orphan",
                             order_by="NGOSupportTier.display_order",
                             foreign_keys="NGOSupportTier.item_id")
    selected_tier = db.relationship("NGOSupportTier", foreign_keys=[selected_tier_id],
                                     post_update=True)


class NGOSupportTier(db.Model):
    """A dropdown range option for an NGOSupportItem, e.g. Seed Fund '>50%'
    -> 2.8% rate reduction, mirroring the Excel 'NGO Impact' Range table."""
    __tablename__ = "ngo_support_tiers"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("ngo_support_items.id"), nullable=False)
    label = db.Column(db.String(50), nullable=False)              # '>50%', '40%-50%', '0%'
    rate_reduction = db.Column(db.Float, nullable=False, default=0.0)  # fraction, e.g. 0.028 = 2.8%
    display_order = db.Column(db.Integer, default=0)
# ---------------------------------------------------------------------------
# Cost of Fund sheet
# ---------------------------------------------------------------------------
class CostOfFundSource(db.Model):
    __tablename__ = "cost_of_fund_sources"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    annual_rate = db.Column(db.Float, default=0.0)
    display_order = db.Column(db.Integer, default=0)

    def annual_expense(self):
        return self.balance * self.annual_rate


# ---------------------------------------------------------------------------
# Vlookup reference tables
# ---------------------------------------------------------------------------
class RWAOption(db.Model):
    """Risk-Weight mapping per NBE capital directive."""
    __tablename__ = "rwa_options"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    rwa_value = db.Column(db.Float, nullable=False, default=1.0)
    display_order = db.Column(db.Integer, default=0)


class RepaymentSchedule(db.Model):
    """Additional rate for repayment schedule / loan tenure, e.g. '9 months-Grains (Furtuu)'."""
    __tablename__ = "repayment_schedules"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    tenure_months = db.Column(db.Float, nullable=False, default=1.0)
    rate = db.Column(db.Float, nullable=False, default=0.0)
    display_order = db.Column(db.Integer, default=0)


class OperationalCostComponent(db.Model):
    __tablename__ = "operational_cost_components"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Float, nullable=False, default=0.0)
    display_order = db.Column(db.Integer, default=0)


# ---------------------------------------------------------------------------
# Risk-Adjusted Price sheet inputs (the blue "Inputs" cells)
# ---------------------------------------------------------------------------
class PricingInput(db.Model):
    __tablename__ = "pricing_inputs"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    cost_of_capital = db.Column(db.Float, default=0.1838)          # C7
    target_return_on_rwa = db.Column(db.Float, default=0.19)       # C8
    liquidity_premium = db.Column(db.Float, default=0.0)           # C10 (blank in source)
    loan_amount = db.Column(db.Float, default=100000.0)            # C11
    rwa_option_id = db.Column(db.Integer, db.ForeignKey("rwa_options.id")) 
     # D12 selection

    loss_given_default = db.Column(db.Float, default=0.5)          # C17
    exposure_at_default = db.Column(db.Float, default=1.0)         # C18
    ngo_max_price_impact_pct = db.Column(db.Float, nullable=False, default=0.0655)  # 100% NGO alloc → this much price cut

    repayment_schedule_id = db.Column(db.Integer, db.ForeignKey("repayment_schedules.id"))  # E28
    expected_access_fee_pct = db.Column(db.Float, default=0.035)   # C31

    rwa_option = db.relationship("RWAOption", foreign_keys=[rwa_option_id])
    repayment_schedule = db.relationship("RepaymentSchedule", foreign_keys=[repayment_schedule_id])


# ---------------------------------------------------------------------------
# Projection (per-crop / per-segment volume & profitability projection)
# Mirrors the "Profit_or_Return_For_30K" workbook: one tab per crop
# (Wheat, Barley, ...), each with its own farmer count, ticket size, tenure
# and rate assumptions, rolling up to Portfolio, Interest Income, Profit and
# ROA. Add as many crops/segments as needed per product.
# ---------------------------------------------------------------------------
class ProjectionScenario(db.Model):
    __tablename__ = "projection_scenarios"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    crop_name = db.Column(db.String(120), nullable=False)      # 'Wheat', 'Barley', ...
    year_label = db.Column(db.String(20), default="Y1")

    number_of_farmers = db.Column(db.Integer, nullable=False, default=0)
    ticket_size = db.Column(db.Float, nullable=False, default=0.0)          # ETB, input cost per farmer
    loan_tenure_months = db.Column(db.Float, nullable=False, default=8.0)
    monthly_interest_rate = db.Column(db.Float, nullable=False, default=0.0)  # fraction, e.g. 0.0196625

    annual_cost_of_fund_pct = db.Column(db.Float, nullable=False, default=0.045)  # fraction, yearly WACF
    cost_of_lmd_pct = db.Column(db.Float, nullable=False, default=0.0)      # fraction of portfolio
    misc_cost_pct = db.Column(db.Float, nullable=False, default=0.01)       # fraction of interest income
    access_fee_pct = db.Column(db.Float, nullable=False, default=0.035)     # fraction of portfolio (income)
    rms_fee_pct = db.Column(db.Float, nullable=False, default=0.015)        # fraction of portfolio (cost)
    disaster_risk_pct = db.Column(db.Float, nullable=False, default=0.0)    # fraction of portfolio (info only)

    income_tax_pct = db.Column(db.Float, nullable=False, default=0.30)
    provision_pct = db.Column(db.Float, nullable=False, default=0.05)         # fraction of profit after tax
    provision_status_pct = db.Column(db.Float, nullable=False, default=0.25)  # fraction of provision amount

    display_order = db.Column(db.Integer, default=0)


# ---------------------------------------------------------------------------
# Eligibility (who qualifies) + Product Features (loan terms/details)
# ---------------------------------------------------------------------------
class EligibilityCriterion(db.Model):
    """A single qualifying condition, e.g. 'Minimum farm size' -> '>= 0.5 hectare'."""
    __tablename__ = "eligibility_criteria"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    criterion = db.Column(db.String(300), nullable=False)
    requirement = db.Column(db.String(300), nullable=False)
    is_mandatory = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)


class ProductFeature(db.Model):
    """A loan feature/detail row, e.g. 'Loan Tenure' -> '4 - 12 months'."""
    __tablename__ = "product_features"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    feature = db.Column(db.String(200), nullable=False)
    value = db.Column(db.String(300), nullable=False)
    display_order = db.Column(db.Integer, default=0)