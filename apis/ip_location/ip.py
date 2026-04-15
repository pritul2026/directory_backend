import requests
from fastapi import Request

def get_ip_and_location(request: Request):
    # Pehle real IP nikaalo
    ip = request.client.host
    xff = request.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[0].strip()
    
    xreal = request.headers.get("x-real-ip")
    if xreal:
        ip = xreal

    # Ab is IP ka location nikaalo (free API - ip-api.com best hai for no key)
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,lat,lon,timezone,isp")
        data = response.json()
        
        if data.get("status") == "success":
            location = {
                "ip": ip,
                "country": data.get("country"),
                "country_code": data.get("countryCode"),
                "region": data.get("regionName"),
                "city": data.get("city"),
                "latitude": data.get("lat"),
                "longitude": data.get("lon"),
                "timezone": data.get("timezone"),
                "isp": data.get("isp")
            }
        else:
            location = {"ip": ip, "error": data.get("message", "Could not get location")}
    except Exception as e:
        location = {"ip": ip, "error": str(e)}

    return location 