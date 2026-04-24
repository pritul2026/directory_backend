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

router = APIRouter(prefix="/airlines", tags=["airlines"])

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in your .env file")

client = AsyncIOMotorClient(MONGO_URI)
db = client['directory_db']
airlines_collection = db["airlines"]


# ================== Helper: Name se Slug generate ==================
def generate_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')


# ================== Pydantic Models ==================
class AirlineCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    category: str = "airline"
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


class AirlineUpdate(BaseModel):
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


class AirlineResponse(AirlineCreate):
    id: str
    slug: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ================== Helper Function ==================
def airline_helper(doc) -> dict:
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


# ================== CRUD + Search APIs ==================

@router.post("/", response_model=AirlineResponse, status_code=201)
async def create_airline(data: AirlineCreate):
    """Nayi Airline add karo"""
    existing = await airlines_collection.find_one({"name": data.name})
    if existing:
        raise HTTPException(status_code=400, detail="This name already exists")

    airline_dict = data.dict()
    airline_dict["slug"] = generate_slug(data.name)
    airline_dict["is_active"] = True
    airline_dict["created_at"] = datetime.utcnow()
    airline_dict["updated_at"] = datetime.utcnow()

    result = await airlines_collection.insert_one(airline_dict)
    new_entry = await airlines_collection.find_one({"_id": result.inserted_id})
    return airline_helper(new_entry)


@router.get("/", response_model=List[AirlineResponse])
async def get_all_airlines(skip: int = 0, limit: int = 50):
    """Saari active entries"""
    cursor = airlines_collection.find({"is_active": True}).skip(skip).limit(limit)
    entries = [airline_helper(doc) async for doc in cursor]
    return entries


# ⚠️ IMPORTANT: Ye saare static routes /{entry_id} se PEHLE aane chahiye
@router.get("/search", response_model=List[AirlineResponse])
async def search_airlines(q: str):
    """Name ya slug se general search"""
    cursor = airlines_collection.find({
        "$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"slug": {"$regex": q, "$options": "i"}}
        ],
        "is_active": True
    })
    entries = [airline_helper(doc) async for doc in cursor]
    return entries


@router.get("/search/by-name", response_model=List[AirlineResponse])
async def search_airlines_by_name(name: str):
    """
    Sirf name se search karo - partial ya full dono chalega.
    
    Examples:
      GET /airlines/search/by-name?name=KLM
      GET /airlines/search/by-name?name=KLM Royal Dutch Airlines
      GET /airlines/search/by-name?name=indigo
    """
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Name query parameter cannot be empty")

    cursor = airlines_collection.find({
        "name": {"$regex": name.strip(), "$options": "i"},
        "is_active": True
    })
    entries = [airline_helper(doc) async for doc in cursor]

    if not entries:
        raise HTTPException(status_code=404, detail=f"No airlines found matching '{name}'")

    return entries


@router.get("/{entry_id}", response_model=AirlineResponse)
async def get_airline_by_id(entry_id: str):
    """ID se single airline fetch karo"""
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    entry = await airlines_collection.find_one({"_id": obj_id})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return airline_helper(entry)


@router.put("/{entry_id}", response_model=AirlineResponse)
async def update_airline(entry_id: str, update_data: AirlineUpdate):
    """Airline update karo"""
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

    result = await airlines_collection.update_one({"_id": obj_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")

    updated = await airlines_collection.find_one({"_id": obj_id})
    return airline_helper(updated)


@router.delete("/{entry_id}")
async def delete_airline(entry_id: str):
    """Airline delete karo"""
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    result = await airlines_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")

    return {"message": "Entry deleted successfully"}


@router.patch("/{entry_id}/deactivate")
async def deactivate_airline(entry_id: str):
    """Airline ko deactivate karo (soft delete)"""
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    result = await airlines_collection.update_one(
        {"_id": obj_id},
        {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")

    return {"message": "Entry deactivated successfully"}