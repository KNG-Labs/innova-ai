from __future__ import annotations

from uuid import UUID


class InnovaAIError(Exception):
    """Базовое исключение"""


class SessionOwnershipError(InnovaAIError):
    """
    Попытка использовать сессию, принадлежащую другому пользователю.

    Возникает, когда клиент передал session_id, но текущий
    анонимный пользователь (channel + anonymous_id) не является
    владельцем этой сессии.
    """

    def __init__(self, *, session_id: UUID, user_id: UUID) -> None:
        self.session_id = session_id
        self.user_id = user_id
        super().__init__(
            f"Session {session_id} does not belong to user {user_id}"
        )