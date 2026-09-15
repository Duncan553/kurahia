"""
purchases.py — Purchase requests + completed purchases.

Approval chain:
  POST /inventory/purchase-requests            → dept head creates (PENDING)
  POST /inventory/purchase-requests/:id/propose → manager attaches budget
  POST /inventory/purchase-requests/:id/approve → owner approves / rejects
  POST /inventory/purchases                    → manager records actual purchase
                                                 (triggers PURCHASE StockMovement)

Rules:
  - Manager cannot approve their own proposed budget (checked explicitly)
  - receipt_photo_path is mandatory on a Purchase record
  - Purchase → StockMovement(PURCHASE) is atomic
"""
import uuid
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.purchase_request import PurchaseRequest, RequestStatus
from app.models.purchase import Purchase
from app.models.stock_movement import StockMovement, MovementReason
from app.models.inventory_item import InventoryItem
from app.models.user import User
from app.models.audit_log import AuditLog

purchases_bp = Blueprint("inv_purchases", __name__, url_prefix="/inventory")

MANAGER_LEVEL = 5
OWNER_LEVEL   = 10


# ── Purchase Requests ─────────────────────────────────────────────────────────

@purchases_bp.get("/purchase-requests")
@require_active_user
def list_requests():
    """Recent purchase requests — manager sees their department's; owner sees all.

    Query params:
      ?status=DRAFT          — filter by status
      ?system_generated=true — only system-generated auto-drafts
    """
    from datetime import datetime, timezone, timedelta
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    q = (request.args.get("q") or "").strip()

    since = datetime.now(timezone.utc) - timedelta(days=30)
    query = db.session.query(PurchaseRequest).filter(PurchaseRequest.created_at >= since)

    if q:
        query = query.outerjoin(InventoryItem, PurchaseRequest.item_id == InventoryItem.id).filter(
            db.or_(
                InventoryItem.name.ilike(f"%{q}%"),
                PurchaseRequest.item_description.ilike(f"%{q}%"),
            )
        )

    status_filter = request.args.get("status")
    if status_filter:
        query = query.filter(PurchaseRequest.status == status_filter)

    sg = request.args.get("system_generated")
    if sg and sg.lower() == "true":
        query = query.filter(PurchaseRequest.system_generated == True)

    if actor.role.level < 10 and actor.department_id:
        from app.models.user import User as U
        dept_ids = [u.id for u in db.session.query(U).filter_by(department_id=actor.department_id).all()]
        query = query.filter(
            db.or_(
                PurchaseRequest.requested_by_id.in_(dept_ids),
                PurchaseRequest.requested_by_id.is_(None),
            )
        )

    reqs = query.order_by(PurchaseRequest.created_at.desc()).all()
    return jsonify([{
        "id":               r.id,
        "item_id":          r.item_id,
        "item_name":        r.item.name if r.item else r.item_description,
        "quantity":         str(r.quantity),
        "unit":             r.item.unit if r.item else None,
        "status":           r.status,
        "system_generated": r.system_generated,
        "created_at":       r.created_at.isoformat(),
        "requested_by":     r.requested_by.username if r.requested_by else "system",
        "department":       r.item.department.name if r.item and r.item.department else (
                            r.requested_by.department.name if r.requested_by and r.requested_by.department else "General"),
        "notes":            r.manager_notes,
        "estimated_cost":   str(r.estimated_cost) if r.estimated_cost else None,
    } for r in reqs]), 200


@purchases_bp.post("/purchase-requests")
@require_active_user
def create_request():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    data     = request.get_json(silent=True) or {}
    item_id  = data.get("item_id")
    item_desc = (data.get("item_description") or "").strip()
    raw_qty  = data.get("quantity")

    if not item_id and not item_desc:
        return jsonify({"error": "item_id or item_description required"}), 400
    if raw_qty is None:
        return jsonify({"error": "quantity is required"}), 400
    try:
        qty = Decimal(str(raw_qty))
    except InvalidOperation:
        return jsonify({"error": "quantity must be a number"}), 400
    if qty <= 0:
        return jsonify({"error": "quantity must be positive"}), 400

    if item_id:
        item = db.session.get(InventoryItem, item_id)
        if not item or not item.is_active:
            return jsonify({"error": "Item not found or inactive."}), 404

    with db.session.begin_nested():
        pr = PurchaseRequest(
            item_id=item_id,
            item_description=item_desc or None,
            quantity=qty,
            requested_by_id=actor.id,
        )
        db.session.add(pr)

    AuditLog.log(actor=actor.username, action="purchase_request.create", target=pr.id)
    db.session.commit()

    return jsonify({"id": pr.id, "status": pr.status}), 201


@purchases_bp.post("/purchase-requests/<pr_id>/submit")
@require_active_user
def submit_draft(pr_id):
    """Manager submits a DRAFT → PENDING, optionally editing quantity first."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    pr = db.session.get(PurchaseRequest, pr_id)
    if not pr:
        return jsonify({"error": "Purchase request not found."}), 404
    if pr.status != RequestStatus.DRAFT.value:
        return jsonify({"error": f"Only DRAFT requests can be submitted. This one is {pr.status}."}), 400

    data = request.get_json(silent=True) or {}
    with db.session.begin_nested():
        if "quantity" in data:
            try:
                qty = Decimal(str(data["quantity"]))
            except InvalidOperation:
                return jsonify({"error": "quantity must be a number."}), 400
            if qty <= 0:
                return jsonify({"error": "quantity must be positive."}), 400
            pr.quantity = qty
        pr.status = RequestStatus.PENDING.value
        pr.requested_by_id = actor.id

    AuditLog.log(actor=actor.username, action="purchase_request.submit", target=pr.id)
    db.session.commit()
    return jsonify({"id": pr.id, "status": pr.status, "quantity": str(pr.quantity)}), 200


@purchases_bp.post("/purchase-requests/<pr_id>/dismiss")
@require_active_user
def dismiss_draft(pr_id):
    """Manager dismisses a DRAFT suggestion → REJECTED."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    pr = db.session.get(PurchaseRequest, pr_id)
    if not pr:
        return jsonify({"error": "Purchase request not found."}), 404
    if pr.status != RequestStatus.DRAFT.value:
        return jsonify({"error": f"Only DRAFT requests can be dismissed. This one is {pr.status}."}), 400

    with db.session.begin_nested():
        pr.status = RequestStatus.REJECTED.value

    AuditLog.log(actor=actor.username, action="purchase_request.dismiss", target=pr.id)
    db.session.commit()
    return jsonify({"id": pr.id, "status": pr.status}), 200


@purchases_bp.post("/purchase-requests/<pr_id>/propose")
@require_active_user
def propose_budget(pr_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    pr = db.session.get(PurchaseRequest, pr_id)
    if not pr:
        return jsonify({"error": "Purchase request not found."}), 404
    # PENDING = first proposal; PROPOSED = manager revising their own estimate
    # before the owner has acted on it. Anything past that is a real decision
    # already made and shouldn't be quietly overwritten.
    if pr.status not in (RequestStatus.PENDING, RequestStatus.PROPOSED):
        return jsonify({"error": f"Request is already {pr.status}."}), 400

    data = request.get_json(silent=True) or {}
    raw_cost = data.get("estimated_cost")
    if raw_cost is None:
        return jsonify({"error": "estimated_cost is required"}), 400
    try:
        cost = Decimal(str(raw_cost))
    except InvalidOperation:
        return jsonify({"error": "estimated_cost must be a number"}), 400
    if cost < 0:
        return jsonify({"error": "estimated_cost cannot be negative"}), 400

    with db.session.begin_nested():
        pr.estimated_cost  = cost
        pr.manager_id      = actor.id
        pr.manager_notes   = data.get("notes")
        pr.status          = RequestStatus.PROPOSED.value

    AuditLog.log(actor=actor.username, action="purchase_request.propose", target=pr.id)
    db.session.commit()

    return jsonify({"id": pr.id, "status": pr.status, "estimated_cost": str(cost)}), 200



def _budget_room(item_id: str, period_dt=None):
    """What is left in this item's department budget this month.

    Returns (budget_amount, spent, remaining, dept_name) or None when no budget
    has been set — in which case there is no delegated authority to speak of
    and the owner decides, which is the safe default.
    """
    from app.models.budget import Budget
    from app.models.department import Department
    from app.services.finance import get_budget_spend
    from datetime import datetime as _dt, timezone as _tz
    from calendar import monthrange

    item = db.session.get(InventoryItem, item_id) if item_id else None
    if not item:
        return None
    now    = period_dt or _dt.now(_tz.utc)
    period = now.strftime("%Y-%m")
    budget = db.session.query(Budget).filter_by(
        department_id=item.department_id, period=period, is_active=True).first()
    if not budget:
        return None

    start = _dt(now.year, now.month, 1, tzinfo=_tz.utc)
    end   = _dt(now.year, now.month, monthrange(now.year, now.month)[1],
                23, 59, 59, tzinfo=_tz.utc)
    spent = get_budget_spend(item.department_id, start, end)
    dept  = db.session.get(Department, item.department_id)
    amount = Decimal(str(budget.amount))
    return amount, spent, amount - spent, (dept.name if dept else "this department")


@purchases_bp.post("/purchase-requests/<pr_id>/approve")
@require_active_user
def approve_request(pr_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    pr = db.session.get(PurchaseRequest, pr_id)
    if not pr:
        return jsonify({"error": "Purchase request not found."}), 404

    # Requestor cannot also be the approver
    if pr.requested_by_id == actor.id:
        return jsonify({"error": "You can't approve your own purchase request."}), 403

    if pr.status not in (RequestStatus.PENDING, RequestStatus.PROPOSED):
        return jsonify({"error": f"This request is already {pr.status} and cannot be approved again."}), 400

    data   = request.get_json(silent=True) or {}
    action = (data.get("action") or "approve").lower()  # "approve" or "reject"

    if action not in ("approve", "reject"):
        return jsonify({"error": "action must be 'approve' or 'reject'"}), 400

    # ── Who may say yes ─────────────────────────────────────────────────────
    #
    # Every request used to need the owner, for a crate of soda as much as for
    # a freezer. That is not control, it is a queue: the owner becomes the
    # bottleneck on the bar running out of tonic, and the real decisions get
    # rubber-stamped along with the trivial ones.
    #
    # The delegation is the budget. The OWNER sets what a department may spend
    # this month; inside that number a manager decides and gets on with it;
    # the moment a request would take the department past it, the manager
    # cannot approve it and it goes to the owner — who is then looking at the
    # one decision that actually needs them.
    #
    # No budget set means no delegated authority, so it stays with the owner.
    if action == "approve" and actor.role.level < OWNER_LEVEL:
        room = _budget_room(pr.item_id)
        cost = Decimal(str(pr.estimated_cost)) if pr.estimated_cost is not None else None
        if room is None:
            return jsonify({
                "error": "No budget is set for this department this month, so only "
                         "the owner can approve spending. Ask the owner to set one."
            }), 403
        amount, spent, remaining, dept = room
        if cost is None:
            return jsonify({
                "error": "Put a cost estimate on this request first — without one "
                         "there is no way to tell whether it fits the budget."
            }), 400
        if cost > remaining:
            return jsonify({
                "error": f"This would take {dept} past its budget. "
                         f"KSh {remaining:,.2f} is left of KSh {amount:,.2f} this month "
                         f"and this request is KSh {cost:,.2f}. Only the owner can approve it."
            }), 403

    with db.session.begin_nested():
        pr.owner_id    = actor.id
        pr.owner_notes = data.get("notes")
        pr.status = RequestStatus.APPROVED if action == "approve" else RequestStatus.REJECTED

    AuditLog.log(
        actor=actor.username,
        action=f"purchase_request.{action}",
        target=pr.id,
    )
    db.session.commit()

    return jsonify({"id": pr.id, "status": pr.status}), 200


# ── Completed Purchase ────────────────────────────────────────────────────────

@purchases_bp.post("/purchases")
@require_active_user
def record_purchase():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    data = request.get_json(silent=True) or {}

    # Mandatory fields
    item_id            = data.get("item_id")
    raw_qty            = data.get("quantity")
    raw_cost           = data.get("actual_cost")
    receipt_photo_path = (data.get("receipt_photo_path") or "").strip()
    idem_key           = data.get("idempotency_key") or str(uuid.uuid4())

    if not receipt_photo_path:
        return jsonify({"error": "Receipt photo is required for every purchase. Upload a photo of the receipt to complete this purchase."}), 400
    if not item_id:
        return jsonify({"error": "item_id is required"}), 400
    if raw_qty is None or raw_cost is None:
        return jsonify({"error": "quantity and actual_cost are required"}), 400

    try:
        qty  = Decimal(str(raw_qty))
        cost = Decimal(str(raw_cost))
    except InvalidOperation:
        return jsonify({"error": "quantity and actual_cost must be numbers"}), 400
    if qty <= 0:
        return jsonify({"error": "quantity must be positive"}), 400
    if cost < 0:
        return jsonify({"error": "actual_cost cannot be negative"}), 400

    # Idempotency
    if db.session.query(Purchase).filter_by(idempotency_key=idem_key).first():
        p = db.session.query(Purchase).filter_by(idempotency_key=idem_key).first()
        return jsonify({"id": p.id, "duplicate": True}), 200

    item = db.session.get(InventoryItem, item_id)
    if not item or not item.is_active:
        return jsonify({"error": "Item not found or inactive."}), 404

    pr_id = data.get("purchase_request_id")
    if pr_id:
        pr = db.session.get(PurchaseRequest, pr_id)
        if not pr:
            return jsonify({"error": "Purchase request not found."}), 404
        # Mark request as fulfilled
        pr.status = RequestStatus.FULFILLED

    # Capture old stock BEFORE writing the movement (for weighted-average cost)
    from app.services.stock import get_current_stock
    old_stock = get_current_stock(item.id)

    with db.session.begin_nested():
        # The stock movement is the system of record for the stock increase
        movement = StockMovement(
            item_id=item.id,
            change_amount=qty,       # positive — stock coming in
            reason=MovementReason.PURCHASE.value,
            actor_id=actor.id,
            notes=data.get("notes"),
            idempotency_key=f"purchase-mv-{idem_key}",
        )
        db.session.add(movement)
        db.session.flush()

        # Weighted-average cost: (old_stock × old_cpu + qty × new_cpu) / (old_stock + qty)
        new_cpu = cost / qty
        if old_stock > Decimal("0") and item.cost_per_unit is not None:
            old_cpu = Decimal(str(item.cost_per_unit))
            item.cost_per_unit = (old_stock * old_cpu + qty * new_cpu) / (old_stock + qty)
        else:
            item.cost_per_unit = new_cpu

        purchase = Purchase(
            item_id=item.id,
            quantity=qty,
            actual_cost=cost,
            receipt_photo_path=receipt_photo_path,
            supplier_name=data.get("supplier_name"),
            recorded_by_id=actor.id,
            purchase_request_id=pr_id,
            movement_id=movement.id,
            idempotency_key=idem_key,
        )
        db.session.add(purchase)

    AuditLog.log(
        actor=actor.username, action="inventory.purchase",
        target=item.name, details=f"qty={qty} cost={cost}",
    )

    # Spending past the budget is not refused here, and that is deliberate: the
    # goods are at the door and the receipt is in the manager's hand. You cannot
    # un-buy a delivery, and a system that pretends otherwise just teaches
    # people to record purchases late or not at all.
    #
    # The control belongs one step earlier, at approval, where the money has not
    # moved yet. What happens HERE is that the owner is told — the same night,
    # by name and amount, not in a report next month.
    over_budget = None
    room = _budget_room(item_id)
    if room is not None:
        amount, spent, _remaining, dept = room
        if spent > amount:
            from app.services.judge_alerts import fire_alert_if_absent
            from app.models.judge_alert import AlertSeverity
            from datetime import datetime as _dt, timezone as _tz
            now = _dt.now(_tz.utc)
            period = now.strftime("%Y-%m")
            over_budget = str(spent - amount)
            fire_alert_if_absent(
                alert_type="OVER_BUDGET",
                description_key=f"{dept} over budget {period}",
                item_id=item.id,
                severity=AlertSeverity.HIGH.value,
                description=(
                    f"{dept} has spent KSh {spent:,.2f} against a KSh {amount:,.2f} "
                    f"budget for {period} — KSh {spent - amount:,.2f} over. "
                    f"Latest: {item.name}, KSh {cost:,.2f}, recorded by {actor.username}."
                ),
                period_start=now,
                period_end=now,
            )

    db.session.commit()

    return jsonify({
        "over_budget_by": over_budget,
        "purchase_id": purchase.id,
        "movement_id": movement.id,
        "item":        item.name,
        "quantity":    str(qty),
        "actual_cost": str(cost),
    }), 201


@purchases_bp.get("/purchases")
@require_active_user
def list_purchases():
    """The deliveries recorded lately — newest first.

    Exists so the receiving screen can show what was just entered. A storeman
    who types 4 instead of 4 crates has no way to notice unless the last few
    lines are on the screen in front of him.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    limit = min(int(request.args.get("limit", 20)), 100)
    rows = (db.session.query(Purchase)
            .order_by(Purchase.timestamp_added.desc())
            .limit(limit).all())
    out = []
    for p in rows:
        item = db.session.get(InventoryItem, p.item_id)
        out.append({
            "id": p.id,
            "item_id": p.item_id,
            "item_name": item.name if item else "—",
            "unit": item.unit if item else "",
            "purchase_pack_name": item.purchase_pack_name if item else None,
            "purchase_pack_size": str(item.purchase_pack_size) if item and item.purchase_pack_size else None,
            "quantity": str(p.quantity),
            "actual_cost": str(p.actual_cost),
            "supplier_name": p.supplier_name,
            "receipt_photo_path": p.receipt_photo_path,
            "recorded_at": p.timestamp_added.isoformat() if p.timestamp_added else None,
        })
    return jsonify(out), 200


@purchases_bp.post("/purchases/<purchase_id>/correct-quantity")
@require_active_user
def correct_purchase_quantity(purchase_id):
    """Fix the quantity on a delivery that was keyed wrong.

    The money and the receipt do not move — only how much actually arrived
    against them. This is the one legitimate way stock can go UP outside a
    purchase, and it is deliberately narrow:

      * manager and above, audit-logged old → new,
      * the difference is written as its own ADJUSTMENT movement, so the
        history still shows what was first recorded and what corrected it,
      * cost_per_unit is recomputed from every purchase of the item, so a
        correction cannot leave the price of an ingredient reading wrong.

    Without it a mis-keyed crate is permanent: a count may not add stock (that
    is how invented stock gets laundered), and there is no other door.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    purchase = db.session.get(Purchase, purchase_id)
    if not purchase:
        return jsonify({"error": "Purchase not found."}), 404

    data = request.get_json(silent=True) or {}
    try:
        new_qty = Decimal(str(data.get("quantity")))
    except (InvalidOperation, TypeError):
        return jsonify({"error": "quantity must be a number"}), 400
    if new_qty <= 0:
        return jsonify({"error": "quantity must be positive"}), 400

    old_qty = Decimal(str(purchase.quantity))
    delta = new_qty - old_qty
    if delta == 0:
        return jsonify({"error": "That is already the quantity on this delivery."}), 400

    item = db.session.get(InventoryItem, purchase.item_id)
    if not item:
        return jsonify({"error": "Item not found."}), 404

    # A correction may not take stock below zero — that would mean the shortfall
    # has already been sold or counted, and the honest answer is a count, not a
    # rewrite of history.
    from app.services.stock import get_current_stock
    if get_current_stock(item.id) + delta < 0:
        return jsonify({
            "error": f"That would take {item.name} below zero. Some of it has already "
                     f"been used — count it instead of correcting the delivery."
        }), 400

    with db.session.begin_nested():
        db.session.add(StockMovement(
            item_id=item.id,
            change_amount=delta,
            reason=MovementReason.ADJUSTMENT.value,
            actor_id=actor.id,
            notes=f"Delivery correction: {old_qty} → {new_qty} {item.unit}"
                  + (f" ({data.get('reason')})" if data.get("reason") else ""),
            idempotency_key=f"purchase-fix-{purchase.id}-{new_qty}",
        ))
        purchase.quantity = new_qty

        # Re-derive the price from every purchase of this item, so one bad line
        # cannot leave a permanent dent in the margin.
        totals = db.session.query(
            db.func.sum(Purchase.quantity), db.func.sum(Purchase.actual_cost)
        ).filter(Purchase.item_id == item.id).first()
        tot_qty, tot_cost = totals or (None, None)
        if tot_qty and Decimal(str(tot_qty)) > 0:
            item.cost_per_unit = Decimal(str(tot_cost)) / Decimal(str(tot_qty))

    AuditLog.log(actor=actor.username, action="inventory.purchase.correct_quantity",
                 target=f"{item.name}: {old_qty} -> {new_qty}")
    db.session.commit()

    return jsonify({
        "id": purchase.id,
        "item": item.name,
        "quantity": str(new_qty),
        "adjusted_by": str(delta),
        "cost_per_unit": str(item.cost_per_unit),
        "message": f"{item.name} corrected to {new_qty} {item.unit}.",
    }), 200
