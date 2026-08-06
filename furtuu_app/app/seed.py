from app import db
from app.models import (
    User, Product, ScoreCategory, SubParameter, ScoringOption, PricingInput,
    CostOfFundSource, RWAOption, RepaymentSchedule, OperationalCostComponent, PDGrade
)


def ensure_default_admin():
    if User.query.count() == 0:
        admin = User(username="admin", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        officer = User(username="loanofficer", role="user")
        officer.set_password("officer123")
        db.session.add(officer)
        db.session.commit()

    if Product.query.count() == 0:
        seed_furtuu_product()


# ---------------------------------------------------------------------------
# Categories -> [(sub-parameter name, weight%, [(option label, score), ...], selected_label)]
# ---------------------------------------------------------------------------
SCORECARD_DEF = [
    ("Rainfall & Disease Risk (15%)", [
        ("Rainfall Outlook", 8, [
            ("Favorable / Strong", 100), ("Adequate / Acceptable", 75), ("Low", 50),
            ("Risky / Below Standard", 25)], "Favorable / Strong"),
        ("Disease Outbreak Tendency", 7, [
            ("Low", 100), ("Moderate", 70), ("High", 40)], "Moderate"),
    ]),
    ("Market & Commercial Risk (10%)", [
        ("Output Price Volatility", 2, [
            ("Stable", 100), ("Moderate", 75), ("Volatile", 50), ("Highly Volatile", 25)], "Stable"),
        ("Input Price Volatility", 3, [
            ("Stable", 100), ("Moderate", 75), ("Volatile", 50), ("Highly Volatile", 25)], "Stable"),
        ("Market Access", 2, [
            ("Formal contract / Off-taker", 100), ("Informal but regular buyers", 75),
            ("Occasional buyers", 50), ("No reliable market", 25)], "Formal contract / Off-taker"),
        ("Infrastructure Support", 2, [
            ("Strong", 100), ("Moderate", 75), ("Limited", 50), ("Very weak / None", 25)], "Strong"),
        ("Demand Stability", 1, [
            ("Strong", 100), ("Moderate", 75), ("Fluctuating", 50), ("Weak", 40)], "Strong"),
    ]),
    ("Economic Risk (4%)", [
        ("Inflation Outlook", 4, [
            ("Stable", 100), ("Moderate", 70), ("High", 40)], "Stable"),
    ]),
    ("Political Risk (6%)", [
        ("Political Instability", 4, [
            ("Stable", 100), ("Moderate", 70), ("Unstable", 40)], "Stable"),
        ("Government Priority", 2, [
            ("High Priority", 100), ("Moderate Priority", 70), ("Low Priority", 40)], "High Priority"),
    ]),
    ("Product Nature Risk (30%)", [
        ("Weather Shock Resilience", 6, [
            ("Resilient", 100), ("Moderate", 75), ("Sensitive", 50), ("Highly Sensitive", 40)], "Resilient"),
        ("Disease Resistance", 6, [
            ("Resistant", 100), ("Sensitive", 70), ("Highly Vulnerable", 40)], "Resistant"),
        ("Perishability", 5, [
            ("Durable", 100), ("Moderately Resilient", 75), ("Perishable", 50),
            ("Highly Perishable", 25)], "Perishable"),
        ("Location Suitability (Soil & Agro)", 6, [
            ("Highly Suitable", 100), ("Suitable", 75), ("Moderate", 50), ("Less Suitable", 25)],
         "Highly Suitable"),
        ("Production Cycle", 7, [
            ("2-5 months", 100), ("5-9 months", 70), ("> 9 months", 40)], "2-5 months"),
    ]),
    ("Counterparty Risk (20%)", [
        ("Experience", 4, [
            (">5 years", 100), ("3-5 years", 75), ("1-3 years", 50), ("No experience", 25)], ">5 years"),
        ("Other Income Sources", 5, [
            ("Regular", 100), ("Seasonal", 70), ("None", 40)], "Regular"),
        ("Technical Capacity & Training", 4, [
            ("Formal Education+ Training", 100), ("Formal Education / Training", 70),
            ("None", 40)], "Formal Education+ Training"),
        ("Loan Amount vs Limit", 3, [
            ("0-40%", 100), ("40-60%", 80), ("60-80%", 60), ("80-100%", 25)], "40-60%"),
        ("Age", 2, [
            ("36-45 Years", 100), ("46-60 Years", 80), ("26-36 Years", 60), ("18-25 Years", 40),
            (">60 Years", 25)], "26-36 Years"),
        ("Marital Status", 2, [
            ("Married", 100), ("Single", 85), ("Divorced", 70), ("Widowed", 55)], "Divorced"),
    ]),
    ("Banking Relationship (15%)", [
        ("Repayment Tendency", 6, [
            ("Regular Payment/ No arrears", 100), ("1-29 days", 80), ("30-89 days", 60),
            ("Default (>90 days)", 0), ("Not Applicable (new customer)", 100)],
         "Regular Payment/ No arrears"),
        ("Borrowing Frequency", 2, [
            (">5 times", 100), ("4-5 times", 80), ("2-3 times", 60), ("1 time", -5),
            ("Not Applicable (new customer)", 100)], ">5 times"),
        ("Previous Exposure limit", 2, [
            (">300,000", 100), ("200,000 - 300,000", 80), ("100,000 - 200,000", 60),
            ("100,000 - 50,000", 25), ("Not Applicable (new customer)", 100)], ">300,000"),
        ("Restructured History", 2, [
            ("No", 100), ("Yes", 0), ("Not Applicable (new customer)", 100)], "No"),
        ("Account Performance against Loan limit", 2, [
            ("Good", 100), ("Moderate", 70), ("Weak", 40)], "Good"),
        ("Account Turnover", 2, [
            (">5 times", 100), ("2-5 times", 70), ("<2 times", 40)], ">5 times"),
    ]),
]

PD_GRADES_DEF = [
    # (grade_num, internal_name, sp_band, score_range, min_score, mid_pd, upper_bound_pd%, stress%, is_default)
    (1, "Exceptionally Low Risk", "AAA-AA", "100 - 90", 90, 0.05, 0.05, 1.0, False),
    (2, "Very Low Risk", "A", "89 - 80", 80, 0.10, 0.10, 1.5, False),
    (3, "Low Risk", "BBB+", "79 - 70", 70, 0.25, 0.30, 2.0, False),
    (4, "Moderate Risk", "BBB", "69 - 60", 60, 0.75, 1.00, 2.5, False),
    (5, "Potential Risk", "BB", "59 - 50", 50, 2.00, 5.00, 3.0, False),
    (6, "High Risk", "B+", "49 - 40", 40, 4.50, 15.00, 3.5, False),
    (7, "Very High Risk", "B-", "39 - 30", 30, 8.00, 40.00, 4.0, False),
    (8, "Default", "CCC-D", "< 30", 0, 15.00, 100.00, 4.5, True),
]


def seed_furtuu_product():
    product = Product(
        name="Furtuu (Grain Value Chain)",
        description="Cooperative Bank of Oromia agricultural loan for grain producers — 9-month tenor.",
    )
    db.session.add(product)
    db.session.flush()

    for cat_idx, (cat_name, subs) in enumerate(SCORECARD_DEF, start=1):
        cat = ScoreCategory(product_id=product.id, name=cat_name, display_order=cat_idx)
        db.session.add(cat)
        db.session.flush()
        for sp_idx, (sp_name, weight_pct, options, selected_label) in enumerate(subs, start=1):
            sp = SubParameter(category_id=cat.id, name=sp_name, weight=weight_pct / 100.0,
                               display_order=sp_idx)
            db.session.add(sp)
            db.session.flush()
            selected_id = None
            for opt_idx, (label, score) in enumerate(options, start=1):
                opt = ScoringOption(sub_parameter_id=sp.id, label=label, score=score,
                                     display_order=opt_idx)
                db.session.add(opt)
                db.session.flush()
                if label == selected_label:
                    selected_id = opt.id
            sp.selected_option_id = selected_id

    # PD Grades
    for num, iname, sp_band, rng, minscore, midpd, upper, stress, is_def in PD_GRADES_DEF:
        db.session.add(PDGrade(
            product_id=product.id, grade_number=num, grade_label=f"Grade {num}",
            internal_grade_name=iname, sp_band=sp_band, score_range_label=rng,
            min_score=minscore, mid_pd=midpd, upper_bound_pd=upper / 100.0,
            stress_agri_digital=stress / 100.0, is_default_grade=is_def,
        ))

    # RWA options (Vlookup sheet)
    rwa_retail = RWAOption(product_id=product.id, label="Retail Exposure- meeting NBE criteria",
                            rwa_value=0.75, display_order=1)
    db.session.add(rwa_retail)
    db.session.add(RWAOption(product_id=product.id, label="Non-Regulatory Retail", rwa_value=1.0,
                              display_order=2))

    # Repayment schedules (Vlookup sheet)
    schedules = [
        ("2 months-Poultry Broiler", 2, 0.25),
        ("5 months-OX/Shoat fattening", 5, 0.5),
        ("7 months-Grains (Michu Agri)", 7, 0.75),
        ("9 months-Grains (Furtuu)", 9, 0.9),
        ("13 months-Poultry Layer", 13, 1.6),
    ]
    furtuu_schedule = None
    for i, (label, months, rate_pct) in enumerate(schedules, start=1):
        rs = RepaymentSchedule(product_id=product.id, label=label, tenure_months=months,
                                rate=rate_pct / 100.0, display_order=i)
        db.session.add(rs)
        db.session.flush()
        if "Furtuu" in label:
            furtuu_schedule = rs

    # Operational cost components (Vlookup sheet)
    for i, (name, val_pct) in enumerate(
            [("Tech", 1.5), ("Commission", 0.37), ("Miscellaneous", 1.0)], start=1):
        db.session.add(OperationalCostComponent(product_id=product.id, name=name, value=val_pct / 100.0,
                                                  display_order=i))

    # Cost of Fund sources (as of March 31, 2026 — figures from the source workbook)
    cof_sources = [
        ("Savings Deposit (Excluding IFB)", 95952803.96, 7.0),
        ("Non-interest Bearing Deposit", 80163083.96, 0.0),
        ("Fixed Time Deposits", 14998167.22, 12.56),
        ("Interbank Money Market Borrowing", 0.0, 17.9),
    ]
    for i, (name, bal, rate_pct) in enumerate(cof_sources, start=1):
        db.session.add(CostOfFundSource(product_id=product.id, name=name, balance=bal,
                                         annual_rate=rate_pct / 100.0, display_order=i))

    db.session.flush()

    # Pricing inputs
    pin = PricingInput(
        product_id=product.id,
        cost_of_capital=0.1388 + 0.045,   # T-bill 13.88% + 4.5% equity risk premium
        target_return_on_rwa=0.19,
        liquidity_premium=0.0,
        loan_amount=100000.0,
        rwa_option_id=rwa_retail.id,
        loss_given_default=0.5,
        exposure_at_default=1.0,
        repayment_schedule_id=furtuu_schedule.id if furtuu_schedule else None,
        expected_access_fee_pct=0.035,
    )
    db.session.add(pin)
    db.session.commit()
