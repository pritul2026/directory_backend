import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

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

SUPER_ADMIN_USERNAME = "admin_creative_volt"
SUPER_ADMIN_PASSWORD = "YourStrongPassword123!"  # Change this to strong password

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


class AdminCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    password: str = Field(..., min_length=6)
    confirm_password: str


class AdminResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    role: str = "admin"
    created_at: datetime
    created_by: str


class SuperAdminResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "superadmin"
    created_at: datetime


# ✅ YEH CLASS IMPORTANT HAI - Airlines aur Cruise files ke liye
class UserInDB(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    hashed_password: str
    disabled: bool = False
    role: str  # "superadmin" or "admin"
    created_at: datetime
    created_by: Optional[str] = None
    
    class Config:
        from_attributes = True


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


async def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Returns user dict with 'id' field"""
    user = await users_collection.find_one({"username": username})
    if user:
        user["id"] = str(user.pop("_id"))
        return user
    return None


# ✅ YEH FUNCTION AB UserInDB RETURN KAREGA
async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
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
    
    # Convert to UserInDB object
    return UserInDB(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        full_name=user.get("full_name"),
        hashed_password=user["hashed_password"],
        disabled=user.get("disabled", False),
        role=user["role"],
        created_at=user["created_at"],
        created_by=user.get("created_by")
    )


def require_superadmin(current_user: UserInDB):
    """Sirf superadmin ko allow"""
    if current_user.role == "superadmin":
        return True
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Super Admin privileges required."
    )


def require_admin(current_user: UserInDB):
    """Admin ya superadmin ko allow"""
    if current_user.role in ["admin", "superadmin"]:
        return True
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Authentication required."
    )


# ========================= INITIAL SETUP =========================
async def init_superadmin():
    """Pehli baar server start ho to superadmin create ho jaaye"""
    existing = await users_collection.find_one({"username": SUPER_ADMIN_USERNAME})
    if not existing:
        hashed_password = get_password_hash(SUPER_ADMIN_PASSWORD)
        superadmin_dict = {
            "username": SUPER_ADMIN_USERNAME,
            "email": "superadmin@example.com",
            "full_name": "Super Admin",
            "hashed_password": hashed_password,
            "role": "superadmin",
            "disabled": False,
            "created_at": datetime.utcnow(),
            "created_by": "system"
        }
        await users_collection.insert_one(superadmin_dict)
        print(f"✅ Superadmin created: {SUPER_ADMIN_USERNAME}")
        print(f"⚠️  Password: {SUPER_ADMIN_PASSWORD}")
    else:
        print("✅ Superadmin already exists")


# ========================= PUBLIC ROUTES =========================

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Superadmin ya admin login kar sakte hain"""
    user = await get_user_by_username(form_data.username)
    
    if not user or not verify_password(form_data.password, user.get("hashed_password")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user["username"]})
    refresh_token = create_refresh_token(data={"sub": user["username"]})

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


# ====================== SUPER ADMIN ONLY ======================

@router.post("/create-admin", response_model=AdminResponse)
async def create_admin(
    admin_data: AdminCreate,
    current_user: UserInDB = Depends(get_current_user)
):
    """Sirf Super Admin hi naya admin create kar sakta hai"""
    require_superadmin(current_user)
    
    # Check passwords match
    if admin_data.password != admin_data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    # Check if username exists
    existing = await users_collection.find_one({"username": admin_data.username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Check if email exists
    existing_email = await users_collection.find_one({"email": admin_data.email})
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # Create admin
    hashed_password = get_password_hash(admin_data.password)
    admin_dict = {
        "username": admin_data.username,
        "email": admin_data.email,
        "full_name": admin_data.full_name,
        "hashed_password": hashed_password,
        "role": "admin",
        "disabled": False,
        "created_at": datetime.utcnow(),
        "created_by": current_user.username  # Super admin ka username
    }
    
    result = await users_collection.insert_one(admin_dict)
    new_admin = await users_collection.find_one({"_id": result.inserted_id})
    
    return AdminResponse(
        id=str(new_admin["_id"]),
        username=new_admin["username"],
        email=new_admin["email"],
        full_name=new_admin.get("full_name"),
        role="admin",
        created_at=new_admin["created_at"],
        created_by=new_admin["created_by"]
    )


@router.get("/admins", response_model=List[AdminResponse])
async def get_all_admins(current_user: UserInDB = Depends(get_current_user)):
    """Saare admins ki list - Sirf Super Admin dekh sakta hai"""
    require_superadmin(current_user)
    
    cursor = users_collection.find({"role": "admin"})
    admins = []
    async for doc in cursor:
        admins.append(AdminResponse(
            id=str(doc["_id"]),
            username=doc["username"],
            email=doc["email"],
            full_name=doc.get("full_name"),
            role="admin",
            created_at=doc["created_at"],
            created_by=doc.get("created_by", "unknown")
        ))
    return admins


@router.get("/admin/{admin_id}")
async def get_admin_by_id(
    admin_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """Kisi specific admin ki details - Sirf Super Admin"""
    require_superadmin(current_user)
    
    try:
        obj_id = ObjectId(admin_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid admin ID")
    
    admin = await users_collection.find_one({"_id": obj_id, "role": "admin"})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    return AdminResponse(
        id=str(admin["_id"]),
        username=admin["username"],
        email=admin["email"],
        full_name=admin.get("full_name"),
        role="admin",
        created_at=admin["created_at"],
        created_by=admin.get("created_by", "unknown")
    )


@router.delete("/admin/{admin_id}")
async def delete_admin(
    admin_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """Admin ko delete karo - Sirf Super Admin"""
    require_superadmin(current_user)
    
    try:
        obj_id = ObjectId(admin_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid admin ID")
    
    # Check if admin exists
    admin = await users_collection.find_one({"_id": obj_id, "role": "admin"})
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    # Delete
    await users_collection.delete_one({"_id": obj_id})
    return {"message": f"Admin {admin['username']} deleted successfully"}


@router.patch("/admin/{admin_id}/reset-password")
async def reset_admin_password(
    admin_id: str,
    new_password: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """Admin ka password reset karo - Sirf Super Admin"""
    require_superadmin(current_user)
    
    try:
        obj_id = ObjectId(admin_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid admin ID")
    
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    hashed_password = get_password_hash(new_password)
    result = await users_collection.update_one(
        {"_id": obj_id, "role": "admin"},
        {"$set": {"hashed_password": hashed_password, "updated_at": datetime.utcnow()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    return {"message": "Password reset successfully"}


# ====================== ADMIN AND SUPER ADMIN ROUTES ======================

@router.get("/me", response_model=UserInDB)
async def get_current_user_info(current_user: UserInDB = Depends(get_current_user)):
    """Apni info dekh sakta hai (admin ya superadmin)"""
    require_admin(current_user)
    return current_user


@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    confirm_password: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """Apna password change karo (admin ya superadmin)"""
    require_admin(current_user)
    
    # Verify old password
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Old password is incorrect")
    
    # Check new password
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match")
    
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    # Update password
    hashed_password = get_password_hash(new_password)
    await users_collection.update_one(
        {"username": current_user.username},
        {"$set": {"hashed_password": hashed_password, "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Password changed successfully"}