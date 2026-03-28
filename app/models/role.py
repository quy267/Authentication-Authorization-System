from beanie import Document, Indexed


class Role(Document):
    """Role document for RBAC."""

    name: Indexed(str, unique=True)
    permissions: list[str] = []
    description: str | None = None

    class Settings:
        name = "roles"
