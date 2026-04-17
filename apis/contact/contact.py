from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os

load_dotenv()

# ========================= MODELS =========================
class ContactBase(BaseModel):
    name: str
    email: EmailStr
    phone: str
    message: Optional[str] = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    message: Optional[str] = None


class ContactResponse(ContactBase):
    id: str
    model_config = ConfigDict(from_attributes=True)   # Pydantic v2 ke liye correct


# ========================= ROUTER =========================
router = APIRouter(
    prefix="/contacts",
    tags=["Contacts"]
)

# ========================= MONGO CONNECTION =========================
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in your .env file")

client = AsyncIOMotorClient(MONGO_URI)
db = client['directory_db']
contacts_collection = db["contacts"]


# ========================= HELPER FUNCTION =========================
def contact_helper(contact) -> dict:
    return {
        "id": str(contact["_id"]),
        "name": contact["name"],
        "email": contact["email"],
        "phone": contact["phone"],
        "message": contact.get("message")
    }


# ========================= ENDPOINTS =========================

@router.post("/", response_model=ContactResponse, status_code=201)
async def create_contact(contact: ContactCreate):
    # Check duplicate email or phone
    existing = await contacts_collection.find_one({
        "$or": [{"email": contact.email}, {"phone": contact.phone}]
    })
    if existing:
        raise HTTPException(status_code=400, detail="Contact with this email or phone already exists.")

    result = await contacts_collection.insert_one(contact.model_dump())
    new_contact = await contacts_collection.find_one({"_id": result.inserted_id})
    
    return contact_helper(new_contact)


@router.get("/", response_model=List[ContactResponse])
async def get_all_contacts(skip: int = 0, limit: int = 100):
    contacts = await contacts_collection.find().skip(skip).limit(limit).to_list(limit)
    return [contact_helper(contact) for contact in contacts]


@router.get("/search", response_model=ContactResponse)
async def get_contact_by_email_or_phone(
    email: Optional[EmailStr] = Query(None, description="Search by email"),
    phone: Optional[str] = Query(None, description="Search by phone")
):
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Provide either email or phone")

    query = {}
    if email:
        query["email"] = email
    if phone:
        query["phone"] = phone

    contact = await contacts_collection.find_one(query)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact Not Found")

    return contact_helper(contact)


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact_by_id(contact_id: str):
    if not ObjectId.is_valid(contact_id):
        raise HTTPException(status_code=400, detail="Invalid Contact ID")

    contact = await contacts_collection.find_one({"_id": ObjectId(contact_id)})
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not Found")

    return contact_helper(contact)


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(contact_id: str, contact_update: ContactUpdate):
    if not ObjectId.is_valid(contact_id):
        raise HTTPException(status_code=400, detail="Invalid Contact ID")

    update_data = {k: v for k, v in contact_update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided to update")

    result = await contacts_collection.update_one(
        {"_id": ObjectId(contact_id)},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contact Not Found.")

    updated_contact = await contacts_collection.find_one({"_id": ObjectId(contact_id)})
    return contact_helper(updated_contact)


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(contact_id: str):
    if not ObjectId.is_valid(contact_id):
        raise HTTPException(status_code=400, detail="Invalid Contact ID")

    result = await contacts_collection.delete_one({"_id": ObjectId(contact_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contact not found")

    return {"message": "Contact Deleted Successfully"}