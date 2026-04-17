


import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/search-fields", tags=["search-fields"])

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in your .env file")

client = AsyncIOMotorClient(MONGO_URI)
db = client['directory_db']
search_fields_collection = db["search_fields"]


# ================== Pydantic Models ==================
class SearchFieldBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    category: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    is_active: bool = True


class SearchFieldCreate(SearchFieldBase):
    pass


class SearchFieldUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SearchFieldResponse(SearchFieldBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Helper function to convert MongoDB document to response
def search_field_helper(doc) -> dict:
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


# ================== APIs ==================

@router.post("/", response_model=SearchFieldResponse, status_code=201)
async def create_search_field(field: SearchFieldCreate):
    """Naya search field/category add karo (airlines, cruise, car repair, etc.)"""
    
    # Check if name already exists
    existing = await search_fields_collection.find_one({"name": field.name})
    if existing:
        raise HTTPException(status_code=400, detail="This name already exists")

    field_dict = field.dict()
    field_dict["created_at"] = datetime.utcnow()
    field_dict["updated_at"] = datetime.utcnow()

    result = await search_fields_collection.insert_one(field_dict)
    
    created_field = await search_fields_collection.find_one({"_id": result.inserted_id})
    
    return search_field_helper(created_field)


@router.get("/", response_model=List[SearchFieldResponse])
async def get_all_search_fields(skip: int = 0, limit: int = 50):
    """Saare active search fields ki list"""
    cursor = search_fields_collection.find({"is_active": True}).skip(skip).limit(limit)
    fields = []
    async for doc in cursor:
        fields.append(search_field_helper(doc))
    return fields


@router.get("/search", response_model=List[SearchFieldResponse])
async def search_by_name(name: str = Query(..., min_length=1)):
    """Name se search karo (partial match)"""
    cursor = search_fields_collection.find({
        "name": {"$regex": name, "$options": "i"},
        "is_active": True
    })
    fields = []
    async for doc in cursor:
        fields.append(search_field_helper(doc))
    return fields


@router.get("/{field_id}", response_model=SearchFieldResponse)
async def get_search_field_by_id(field_id: str):
    """ID se single field lo"""
    try:
        obj_id = ObjectId(field_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    field = await search_fields_collection.find_one({"_id": obj_id})
    if not field:
        raise HTTPException(status_code=404, detail="Search field not found")
    
    return search_field_helper(field)


@router.put("/{field_id}", response_model=SearchFieldResponse)
async def update_search_field(field_id: str, update_data: SearchFieldUpdate):
    """Field update karo"""
    try:
        obj_id = ObjectId(field_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    update_dict = {k: v for k, v in update_data.dict().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No data to update")

    update_dict["updated_at"] = datetime.utcnow()

    result = await search_fields_collection.update_one(
        {"_id": obj_id},
        {"$set": update_dict}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Search field not found")

    updated_field = await search_fields_collection.find_one({"_id": obj_id})
    return search_field_helper(updated_field)


@router.delete("/{field_id}")
async def delete_search_field(field_id: str):
    """Field delete karo"""
    try:
        obj_id = ObjectId(field_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await search_fields_collection.delete_one({"_id": obj_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Search field not found")

    return {"message": "Search field deleted successfully", "id": field_id}


# Optional: Soft Delete (recommended)
@router.patch("/{field_id}/deactivate")
async def deactivate_search_field(field_id: str):
    """Soft delete (is_active = False)"""
    try:
        obj_id = ObjectId(field_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await search_fields_collection.update_one(
        {"_id": obj_id},
        {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Search field not found")

    return {"message": "Search field deactivated successfully"}