
import sys
import os
from sqlalchemy import text
from app.models.database import SessionLocal

def check_exclusions():
    db = SessionLocal()
    try:
        # Get latest run ID
        latest_run = db.execute(text("SELECT id FROM enrollment_runs ORDER BY id DESC LIMIT 1")).fetchone()
        if not latest_run:
            print("No runs found.")
            return
            
        run_id = latest_run[0]
        print(f"Checking exclusions for Run ID: {run_id}")
        
        query = text("""
            SELECT status, error_message, COUNT(*) as count 
            FROM enrolled_courses 
            WHERE enrollment_run_id = :run_id AND status='excluded' 
            GROUP BY error_message
        """)
        results = db.execute(query, {"run_id": run_id}).fetchall()
        
        print(f"{'Status':<10} | {'Reason':<60} | {'Count':<5}")
        print("-" * 80)
        for row in results:
            status, reason, count = row
            print(f"{status:<10} | {str(reason):<60} | {count:<5}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_exclusions()
