from sqlalchemy.orm import Session

from app.models.api_key import APIKey
from app.repositories.base import BaseRepository


class APIKeyRepository(BaseRepository[APIKey]):
    def __init__(self, db: Session):
        super().__init__(APIKey, db)

    def get_by_hash(self, key_hash: str) -> APIKey | None:
        return self.db.query(APIKey).filter(APIKey.key_hash == key_hash).first()

    def get_by_user(self, user_id: int) -> list[APIKey]:
        return self.db.query(APIKey).filter(APIKey.user_id == user_id).all()

    def get_by_id_and_user(self, key_id: int, user_id: int) -> APIKey | None:
        return (
            self.db.query(APIKey)
            .filter(APIKey.id == key_id, APIKey.user_id == user_id)
            .first()
        )

    def update(self, api_key: APIKey, **fields) -> APIKey:
        for k, v in fields.items():
            setattr(api_key, k, v)
        self.db.commit()
        self.db.refresh(api_key)
        return api_key
