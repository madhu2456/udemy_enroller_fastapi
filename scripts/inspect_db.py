from app.models.database import SessionLocal, UserSettings
import json

db = SessionLocal()
try:
    settings = db.query(UserSettings).all()
    print(f"Total UserSettings records: {len(settings)}")
    for s in settings:
        print(f"User ID: {s.user_id}")
        print(f"Sites: {json.dumps(s.sites, indent=2)}")
        print(f"Languages: {json.dumps(s.languages, indent=2)}")
        print(f"Categories: {json.dumps(s.categories, indent=2)}")
finally:
    db.close()
