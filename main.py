from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from apis.ip_location.ip import get_ip_and_location
from apis.places.places import router as places_router
from apis.contact.contact import router as contact_router
from apis.search_fields.search import router as search_fields_router
from apis.search_fields.fields.airlines import router as airlines_router
from apis.search_fields.fields.cruise import router as cruise_router
from apis.auth.auth import router as auth_router

app = FastAPI(
    title="Directory Backend",
    description="User IP + Nearby Barber Shops + Contact API",
    version="1.0"
)

# ✅ CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ production me specific domain dalna
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ip-location")
async def get_ip_location(request: Request):
    return get_ip_and_location(request)

# Include Routers
app.include_router(places_router)
app.include_router(contact_router)
app.include_router(search_fields_router)
app.include_router(airlines_router)
app.include_router(cruise_router)
app.include_router(auth_router)

@app.get("/")
async def root():
    return {
        "message": "Backend is running successfully 🚀",
        "endpoints": {
            "ip_location": "/ip-location (GET)",
            "nearby_barber": "/places/nearby-barber (POST)",
            "contacts": "/contacts/ (GET, POST, PUT, DELETE)"
        }
    }