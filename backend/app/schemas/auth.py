"""Authentication and user session schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    """Authenticated user profile representation."""

    id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "farmer"
    phone_number: Optional[str] = None
    preferred_language: str = "en"
