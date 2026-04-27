import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

load_dotenv()

router = APIRouter(prefix="/auth", tags=["auth"])

# ========================= CONFIG =========================
SECRET_KEY = os.getenv("SECRET_KEY")
MONGO_URI = os.getenv("MONGO_URI")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set in .env file")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in .env file")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 3
REFRESH_TOKEN_EXPIRE_DAYS = 30

SUPER_ADMIN_USERNAME = "admin_creative_volt"   # Yeh sirf ek hi superadmin rahega

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# MongoDB Connection
client = AsyncIOMotorClient(MONGO_URI)
db = client['directory_db']
users_collection = db["users"]


# ========================= MODELS =========================
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: str
    confirm_password: str = Field(..., description="Must match with password")


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: bool = False
    created_at: Optional[datetime] = None
    is_superadmin: bool = False


class UserInDB(UserResponse):
    hashed_password: str


# ========================= HELPERS =========================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_user_by_username(username: str):
    user = await users_collection.find_one({"username": username})
    if user:
        user["id"] = str(user.pop("_id"))
        return UserInDB(**user)
    return None


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await get_user_by_username(username)
    if user is None:
        raise credentials_exception
    return user


def require_superadmin(current_user: UserInDB):
    """Strict check - Sirf admin_creative_volt ko hi allow"""
    if current_user.username == SUPER_ADMIN_USERNAME:
        return True
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Super Admin privileges required. Only admin_creative_volt is allowed."
    )


# ========================= ROUTES =========================

@router.post("/register", response_model=UserResponse)
async def register(user: UserCreate):
    if user.password != user.confirm_password:
        raise HTTPException(
            status_code=400,
            detail="Password and confirm password do not match"
        )

    # Username already exists check
    existing_user = await users_collection.find_one({"username": user.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    if user.email:
        existing_email = await users_collection.find_one({"email": user.email})
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password)

    is_superadmin = (user.username == SUPER_ADMIN_USERNAME)

    user_dict = {
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "hashed_password": hashed_password,
        "disabled": False,
        "is_superadmin": is_superadmin,
        "created_at": datetime.utcnow()
    }

    result = await users_collection.insert_one(user_dict)
    new_user = await users_collection.find_one({"_id": result.inserted_id})
    new_user["id"] = str(new_user.pop("_id"))

    return UserResponse(**{k: v for k, v in new_user.items() if k in UserResponse.model_fields})


@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await get_user_by_username(form_data.username)
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: str):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
    )
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or payload.get("type") != "refresh":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await get_user_by_username(username)
    if not user:
        raise credentials_exception

    new_access = create_access_token(data={"sub": username})
    new_refresh = create_refresh_token(data={"sub": username})

    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user


# ====================== SUPER ADMIN ONLY ======================

@router.get("/users", response_model=List[UserResponse])
async def get_all_users(current_user: UserInDB = Depends(get_current_user)):
    """Saare users ki list - Sirf admin_creative_volt ko allowed"""
    require_superadmin(current_user)

    cursor = users_collection.find({})
    users = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        users.append(UserResponse(**{k: v for k, v in doc.items() if k in UserResponse.model_fields}))
    return users


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: UserInDB = Depends(get_current_user)):
    """Kisi user ko delete karo - Sirf Super Admin"""
    require_superadmin(current_user)

    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    # Khud ko delete nahi kar sakta
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")

    result = await users_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deleted successfully"}