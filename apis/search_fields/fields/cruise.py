import os
from datetime import datetime
from typing import List, Optional
import re

from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/cruise", tags=["cruise"])

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in your .env file")

client = AsyncIOMotorClient(MONGO_URI)
db = client['directory_db']
cruise_collection = db["cruise"]


# ================== Helper: Name se Slug generate karne ke liye ==================
def generate_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)   # special chars remove
    slug = re.sub(r'[\s-]+', '-', slug)        # spaces aur multiple - ko single - mein
    return slug.strip('-')


# ================== Pydantic Models ==================
class PhoneNumber(BaseModel):
    type: str = Field(..., description="e.g. main, reservations, customer-service, billing")
    number: str = Field(..., description="Phone number with country code if possible")
    extension: Optional[str] = None


class CruiseCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    category: str = "cruise"          # default category
    phone_numbers: List[PhoneNumber] = []
    website: Optional[str] = None
    email: Optional[str] = None
    description: Optional[str] = None
    hours: Optional[str] = None
    average_hold_time: Optional[int] = None   # in minutes
    best_time_to_call: Optional[str] = None
    phone_menu_tips: Optional[str] = None
    common_issues: List[str] = []
    notes: Optional[str] = None


class CruiseUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    phone_numbers: Optional[List[PhoneNumber]] = None
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

    class Config:
        from_attributes = True


# Helper function
def cruise_helper(doc) -> dict:
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


# ================== CRUD APIs ==================

@router.post("/", response_model=CruiseResponse, status_code=201)
async def create_cruise(data: CruiseCreate):
    """Naya Cruise Company / Support Entry add karo"""

    # Check duplicate name
    existing = await cruise_collection.find_one({"name": data.name})
    if existing:
        raise HTTPException(status_code=400, detail="This cruise company name already exists")

    cruise_dict = data.dict()
    cruise_dict["slug"] = generate_slug(data.name)
    cruise_dict["is_active"] = True
    cruise_dict["created_at"] = datetime.utcnow()
    cruise_dict["updated_at"] = datetime.utcnow()

    result = await cruise_collection.insert_one(cruise_dict)
    new_entry = await cruise_collection.find_one({"_id": result.inserted_id})

    return cruise_helper(new_entry)


@router.get("/", response_model=List[CruiseResponse])
async def get_all_cruises(skip: int = 0, limit: int = 50):
    """Saari active cruise entries"""
    cursor = cruise_collection.find({"is_active": True}).skip(skip).limit(limit)
    entries = [cruise_helper(doc) async for doc in cursor]
    return entries


@router.get("/search", response_model=List[CruiseResponse])
async def search_cruises(q: str):
    """Name ya slug se search"""
    cursor = cruise_collection.find({
        "$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"slug": {"$regex": q, "$options": "i"}}
        ],
        "is_active": True
    })
    entries = [cruise_helper(doc) async for doc in cursor]
    return entries


@router.get("/{entry_id}", response_model=CruiseResponse)
async def get_cruise_by_id(entry_id: str):
    try:
        obj_id = ObjectId(entry_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID")

    entry = await cruise_collection.find_one({"_id": obj_id})
    if not entry:
        raise HTTPException(status_code=404, detail="Cruise entry not found")
    
    return cruise_helper(entry)


@router.put("/{entry_id}", response_model=CruiseResponse)
async def update_cruise(entry_id: str, update_data: CruiseUpdate):
    try:
        obj_id = ObjectId(entry_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID")

    update_dict = {k: v for k, v in update_data.dict().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No update data provided")

    if "name" in update_dict:
        update_dict["slug"] = generate_slug(update_dict["name"])

    update_dict["updated_at"] = datetime.utcnow()

    result = await cruise_collection.update_one({"_id": obj_id}, {"$set": update_dict})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cruise entry not found")

    updated = await cruise_collection.find_one({"_id": obj_id})
    return cruise_helper(updated)


@router.delete("/{entry_id}")
async def delete_cruise(entry_id: str):
    try:
        obj_id = ObjectId(entry_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID")

    result = await cruise_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cruise entry not found")

    return {"message": "Cruise entry deleted successfully"}


# Soft Delete
@router.patch("/{entry_id}/deactivate")
async def deactivate_cruise(entry_id: str):
    try:
        obj_id = ObjectId(entry_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID")

    result = await cruise_collection.update_one(
        {"_id": obj_id},
        {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cruise entry not found")

    return {"message": "Cruise entry deactivated successfully"}