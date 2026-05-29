"""
WristbandCounter — per-day atomic band number allocator.
One row per issue_date (primary key). next_number is incremented under a row lock
on each allocation, ensuring no two bands get the same number on the same day.
"""
from app.extensions import db


class WristbandCounter(db.Model):
    __tablename__ = "wristband_counters"

    # The date string IS the primary key — one row per day
    issue_date  = db.Column(db.String(10), primary_key=True)   # "YYYY-MM-DD"
    next_number = db.Column(db.Integer, nullable=False, default=1)

    def __repr__(self):
        return f"<WristbandCounter {self.issue_date} next={self.next_number}>"
