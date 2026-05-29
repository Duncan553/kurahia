"""
ConductRule — versioned code-of-conduct rule.
A "change" creates a NEW version row with is_active=True and the previous
version set to is_active=False. History is never lost.
rule_key groups versions of the same rule (e.g. "punctuality-policy").
"""
import uuid
import enum
from datetime import datetime, timezone
from app.extensions import db


class RuleCategory(str, enum.Enum):
    RESPECT         = "RESPECT"
    PUNCTUALITY     = "PUNCTUALITY"
    SAFETY          = "SAFETY"
    CONFIDENTIALITY = "CONFIDENTIALITY"
    GENERAL         = "GENERAL"


class ConductRule(db.Model):
    __tablename__ = "conduct_rules"

    id        = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_key  = db.Column(db.String(80),  nullable=False, index=True)  # slug — same across versions
    version   = db.Column(db.Integer,    nullable=False, default=1)
    title     = db.Column(db.String(200), nullable=False)
    body      = db.Column(db.Text,        nullable=False)  # markdown
    category  = db.Column(db.String(20),  nullable=False)
    is_active = db.Column(db.Boolean,     nullable=False, default=True)

    created_by_id  = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    created_by = db.relationship("User", foreign_keys=[created_by_id], lazy="select")
    signatures = db.relationship("ConductSignature", back_populates="rule",
                                 lazy="dynamic")

    __table_args__ = (
        db.UniqueConstraint("rule_key", "version", name="uq_conduct_rule_key_version"),
        db.CheckConstraint("version > 0", name="ck_conduct_rule_version_pos"),
    )

    def __repr__(self):
        return f"<ConductRule {self.rule_key!r} v{self.version} active={self.is_active}>"
