from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: Session):
        super().__init__(User, db)

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def get_by_username(self, username: str) -> User | None:
        return self.db.query(User).filter(User.username == username).first()

    def get_by_verification_token(self, token_hash: str) -> User | None:
        return self.db.query(User).filter(User.verification_token == token_hash).first()

    def get_by_reset_token(self, token_hash: str) -> User | None:
        return self.db.query(User).filter(User.reset_token == token_hash).first()

    def update(self, user: User, **fields) -> User:
        for key, value in fields.items():
            setattr(user, key, value)
        self.db.commit()
        self.db.refresh(user)
        return user
