import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.database import SessionLocal, User, EnrollmentRun, EnrolledCourse

def sync_stats():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for user in users:
            print(f"Syncing stats for user: {user.email}")
            stats = (
                db.query(
                    func.sum(EnrollmentRun.successfully_enrolled).label("total_enrolled"),
                    func.sum(EnrollmentRun.amount_saved).label("total_amount_saved"),
                    func.sum(EnrollmentRun.already_enrolled).label("total_already_enrolled"),
                    func.sum(EnrollmentRun.expired).label("total_expired"),
                    func.sum(EnrollmentRun.excluded).label("total_excluded"),
                )
                .filter(EnrollmentRun.user_id == user.id)
                .first()
            )
            
            user.total_enrolled = int(stats.total_enrolled or 0)
            user.total_amount_saved = float(stats.total_amount_saved or 0)
            user.total_already_enrolled = int(stats.total_already_enrolled or 0)
            user.total_expired = int(stats.total_expired or 0)
            user.total_excluded = int(stats.total_excluded or 0)
            
            db.commit()
            print(f"Updated user {user.email}: {user.total_enrolled} enrolled, ${user.total_amount_saved} saved.")
    finally:
        db.close()

if __name__ == "__main__":
    sync_stats()