from fastapi import FastAPI, Request
from apis.ip_location.ip import get_ip_and_location

app = FastAPI()

@app.get("/ip-location")
async def get_ip_location(request: Request):
    return get_ip_and_location(request)