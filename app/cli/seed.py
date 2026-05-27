"""
seed.py — CLI commands for bootstrapping the database.

Usage:
  flask seed owner          → creates the first owner account interactively
  flask seed roles-depts    → seeds default roles and departments

Run once after `flask db upgrade` on a fresh database.
"""
import click
from flask import Blueprint
from app.extensions import db
from app.models.department import Department
from app.models.role import Role
from app.models.user import User
from app.models.audit_log import AuditLog

seed_bp = Blueprint("seed", __name__)


@seed_bp.cli.command("roles-depts")
def seed_roles_departments():
    """Create default roles (owner/manager/staff) and departments."""
    # Roles: level=10 owner, level=5 manager, level=1 staff
    default_roles = [
        {"name": "owner",   "level": 10},
        {"name": "manager", "level": 5},
        {"name": "staff",   "level": 1},
    ]
    for r in default_roles:
        if not db.session.query(Role).filter_by(name=r["name"]).first():
            db.session.add(Role(name=r["name"], level=r["level"]))
            click.echo(f"  Created role: {r['name']} (level {r['level']})")
        else:
            click.echo(f"  Role already exists: {r['name']}")

    default_departments = ["General", "Kitchen", "Bar", "Front-of-House", "Finance"]
    for d in default_departments:
        if not db.session.query(Department).filter_by(name=d).first():
            db.session.add(Department(name=d))
            click.echo(f"  Created department: {d}")
        else:
            click.echo(f"  Department already exists: {d}")

    db.session.commit()
    click.echo("Done.")


@seed_bp.cli.command("owner")
@click.option("--username", prompt="Owner username", help="Username for the first owner")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Owner password")
def seed_owner(username, password):
    """Create the first owner account. Run this once on a fresh DB."""
    owner_role = db.session.query(Role).filter_by(name="owner").first()
    if not owner_role:
        click.echo("Run `flask seed roles-depts` first to create roles.")
        return

    existing = db.session.query(User).filter_by(username=username.strip().lower()).first()
    if existing:
        click.echo(f"User '{username}' already exists.")
        return

    general_dept = db.session.query(Department).filter_by(name="General").first()

    user = User(
        username=username.strip().lower(),
        role_id=owner_role.id,
        department_id=general_dept.id if general_dept else None,
        is_active=True,
    )
    user.set_password(password)

    db.session.add(user)
    db.session.flush()  # get the user.id before AuditLog references it

    AuditLog.log(actor=user.username, action="user.create", target=user.username, details="initial owner seed")
    db.session.commit()

    click.echo(f"Owner '{user.username}' created successfully.")
    click.echo("Log in via POST /auth/login and set your PIN via POST /auth/set-pin.")
