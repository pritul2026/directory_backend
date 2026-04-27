import os
from datetime import datetime
from typing import List, Optional
import re

from fastapi import APIRouter, HTTPException, Depends, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from bson import ObjectId
from dotenv import load_dotenv

from apis.auth.auth import get_current_user, UserInDB

load_dotenv()

router = APIRouter(prefix="/cruise", tags=["cruise"])

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in your .env file")

client = AsyncIOMotorClient(MONGO_URI)
db = client['directory_db']
cruise_collection = db["cruise"]


# ================== Slug Generator ==================
def generate_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')


# ================== Pydantic Models ==================
class CruiseCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    category: str = "cruise"
    phone: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    description: Optional[str] = None
    hours: Optional[str] = None
    average_hold_time: Optional[int] = None
    best_time_to_call: Optional[str] = None
    phone_menu_tips: Optional[str] = None
    common_issues: List[str] = []
    notes: Optional[str] = None


class CruiseUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    description: Optional[str] = None
    hours: Optional[str] = None
    average_hold_time: Optional[int] = None
    best_time_to_call: Optional[str] = None
    phone_menu_tips: Optional[str] = None
    common_issues: Optional[List[str]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CruiseResponse(CruiseCreate):
    id: str
    slug: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    # Extra fields
    address: Optional[str] = ""
    city: Optional[str] = ""
    state: Optional[str] = ""
    country: Optional[str] = ""
    zip_code: Optional[str] = ""

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True
        json_encoders = {
            str: lambda v: v if v is not None else ""
        }


# ================== Helper Function ==================
def cruise_helper(doc) -> dict:
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    
    # Default values for missing fields
    doc.setdefault("address", "")
    doc.setdefault("city", "")
    doc.setdefault("state", "")
    doc.setdefault("country", "")
    doc.setdefault("zip_code", "")
    doc.setdefault("slug", generate_slug(doc.get("name", "")))
    doc.setdefault("common_issues", [])
    
    if "description" in doc and doc["description"]:
        doc["description"] = str(doc["description"]).strip()
    
    return doc


# ====================== PUBLIC ROUTES ======================

@router.get("/", response_model=List[CruiseResponse])
async def get_all_cruises(
    skip: int = 0, 
    limit: int = 50,
    show_all: bool = Query(False, description="Show both active and inactive cruises")
):
    """Saari cruises - show_all=true se inactive bhi aa jayenge"""
    query = {} if show_all else {"is_active": True}
    
    cursor = cruise_collection.find(query).skip(skip).limit(limit)
    entries = [cruise_helper(doc) async for doc in cursor]
    return entries


@router.get("/search", response_model=List[dict])
async def search_cruises(q: str):
    """Search only active cruises"""
    cursor = cruise_collection.find({
        "$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"slug": {"$regex": q, "$options": "i"}}
        ],
        "is_active": True
    })
    
    entries = []
    async for doc in cursor:
        entries.append({
            "id": str(doc["_id"]),
            "slug": doc.get("slug", ""),
            "name": doc.get("name", ""),
            "category": doc.get("category", "cruise")
        })
    return entries


@router.get("/{entry_id}", response_model=CruiseResponse)
async def get_cruise_by_id(entry_id: str):
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    entry = await cruise_collection.find_one({"_id": obj_id})
    if not entry:
        raise HTTPException(status_code=404, detail="Cruise not found")
    
    return cruise_helper(entry)


@router.get("/slug/{slug}", response_model=CruiseResponse)
async def get_cruise_by_slug(slug: str):
    if not slug or not slug.strip():
        raise HTTPException(status_code=400, detail="Slug cannot be empty")
    
    entry = await cruise_collection.find_one({
        "slug": slug.strip().lower(),
        "is_active": True
    })
    
    if not entry:
        raise HTTPException(status_code=404, detail=f"No cruise found with slug '{slug}'")
    
    return cruise_helper(entry)


# ====================== PROTECTED ROUTES ======================

@router.post("/", response_model=CruiseResponse, status_code=201)
async def create_cruise(
    data: CruiseCreate, 
    current_user: UserInDB = Depends(get_current_user)
):
    existing = await cruise_collection.find_one({"name": data.name})
    if existing:
        raise HTTPException(status_code=400, detail="This cruise name already exists")

    cruise_dict = data.dict()
    cruise_dict["slug"] = generate_slug(data.name)
    cruise_dict["is_active"] = True
    cruise_dict["created_at"] = datetime.utcnow()
    cruise_dict["updated_at"] = datetime.utcnow()
    
    # Extra fields default
    cruise_dict.setdefault("address", "")
    cruise_dict.setdefault("city", "")
    cruise_dict.setdefault("state", "")
    cruise_dict.setdefault("country", "")
    cruise_dict.setdefault("zip_code", "")

    result = await cruise_collection.insert_one(cruise_dict)
    new_entry = await cruise_collection.find_one({"_id": result.inserted_id})
    
    return cruise_helper(new_entry)


@router.put("/{entry_id}", response_model=CruiseResponse)
async def update_cruise(
    entry_id: str, 
    update_data: CruiseUpdate,
    current_user: UserInDB = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    update_dict = {k: v for k, v in update_data.dict().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No update data provided")

    if "name" in update_dict:
        update_dict["slug"] = generate_slug(update_dict["name"])

    update_dict["updated_at"] = datetime.utcnow()

    result = await cruise_collection.update_one({"_id": obj_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cruise not found")

    updated = await cruise_collection.find_one({"_id": obj_id})
    return cruise_helper(updated)


@router.delete("/{entry_id}")
async def delete_cruise(
    entry_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    result = await cruise_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cruise not found")

    return {"message": "Cruise deleted successfully"}


@router.patch("/{entry_id}/deactivate")
async def deactivate_cruise(
    entry_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    result = await cruise_collection.update_one(
        {"_id": obj_id},
        {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cruise not found")

    return {"message": "Cruise deactivated successfully"}