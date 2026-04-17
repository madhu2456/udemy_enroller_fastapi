import os
import sys
sys.path.append('.')
from app.models.database import SessionLocal, EnrollmentRun

def check_runs():
    with SessionLocal() as db:
        runs = db.query(EnrollmentRun).all()
        print(f"Total enrollment runs: {len(runs)}")
        for run in runs:
            print(f"Run ID: {run.id}, Status: {run.status}, Started: {run.started_at}, Finished: {run.completed_at}")

if __name__ == "__main__":
    check_runs()
