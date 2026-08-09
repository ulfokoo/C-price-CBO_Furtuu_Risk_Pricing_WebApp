"""
Calculation engine that reproduces every formula found in the original workbook:
  - Furtuu- Score card Weighted
  - Risk-Adjusted Price
  - Cost of Fund
  - PD Transformation
  - Vlookup sheet
  - S&P PD and Rating   (folded into PD Transformation / reference data)

All functions are pure: they read a Product's related rows and return plain
dict/number results. Nothing here mutates the database.
"""

NGO_MAX_PRICE_IMPACT_PCT = 0.0655  # 100% NGO allocation = max 6.55% price reduction


def compute_scorecard(product):
    """Mirrors 'Furtuu- Score card Weighted': category totals, total weighted
    score, resulting Customer Grade, and the PD looked up from that grade."""
    categories = []
    total_weighted_score = 0.0
    for cat in product.categories:
        sub_rows = []
        cat_total = 0.0
        for sp in cat.sub_parameters:
            score = sp.score()
            weighted = sp.weighted_score()
            cat_total += weighted
            sub_rows.append({
                "sub_parameter": sp,
                "score": score,
                "weighted_score": weighted,
            })
        categories.append({
            "category": cat,
            "sub_rows": sub_rows,
            "category_weighted_total": cat_total,
        })
        total_weighted_score += cat_total

    grade = grade_from_score(total_weighted_score)
    pd_grade = next((g for g in product.pd_grades if g.grade_label == grade), None)
    pd_value = pd_grade.adjusted_pd() if pd_grade else None

    return {
        "categories": categories,
        "total_weighted_score": total_weighted_score,
        "total_weight": product.total_category_weight(),
        "grade": grade,
        "pd_grade": pd_grade,
        "pd_value": pd_value,
    }


def grade_from_score(score):
    """=IF(G115>=90,"Grade 1",IF(G115>=80,"Grade 2", ... ,"Grade 8"))"""
    if score >= 90:
        return "Grade 1"
    if score >= 80:
        return "Grade 2"
    if score >= 70:
        return "Grade 3"
    if score >= 60:
        return "Grade 4"
    if score >= 50:
        return "Grade 5"
    if score >= 40:
        return "Grade 6"
    if score >= 30:
        return "Grade 7"
    return "Grade 8"





def compute_ngo_support(product):
    rows = list(product.ngo_support_items)
    cap = product.pricing_input.ngo_max_price_impact_pct if product.pricing_input else NGO_MAX_PRICE_IMPACT_PCT
    total_pct = min(sum(r.percent for r in rows if r.is_active), 1.0)
    total_max_pct = sum(r.max_price_impact_pct for r in rows if r.is_active)
    raw_reduction_pct = 0.0
    for r in rows:
        if not r.is_active:
            continue
        if r.tiers:
            raw_reduction_pct += r.selected_tier.rate_reduction if r.selected_tier else 0.0
        else:
            raw_reduction_pct += r.percent * r.max_price_impact_pct
    # However many items are active/allocated, the combined price reduction
    # can never exceed the product's cap — items don't simply stack past it.
    effective_reduction_pct = min(raw_reduction_pct, cap)
    return {
        "rows": rows,
        "total_pct": total_pct,
        "total_max_pct": total_max_pct,
        "cap": cap,
        "raw_reduction_pct": raw_reduction_pct,
        "effective_reduction_pct": effective_reduction_pct,
    }


def compute_cost_of_fund(product):
    """Mirrors 'Cost of Fund': weighted average cost of funding across all
    funding sources = SUM(Annual Int Expense) / SUM(Balance)."""
    rows = []
    total_balance = 0.0
    total_expense = 0.0
    for src in product.cost_of_fund_sources:
        expense = src.annual_expense()
        rows.append({"source": src, "expense": expense})
        total_balance += src.balance
        total_expense += expense

    weighted_avg = (total_expense / total_balance) if total_balance else 0.0
    return {
        "rows": rows,
        "total_balance": total_balance,
        "total_expense": total_expense,
        "weighted_avg_cost_of_fund": weighted_avg,
    }


def compute_pd_transformation(product):
    """Mirrors 'PD Transformation' / 'S&P PD and Rating': multiplier and
    adjusted PD per grade, using the Agri + Digital stress uplift."""
    rows = []
    for g in sorted(product.pd_grades, key=lambda x: x.grade_number):
        rows.append({
            "grade": g,
            "multiplier": g.multiplier(),
            "adjusted_pd": g.adjusted_pd(),
        })
    return {"rows": rows}


def compute_pricing(product):
    """Mirrors 'Risk-Adjusted Price': the main scenario waterfall plus the
    'Price Across Bankable Risk Grade' table."""
    pin = product.pricing_input
    if pin is None:
        return None

    scorecard = compute_scorecard(product)
    cof = compute_cost_of_fund(product)
    pd_transform = compute_pd_transformation(product)

    rwa = pin.rwa_option.rwa_value if pin.rwa_option else 0.0
    cost_of_fund = cof["weighted_avg_cost_of_fund"]
    op_cost = sum(c.value for c in product.op_cost_components)
    tenure_rate = pin.repayment_schedule.rate if pin.repayment_schedule else 0.0
    tenure_months = pin.repayment_schedule.tenure_months if pin.repayment_schedule else 12.0

    pd_value = scorecard["pd_value"] or 0.0
    expected_credit_loss = pd_value * pin.loss_given_default * pin.exposure_at_default  # C19

    target_return = pin.target_return_on_rwa * rwa                       # C24
    target_return_etb = target_return * pin.loan_amount                  # D24

    cost_of_fund_etb = cost_of_fund * pin.loan_amount                    # D25
    risk_adj_etb = expected_credit_loss * pin.loan_amount                 # D26
    op_cost_etb = op_cost * pin.loan_amount                               # D27
    tenure_charge_etb = tenure_rate * pin.loan_amount                     # D28

    interest_rate_annual_before_ngo = (target_return + cost_of_fund + expected_credit_loss
                                        + op_cost + tenure_rate)          # C29, pre-NGO

    ngo = compute_ngo_support(product)
    interest_rate_annual = interest_rate_annual_before_ngo - ngo["effective_reduction_pct"]
    interest_rate_annual_etb = interest_rate_annual * pin.loan_amount     # D29

    interest_rate_tenor = (interest_rate_annual * tenure_months) / 12.0   # C30 generalised
    interest_rate_tenor_etb = interest_rate_tenor * pin.loan_amount       # D30

    access_fee_etb = pin.loan_amount * pin.expected_access_fee_pct        # D31
    required_rate = interest_rate_tenor - pin.expected_access_fee_pct     # C32
    required_rate_etb = required_rate * pin.loan_amount                  # D32

    main_scenario = {
        "cost_of_capital": pin.cost_of_capital,
        "target_return_on_rwa": pin.target_return_on_rwa,
        "cost_of_fund": cost_of_fund,
        "loan_amount": pin.loan_amount,
        "rwa": rwa,
        "rwa_label": pin.rwa_option.label if pin.rwa_option else "-",
        "pd": pd_value,
        "lgd": pin.loss_given_default,
        "ead": pin.exposure_at_default,
        "expected_credit_loss": expected_credit_loss,
        "target_return": target_return,
        "target_return_etb": target_return_etb,
        "cost_of_fund_etb": cost_of_fund_etb,
        "risk_adj_etb": risk_adj_etb,
        "op_cost": op_cost,
        "op_cost_etb": op_cost_etb,
        "tenure_label": pin.repayment_schedule.label if pin.repayment_schedule else "-",
        "tenure_months": tenure_months,
        "tenure_rate": tenure_rate,
        "tenure_charge_etb": tenure_charge_etb,
        "interest_rate_annual": interest_rate_annual,
        "interest_rate_annual_etb": interest_rate_annual_etb,
        "interest_rate_tenor": interest_rate_tenor,
        "interest_rate_tenor_etb": interest_rate_tenor_etb,
        "access_fee_pct": pin.expected_access_fee_pct,
        "access_fee_etb": access_fee_etb,
        "required_rate": required_rate,
        "required_rate_etb": required_rate_etb,
        "interest_rate_annual_before_ngo": interest_rate_annual_before_ngo,
        "ngo_total_pct": ngo["total_pct"],
        "ngo_effective_reduction_pct": ngo["effective_reduction_pct"],
        "grade": scorecard["grade"],
        "total_weighted_score": scorecard["total_weighted_score"],
    }

    # Price Across Bankable Risk Grade table: same fixed target return / cost
    # of fund / tenure charge / op cost, varying credit risk premium (PD*LGD*EAD)
    ngo_reduction = ngo["effective_reduction_pct"]

    grade_rows = []
    for row in pd_transform["rows"]:
        g = row["grade"]
        g_pd = row["adjusted_pd"]
        credit_premium = g_pd * pin.loss_given_default * pin.exposure_at_default
        annual = target_return + cost_of_fund + credit_premium + tenure_rate + op_cost
        tenor = (annual * tenure_months) / 12.0
        annual_after_ngo = annual - ngo_reduction
        tenor_after_ngo = (annual_after_ngo * tenure_months) / 12.0
        grade_rows.append({
            "grade_label": g.grade_label,
            "pd": g_pd,
            "target_return": target_return,
            "cost_of_fund": cost_of_fund,
            "tenure_rate": tenure_rate,
            "op_cost": op_cost,
            "credit_risk_premium": credit_premium,
            "interest_rate_annual": annual,
            "interest_rate_tenor": tenor,
            "ngo_reduction": ngo_reduction,
            "interest_rate_annual_after_ngo": annual_after_ngo,
            "interest_rate_tenor_after_ngo": tenor_after_ngo,
        })