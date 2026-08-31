"""
finance/budgets.py — Per-department monthly budget management.

POST   /finance/budgets              → manager or above sets a budget
PATCH  /finance/budgets/:id          → owner edits amount
POST   /finance/budgets/:id/disable  → owner suspends a budget
POST   /finance/budgets/:id/enable   → owner re-activates
GET    /finance/budgets/status?period=YYYY-MM → per-dept: budget vs spend vs remaining
GET    /finance/budgets/status?period=YYYY    → same, summed across that year's 12 months
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.utils.money import parse_amount, parse_quantity
from app.extensions import db
from app.models.user import User
from app.models.budget import Budget
from app.models.department import Department
from app.models.audit_log import AuditLog
from app.services.finance import parse_month_bounds, get_budget_spend

budgets_bp = Blueprint("finance_budgets", __name__, url_prefix="/finance")

OWNER_LEVEL   = 10
MANAGER_LEVEL = 5


@budgets_bp.post("/budgets")
@require_active_user
def create_budget():
    # Manager+ can set a budget (edit/disable/enable below stay owner-only —
    # changing or removing a budget already in force is more sensitive than
    # setting one for the first time).
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to set budgets."}), 403

    data    = request.get_json(silent=True) or {}
    dept_id = data.get("department_id")
    period  = (data.get("period") or "").strip()
    raw_amt = data.get("amount")

    if not dept_id or not period or raw_amt is None:
        return jsonify({"error": "department_id, period (YYYY-MM), and amount are required."}), 400

    try:
        datetime.strptime(period, "%Y-%m")
    except ValueError:
        return jsonify({"error": "period must be in YYYY-MM format, e.g. 2026-05."}), 400

    # A zero budget is meaningful — it says "spend nothing here this month".
    amount, err = parse_amount(raw_amt, "Budget amount", allow_zero=True)
    if err:
        return jsonify({"error": err}), 400

    dept = db.session.get(Department, dept_id)
    if not dept:
        return jsonify({"error": "Department not found."}), 404

    existing = db.session.query(Budget).filter_by(
        department_id=dept_id, period=period
    ).first()
    if existing:
        return jsonify({"error": f"A budget for {dept.name} in {period} already exists. "
                                  f"PATCH it to change the amount."}), 409

    budget = Budget(
        department_id=dept_id,
        period=period,
        amount=amount,
        set_by_id=actor.id,
    )
    db.session.add(budget)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="finance.budget.create",
                 target=dept_id, details=f"period={period} amount={amount}")
    db.session.commit()

    return jsonify({"id": budget.id, "department": dept.name,
                    "period": period, "amount": str(amount)}), 201


@budgets_bp.patch("/budgets/<budget_id>")
@require_active_user
def edit_budget(budget_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can edit budgets."}), 403

    budget = db.session.get(Budget, budget_id)
    if not budget:
        return jsonify({"error": "Budget not found."}), 404

    data = request.get_json(silent=True) or {}
    if "amount" in data:
        try:
            budget.amount = Decimal(str(data["amount"]))
        except InvalidOperation:
            return jsonify({"error": "amount must be a number."}), 400
        if budget.amount < Decimal("0"):
            return jsonify({"error": "Budget amount cannot be negative."}), 400

    budget.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="finance.budget.edit", target=budget_id)
    db.session.commit()
    return jsonify({"id": budget.id, "amount": str(budget.amount),
                    "is_active": budget.is_active}), 200


@budgets_bp.post("/budgets/<budget_id>/disable")
@require_active_user
def disable_budget(budget_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can disable budgets."}), 403
    budget = db.session.get(Budget, budget_id)
    if not budget:
        return jsonify({"error": "Budget not found."}), 404
    budget.is_active = False
    db.session.flush()
    AuditLog.log(actor=actor.username, action="finance.budget.disable", target=budget_id)
    db.session.commit()
    return jsonify({"id": budget.id, "is_active": False}), 200


@budgets_bp.post("/budgets/<budget_id>/enable")
@require_active_user
def enable_budget(budget_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can enable budgets."}), 403
    budget = db.session.get(Budget, budget_id)
    if not budget:
        return jsonify({"error": "Budget not found."}), 404
    budget.is_active = True
    db.session.flush()
    AuditLog.log(actor=actor.username, action="finance.budget.enable", target=budget_id)
    db.session.commit()
    return jsonify({"id": budget.id, "is_active": True}), 200


@budgets_bp.get("/budgets/status")
@require_active_user
def budget_status():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    period_str = request.args.get("period")
    if not period_str:
        from datetime import datetime
        period_str = datetime.now(timezone.utc).strftime("%Y-%m")

    include_disabled = request.args.get("include_disabled", "false").lower() == "true"

    # A bare 4-digit year (e.g. "2026") asks for the whole-year view: sum
    # every month that year has a budget for, per department, rather than
    # one specific month. Budgets are still only ever SET monthly (create_budget
    # above) — this only changes how the status/reporting endpoint reads them
    # back, so no schema change, no new period format to store or migrate.
    if period_str.isdigit() and len(period_str) == 4:
        year = period_str
        query = db.session.query(Budget).filter(Budget.period.like(f"{year}-%"))
        if not include_disabled:
            query = query.filter_by(is_active=True)
        budgets = query.all()

        by_dept: dict[str, dict] = {}
        for b in budgets:
            month_start, month_end = parse_month_bounds(b.period)
            spent = get_budget_spend(b.department_id, month_start, month_end)
            dept_name = b.department.name if b.department else b.department_id
            row = by_dept.setdefault(dept_name, {"budget": Decimal("0"), "spent": Decimal("0")})
            row["budget"] += Decimal(str(b.amount))
            row["spent"]  += spent

        result = []
        for dept_name, row in by_dept.items():
            bamt, spent = row["budget"], row["spent"]
            remaining = bamt - spent
            pct_used  = float(spent / bamt * 100) if bamt > 0 else 0.0
            result.append({
                "department":  dept_name,
                "period":      year,
                "budget":      str(bamt),
                "spent":       str(spent),
                "remaining":   str(remaining),
                "pct_used":    round(pct_used, 1),
                "over_budget": spent > bamt,
            })
        return jsonify({"period": year, "budgets": result}), 200

    try:
        period_start, period_end = parse_month_bounds(period_str)
    except ValueError:
        return jsonify({"error": "Invalid period. Use YYYY-MM (month) or YYYY (year)."}), 400

    query = db.session.query(Budget).filter_by(period=period_str)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    budgets = query.all()

    result = []
    for b in budgets:
        spent     = get_budget_spend(b.department_id, period_start, period_end)
        bamt      = Decimal(str(b.amount))
        remaining = bamt - spent
        pct_used  = float(spent / bamt * 100) if bamt > 0 else 0.0

        dept_name = b.department.name if b.department else b.department_id
        result.append({
            "budget_id":    b.id,
            "department":   dept_name,
            "period":       period_str,
            "budget":       str(bamt),
            "spent":        str(spent),
            "remaining":    str(remaining),
            "pct_used":     round(pct_used, 1),
            "over_budget":  spent > bamt,
        })

    return jsonify({"period": period_str, "budgets": result}), 200
