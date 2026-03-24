import secrets
from models.user import User
from utils.logger import log


class AuthService:
    def __init__(self):
        self._users: dict[str, User] = {}  # username -> User
        self._tokens: dict[str, str] = {}  # token -> username

    def register(self, username: str, email: str, password: str) -> User:
        if username in self._users:
            raise ValueError(f"Username '{username}' already exists")

        user = User.create(username, email, password)
        self._users[username] = user
        log(f"User registered: {username}")
        return user

    def login(self, username: str, password: str) -> str | None:
        user = self._users.get(username)
        if not user:
            log(f"Login failed: user '{username}' not found")
            return None

        if not user.is_active:
            log(f"Login failed: user '{username}' is deactivated")
            return None

        if not user.check_password(password):
            log(f"Login failed: wrong password for '{username}'")
            return None

        token = secrets.token_hex(16)
        self._tokens[token] = username
        log(f"User logged in: {username}")
        return token

    def get_user_by_token(self, token: str) -> User | None:
        username = self._tokens.get(token)
        if not username:
            return None
        return self._users.get(username)

    def logout(self, token: str) -> bool:
        if token in self._tokens:
            username = self._tokens.pop(token)
            log(f"User logged out: {username}")
            return True
        return False
