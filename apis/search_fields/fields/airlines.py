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

router = APIRouter(prefix="/airlines", tags=["airlines"])

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in .env file")

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


# ====================== PUBLIC ROUTES ======================

@router.get("/", response_model=List[AirlineResponse])
async def get_all_airlines(
    skip: int = 0, 
    limit: int = 50,
    show_all: bool = Query(True, description="Show both active and inactive airlines")
):
    """Saari airlines dikhega (active + inactive). 
    Agar sirf active chahiye to ?show_all=false use karo"""
    query = {} if show_all else {"is_active": True}
    
    cursor = airlines_collection.find(query).skip(skip).limit(limit)
    entries = [airline_helper(doc) async for doc in cursor]
    return entries


@router.get("/search", response_model=List[dict])
async def search_airlines(
    q: str,
    show_all: bool = Query(True, description="Search in both active and inactive airlines")
):
    """Name ya slug se search - ab show_all=true se inactive bhi search honge"""
    query = {
        "$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"slug": {"$regex": q, "$options": "i"}}
        ]
    }
    
    if not show_all:
        query["is_active"] = True
    
    cursor = airlines_collection.find(query)
    
    entries = []
    async for doc in cursor:
        entries.append({
            "id": str(doc["_id"]),
            "slug": doc.get("slug", ""),
            "name": doc.get("name", ""),
            "category": doc.get("category", "airline"),
            "is_active": doc.get("is_active", True)  # Added is_active flag in response
        })
    
    return entries


@router.get("/{entry_id}", response_model=AirlineResponse)
async def get_airline_by_id(entry_id: str):
    """ID se airline fetch karo - active/inactive dono milenge"""
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    entry = await airlines_collection.find_one({"_id": obj_id})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return airline_helper(entry)


@router.get("/slug/{slug}", response_model=AirlineResponse)
async def get_airline_by_slug(
    slug: str,
    show_all: bool = Query(True, description="Show both active and inactive")
):
    """Slug se airline fetch karo - ab show_all=true se inactive bhi dikhega"""
    if not slug or not slug.strip():
        raise HTTPException(status_code=400, detail="Slug cannot be empty")
    
    query = {"slug": slug.strip().lower()}
    if not show_all:
        query["is_active"] = True
    
    entry = await airlines_collection.find_one(query)
    
    if not entry:
        raise HTTPException(status_code=404, detail=f"No airline found with slug '{slug}'")
    
    return airline_helper(entry)


# ====================== PROTECTED ROUTES ======================

@router.post("/", response_model=AirlineResponse, status_code=201)
async def create_airline(
    data: AirlineCreate, 
    current_user: UserInDB = Depends(get_current_user)
):
    existing = await airlines_collection.find_one({"name": data.name})
    if existing:
        raise HTTPException(status_code=400, detail="This name already exists")

    airline_dict = data.dict()
    airline_dict["slug"] = generate_slug(data.name)
    airline_dict["is_active"] = True          # Naya entry hamesha active
    airline_dict["created_at"] = datetime.utcnow()
    airline_dict["updated_at"] = datetime.utcnow()

    result = await airlines_collection.insert_one(airline_dict)
    new_entry = await airlines_collection.find_one({"_id": result.inserted_id})
    return airline_helper(new_entry)


@router.put("/{entry_id}", response_model=AirlineResponse)
async def update_airline(
    entry_id: str, 
    update_data: AirlineUpdate,
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

    result = await airlines_collection.update_one({"_id": obj_id}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")

    updated = await airlines_collection.find_one({"_id": obj_id})
    return airline_helper(updated)


@router.delete("/{entry_id}")
async def delete_airline(
    entry_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    result = await airlines_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")

    return {"message": "Entry deleted successfully"}


@router.patch("/{entry_id}/deactivate")
async def deactivate_airline(
    entry_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
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


@router.patch("/{entry_id}/activate")
async def activate_airline(
    entry_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    """Inactive airline ko wapas active karne ke liye"""
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    result = await airlines_collection.update_one(
        {"_id": obj_id},
        {"$set": {"is_active": True, "updated_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")

    return {"message": "Entry activated successfully"}