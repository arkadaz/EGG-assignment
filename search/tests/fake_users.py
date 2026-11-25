from app.application.ports.users import UserDirectoryPort


class FakeUserDirectory(UserDirectoryPort):
    def __init__(self, roles: dict[str, str]) -> None:
        self.roles = roles

    async def role_of(self, email: str) -> str | None:
        return self.roles.get(email)
