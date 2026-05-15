from pydantic import BaseModel


class UserProfileContext(BaseModel):
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None


class RuntimeContext(BaseModel):
    user_profile: UserProfileContext | None = None
