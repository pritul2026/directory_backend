import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from collections import defaultdict

load_dotenv()

router = APIRouter(prefix="/places", tags=["places"])

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise ValueError("Mongo_URI is not set in your .env file")

client = AsyncIOMotorClient(MONGO_URI)
db = client['directory_db']
places_collection = db["places"]

if not GOOGLE_PLACES_API_KEY:
    raise Exception("GOOGLE_PLACES_API_KEY .env file mein nahi mila!")


# ====================== RESPONSE MODELS ======================
class PlaceResponse(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None
    short_address: Optional[str] = None
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    business_status: Optional[str] = None
    types: List[str] = []
    primary_type: Optional[str] = None
    google_maps_url: Optional[str] = None
    photo_urls: List[str] = []
    photos: List[Dict[str, Any]] = []
    photo_count: Optional[int] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    searched_keyword: Optional[str] = None


class NearbyPlacesResponse(BaseModel):
    success: bool
    count: int
    results: List[PlaceResponse]
    source: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    keyword_used: Optional[str] = None
    saved_to_db: Optional[int] = None


class CitySummaryResponse(BaseModel):
    success: bool
    city: str
    state: Optional[str] = None
    country: Optional[str] = None
    total_places: int
    total_keywords: int
    keywords: List[Dict[str, Any]]
    message: Optional[str] = None


class DeleteResponse(BaseModel):
    success: bool
    message: str
    city: str
    state: Optional[str] = None
    country: Optional[str] = None
    keyword: str
    deleted_count: int


# ====================== REQUEST MODEL ======================
class Location(BaseModel):
    latitude: float
    longitude: float


class PlaceRequest(BaseModel):
    location: Location
    radius: int = 10000
    max_results: int = 10
    included_types: Optional[List[str]] = None
    keyword: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None

    @field_validator("included_types")
    @classmethod
    def validate_types(cls, v):
        if not v or len(v) == 0:
            return None
        return [t.strip().lower() for t in v if t and t.strip()]

    @field_validator("keyword", "city", "state", "country")
    @classmethod
    def validate_string(cls, v):
        if not v:
            return None
        v = v.strip()
        return v if v else None


# ====================== COMMON HELPER ======================
async def get_cached_places(city: str, state: str, country: str, keyword: str, max_age_hours: int = 24):
    if not city or not keyword:
        return None
    
    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    
    query = {
        "city": {"$regex": f"^{city}$", "$options": "i"},
        "searched_keyword": {"$regex": f"^{keyword}$", "$options": "i"}
    }
    
    if state:
        query["state"] = {"$regex": f"^{state}$", "$options": "i"}
    if country:
        query["country"] = {"$regex": f"^{country}$", "$options": "i"}

    cached = await places_collection.find(query).sort("last_updated", -1).to_list(length=50)

    if cached and cached[0].get("last_updated") and cached[0]["last_updated"] > cutoff:
        return cached
    return None


def prepare_response_place(place):
    return {
        "id": place.get("google_place_id"),
        "name": place.get("name"),
        "address": place.get("address"),
        "short_address": place.get("short_address"),
        "rating": place.get("rating"),
        "user_ratings_total": place.get("user_ratings_total"),
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "business_status": place.get("business_status"),
        "types": place.get("types"),
        "primary_type": place.get("primary_type"),
        "google_maps_url": place.get("google_maps_url"),
        "photo_urls": place.get("photo_urls", []),
        "photos": place.get("photos", []),
        "photo_count": place.get("photo_count"),
        "phone": place.get("phone"),
        "website": place.get("website"),
        "city": place.get("city"),
        "state": place.get("state"),
        "country": place.get("country"),
        "searched_keyword": place.get("searched_keyword"),
    }


# ====================== 1. CACHE API ======================
@router.post("/nearby", response_model=NearbyPlacesResponse)
async def get_nearby_places_cached(request: PlaceRequest):
    """Fast Search - DB Cache pehle check karega"""
    try:
        cached_places = await get_cached_places(
            request.city, request.state, request.country, request.keyword
        )

        if cached_places:
            results = [prepare_response_place(p) for p in cached_places[:request.max_results]]
            return {
                "success": True,
                "count": len(results),
                "results": results,
                "source": "cache",
                "city": request.city,
                "state": request.state,
                "country": request.country,
                "keyword_used": request.keyword
            }

        return await fetch_from_google(request)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ====================== 2. FRESH SEARCH API ======================
@router.post("/nearby/fresh", response_model=NearbyPlacesResponse)
async def get_nearby_places_fresh(request: PlaceRequest):
    """Force Fresh Google Search"""
    try:
        return await fetch_from_google(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ====================== GOOGLE FETCH LOGIC ======================
async def fetch_from_google(request: PlaceRequest):
    # ... headers same (no change) ...
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.displayName,places.formattedAddress,places.shortFormattedAddress,"
            "places.rating,places.userRatingCount,places.location,places.businessStatus,"
            "places.types,places.primaryType,places.id,places.googleMapsUri,places.photos,"
            "places.internationalPhoneNumber,places.websiteUri"
        )
    }

    if request.keyword:
        url = "https://places.googleapis.com/v1/places:searchText"
        payload = {
            "textQuery": request.keyword,
            "maxResultCount": min(request.max_results, 20),
            "locationBias": {
                "circle": {
                    "center": {"latitude": request.location.latitude, "longitude": request.location.longitude},
                    "radius": min(request.radius, 50000)
                }
            }
        }
        if request.included_types:
            payload["includedTypes"] = request.included_types
    else:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        payload = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": request.location.latitude, "longitude": request.location.longitude},
                    "radius": min(request.radius, 50000)
                }
            },
            "maxResultCount": min(request.max_results, 20),
            "rankPreference": "DISTANCE"
        }
        if request.included_types:
            payload["includedTypes"] = request.included_types

    response = requests.post(url, json=payload, headers=headers, timeout=15)

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Google Places API failed")

    data = response.json()
    places = []
    place_datas = []

    for place in data.get("places", []):
        loc = place.get("location", {})
        photos = place.get("photos", [])

        photo_list = []
        for photo in photos[:8]:
            photo_name = photo.get("name")
            if photo_name:
                photo_url = f"https://places.googleapis.com/v1/{photo_name}/media?maxHeightPx=800&maxWidthPx=1200&key={GOOGLE_PLACES_API_KEY}"
                photo_list.append({
                    "url": photo_url,
                    "height": photo.get("heightPx"),
                    "width": photo.get("widthPx")
                })

        place_data = {
            "google_place_id": place.get("id"),
            "name": place.get("displayName", {}).get("text"),
            "address": place.get("formattedAddress"),
            "short_address": place.get("shortFormattedAddress"),
            "rating": place.get("rating"),
            "user_ratings_total": place.get("userRatingCount"),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "business_status": place.get("businessStatus"),
            "types": place.get("types", []),
            "primary_type": place.get("primaryType"),
            "google_maps_url": place.get("googleMapsUri"),
            "photos": photo_list,
            "photo_urls": [p["url"] for p in photo_list],
            "photo_count": len(photos),
            "phone": place.get("internationalPhoneNumber"),
            "website": place.get("websiteUri"),

            "city": request.city,
            "state": request.state,
            "country": request.country,
            "searched_keyword": request.keyword,
            "searched_types": request.included_types,
            "searched_location": {"latitude": request.location.latitude, "longitude": request.location.longitude},
            "search_type": "text_search" if request.keyword else "nearby_search",
            "last_updated": datetime.utcnow(),
        }

        places.append(prepare_response_place(place_data))
        place_datas.append(place_data)

    # Save to DB
    if place_datas:
        for pd in place_datas:
            await places_collection.update_one(
                {"google_place_id": pd["google_place_id"]},
                {"$set": pd},
                upsert=True
            )

    return {
        "success": True,
        "count": len(places),
        "saved_to_db": len(place_datas),
        "results": places,
        "source": "google_api",
        "city": request.city,
        "state": request.state,
        "country": request.country,
        "keyword_used": request.keyword,
    }


# ====================== 3. CITY SEARCH API (Updated) ======================
@router.get("/city/{city_name}", response_model=CitySummaryResponse)
async def get_places_by_city(city_name: str, state: Optional[str] = None, country: Optional[str] = None, limit: int = 100):
    try:
        query = {"city": {"$regex": f"^{city_name}$", "$options": "i"}}
        if state:
            query["state"] = {"$regex": f"^{state}$", "$options": "i"}
        if country:
            query["country"] = {"$regex": f"^{country}$", "$options": "i"}

        places = await places_collection.find(query).to_list(length=limit)

        if not places:
            return {
                "success": True,
                "city": city_name,
                "state": state,
                "country": country,
                "total_places": 0,
                "total_keywords": 0,
                "keywords": [],
                "message": "No data found for this city"
            }

        keyword_group = defaultdict(list)
        for place in places:
            kw = place.get("searched_keyword")
            if kw:
                keyword_group[kw].append(place)

        keywords_summary = []
        for keyword, items in keyword_group.items():
            keywords_summary.append({
                "keyword": keyword,
                "count": len(items),
                "last_updated": items[0].get("last_updated")
            })

        keywords_summary.sort(key=lambda x: x["count"], reverse=True)

        return {
            "success": True,
            "city": city_name,
            "state": state,
            "country": country,
            "total_places": len(places),
            "total_keywords": len(keywords_summary),
            "keywords": keywords_summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ====================== 4. DELETE API ======================
@router.delete("/city/{city_name}", response_model=DeleteResponse)
async def delete_places_by_city_keyword(
    city_name: str, 
    keyword: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = None
):
    try:
        filter_query = {"city": {"$regex": f"^{city_name}$", "$options": "i"}}
        
        if keyword:
            filter_query["searched_keyword"] = {"$regex": f"^{keyword}$", "$options": "i"}
        if state:
            filter_query["state"] = {"$regex": f"^{state}$", "$options": "i"}
        if country:
            filter_query["country"] = {"$regex": f"^{country}$", "$options": "i"}

        result = await places_collection.delete_many(filter_query)

        return {
            "success": True,
            "message": "Data successfully deleted",
            "city": city_name,
            "state": state,
            "country": country,
            "keyword": keyword or "ALL",
            "deleted_count": result.deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ====================== GET PLACE BY ID (Only from DB) ======================
@router.get("/{place_id}", response_model=PlaceResponse)
async def get_place_by_id(place_id: str):
    """Get single place by Google Place ID - Only from MongoDB"""
    try:
        place = await places_collection.find_one(
            {"google_place_id": place_id}
        )

        if not place:
            raise HTTPException(
                status_code=404, 
                detail=f"Place with ID {place_id} not found in database"
            )

        return prepare_response_place(place)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{place_id}", response_model=PlaceResponse)
async def get_place_by_id(
    place_id: str, 
    city: Optional[str] = None,
    state: Optional[str] = None
):
    """Get place by ID with optional city/state filter"""
    try:
        query = {"google_place_id": place_id}
        
        if city:
            query["city"] = {"$regex": f"^{city}$", "$options": "i"}
        if state:
            query["state"] = {"$regex": f"^{state}$", "$options": "i"}

        place = await places_collection.find_one(query)

        if not place:
            raise HTTPException(
                status_code=404, 
                detail="Place not found in database"
            )

        return prepare_response_place(place)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))