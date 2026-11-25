from abc import ABC, abstractmethod


class UserDirectoryPort(ABC):
    @abstractmethod
    async def role_of(self, email: str) -> str | None: ...
