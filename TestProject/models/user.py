import uuid
from dataclasses import dataclass, field
from utils.validators import validate_email, validate_password


@dataclass
class User:
    username: str
    email: str
    password_hash: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    is_active: bool = True

    @classmethod
    def create(cls, username: str, email: str, password: str) -> "User":
        if not validate_email(email):
            raise ValueError(f"Invalid email: {email}")
        if not validate_password(password):
            raise ValueError("Password must be at least 6 characters")
        # 简单 hash，仅供演示
        password_hash = str(hash(password))
        return cls(username=username, email=email, password_hash=password_hash)

    def check_password(self, password: str) -> bool:
        return self.password_hash == str(hash(password))

    def __repr__(self) -> str:
        return f"User(username={self.username!r}, email={self.email!r})"
