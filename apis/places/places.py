import os
import requests
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorClient



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

class Location(BaseModel):
    latitude: float
    longitude: float

class PlaceRequest(BaseModel):
    location: Location
    radius: int = 10000                    # meters, max 50000
    max_results: int = 12
    included_types: Optional[List[str]] = None
    keyword: Optional[str] = None          # "pest control", "airline office", "beauty salon" etc.

    @field_validator("included_types")
    @classmethod
    def validate_types(cls, v):
        if not v or len(v) == 0:
            return None
        return [t.strip().lower() for t in v if t and t.strip()]

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, v):
        if not v:
            return None
        v = v.strip()
        return v if v else None


@router.post("/nearby")
async def get_nearby_places(request: PlaceRequest):
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

    try:
        if request.keyword:
            # === TEXT SEARCH (Best for keywords like "pest control", "airlines") ===
            url = "https://places.googleapis.com/v1/places:searchText"
            
            payload = {
                "textQuery": request.keyword,
                "maxResultCount": min(request.max_results, 20),
                # Location bias ke liye (nearby feel ke liye)
                "locationBias": {
                    "circle": {
                        "center": {
                            "latitude": request.location.latitude,
                            "longitude": request.location.longitude
                        },
                        "radius": min(request.radius, 50000)
                    }
                }
            }

            if request.included_types:
                payload["includedTypes"] = request.included_types

        else:
            # === NEARBY SEARCH (jab sirf types diye ho) ===
            url = "https://places.googleapis.com/v1/places:searchNearby"
            
            payload = {
                "locationRestriction": {
                    "circle": {
                        "center": {
                            "latitude": request.location.latitude,
                            "longitude": request.location.longitude
                        },
                        "radius": min(request.radius, 50000)
                    }
                },
                "maxResultCount": min(request.max_results, 20),
                "rankPreference": "DISTANCE"
            }

            if request.included_types:
                payload["includedTypes"] = request.included_types

        # API call
        response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code != 200:
            print("Google API Error:", response.text)
            raise HTTPException(
                status_code=502,
                detail=f"Google Places API failed: {response.status_code} - {response.text[:300]}"
            )

        data = response.json()
        places = []

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

            places.append({
                "id": place.get("id"),
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
                "photo_urls": [p["url"] for p in photo_list],
                "photos": photo_list,
                "photo_count": len(photos),
                "phone": place.get("internationalPhoneNumber"),
                "website": place.get("websiteUri"),
            })

            
       
        return {
            "success": True,
            "count": len(places),
            "results": places,
            "search_type": "text_search" if request.keyword else "nearby_search",
            "keyword_used": request.keyword,
            "types_used": request.included_types,
            "location_used": request.location
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")