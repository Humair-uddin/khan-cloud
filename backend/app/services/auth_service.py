from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate
from app.security.password import hash_password, verify_password


class AuthConflictError(ValueError):
    pass


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_user_by_login(db: Session, login: str) -> User | None:
    value = login.strip()
    return db.scalar(
        select(User).where(
            or_(User.email == value.lower(), User.username == value)
        )
    )


def register_user(db: Session, payload: UserCreate) -> User:
    if get_user_by_email(db, payload.email):
        raise AuthConflictError("Email is already registered.")
    if get_user_by_username(db, payload.username):
        raise AuthConflictError("Username is already registered.")

    user = User(
        email=payload.email.lower(),
        username=payload.username,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, login: str, password: str) -> User | None:
    user = get_user_by_login(db, login)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
