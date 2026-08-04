import argparse

from app.db.database import SessionLocal
from app.models.user import User
from app.security.password import hash_password
from app.services.auth_service import get_user_by_email, get_user_by_username


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first Khan Cloud superuser.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    with SessionLocal() as db:
        user = get_user_by_email(db, args.email) or get_user_by_username(
            db, args.username
        )
        if user:
            user.email = args.email.lower()
            user.username = args.username
            user.full_name = args.full_name
            user.password_hash = hash_password(args.password)
            user.is_active = True
            user.is_superuser = True
            db.commit()
            print(f"Updated superuser: {user.username}")
            return

        user = User(
            email=args.email.lower(),
            username=args.username,
            full_name=args.full_name,
            password_hash=hash_password(args.password),
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        db.commit()
        print(f"Created superuser: {user.username}")


if __name__ == "__main__":
    main()
