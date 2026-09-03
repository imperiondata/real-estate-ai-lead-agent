import secrets
import string
import models
from auth import get_password_hash
from database import SessionLocal, engine

def seed_client_b():
    print("=" * 50)
    print("  SEEDING CLIENT B HOLDINGS (NON-INTERACTIVE)")
    print("=" * 50)

    # Ensure tables are created
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        company_name = "Client B Holdings"
        email = "admin@clientbholdings.com"
        
        existing = db.query(models.Client).filter_by(email=email).first()
        if existing:
            print(f"[*] Client '{email}' already exists!")
            print(f"[*] API Key: {existing.api_key}")
            return

        alphabet = string.ascii_letters + string.digits
        raw_password = ''.join(secrets.choice(alphabet) for i in range(12))
        hashed_password = get_password_hash(raw_password)
        api_key = secrets.token_hex(32)

        new_client = models.Client(
            company_name=company_name,
            email=email,
            hashed_password=hashed_password,
            api_key=api_key
        )
        db.add(new_client)
        db.flush()

        default_manager = models.Agent(
            client_id=new_client.id,
            name=f"{company_name} Admin",
            phone="+910000000000",
            email=email,
            is_manager=True
        )
        db.add(default_manager)
        db.commit()

        print("\n✅ SUCCESS: CLIENT B PROVISIONED")
        print(f"  Company Name   : {new_client.company_name}")
        print(f"  Login Email    : {new_client.email}")
        print(f"  Login Password : {raw_password}")
        print(f"  Twilio API Key : {new_client.api_key}")
        print("=" * 50 + "\n")

    except Exception as e:
        print(f"\n❌ DATABASE ERROR: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_client_b()
