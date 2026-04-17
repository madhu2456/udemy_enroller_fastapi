
import sys
import os
from sqlalchemy import text
from app.models.database import SessionLocal

def check_exclusions():
    db = SessionLocal()
    try:
        query = text("""
            SELECT status, error_message, COUNT(*) as count 
            FROM enrolled_courses 
            WHERE status='excluded' 
            GROUP BY error_message
        """)
        results = db.execute(query).fetchall()
        
        print(f"{'Status':<10} | {'Reason':<60} | {'Count':<5}")
        print("-" * 80)
        for row in results:
            status, reason, count = row
            print(f"{status:<10} | {str(reason):<60} | {count:<5}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_exclusions()
