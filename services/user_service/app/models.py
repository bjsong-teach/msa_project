from typing import Optional
from sqlmodel import Field, SQLModel, col

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    email: str = Field(unique=True, index=True)
    hashed_password: str
    bio: Optional[str] = None
    profile_image_filename: Optional[str] = None

class UserCreate(SQLModel):
    username: str
    email: str
    password: str
    bio: Optional[str] = None
    
class UserUpdate(SQLModel):
    username: Optional[str] = None
    bio: Optional[str] = None

class UserPublic(SQLModel):
    id: int
    username: str
    email: str
    bio: Optional[str] = None
    profile_image_url: Optional[str] = None

class PasswordUpdate(SQLModel):
    current_password: str
    new_password: str    
class Userlogin(SQLModel):
    email : str
    password : str