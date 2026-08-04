from app.db.database import SessionLocal
from app.services.rbac_service import seed_default_rbac


def main() -> None:
    with SessionLocal() as db:
        seed_default_rbac(db)
    print("Default RBAC roles and permissions seeded.")


if __name__ == "__main__":
    main()
