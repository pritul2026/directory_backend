import os
import json
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in your .env file")

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client['directory_db']
cruise_collection = db["cruise"]

# JSON file path
json_file_path = "/Users/pritulsinha/Desktop/directory_backend/data/Cruise_TFN_Data.json"

def import_cruises_from_json():
    """Import cruise data from JSON to MongoDB (only those with phone numbers)"""
    
    imported_count = 0
    skipped_no_phone = 0
    skipped_exists = 0
    
    try:
        with open(json_file_path, mode='r', encoding='utf-8') as file:
            cruises_data = json.load(file)   # JSON list hai toh directly load
            
            for row in cruises_data:
                cruise_name = row.get('Airline Name', '').strip()   # Tune bola "Airline Name" hi key hai
                phone_number = row.get('Phone Number', '').strip()
                source_url = row.get('Source URL', '')
                
                if not cruise_name:
                    continue
                
                # Skip if no phone number
                if phone_number == "Not Found" or not phone_number:
                    print(f"Skipped (no phone number): {cruise_name}")
                    skipped_no_phone += 1
                    continue
                
                # Check if already exists
                existing_cruise = cruise_collection.find_one({"name": cruise_name})
                
                if existing_cruise:
                    print(f"Skipped (already exists): {cruise_name}")
                    skipped_exists += 1
                else:
                    # Create cruise document (same structure as airline)
                    cruise_document = {
                        "name": cruise_name,
                        "phone": phone_number,
                        "category": "Cruise",
                        "description": "",
                        "website": "",
                        "email": "",
                        "address": "",
                        "city": "",
                        "state": "",
                        "country": "",
                        "zip_code": "",
                        "is_active": True,
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc)
                    }
                    
                    cruise_collection.insert_one(cruise_document)
                    print(f"Inserted: {cruise_name} - Phone: {phone_number}")
                    imported_count += 1
        
        print(f"\n{'='*60}")
        print(f"Cruise Import Completed!")
        print(f"Inserted          : {imported_count}")
        print(f"Skipped (no phone): {skipped_no_phone}")
        print(f"Skipped (exists)  : {skipped_exists}")
        print(f"{'='*60}")
        
    except FileNotFoundError:
        print(f"Error: JSON file not found at {json_file_path}")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        client.close()

# ====================== Extra Functions (optional) ======================

def delete_all_cruises():
    """Delete all cruises (use with caution!)"""
    confirm = input("Are you sure you want to delete ALL cruises? (yes/no): ")
    if confirm.lower() == "yes":
        result = cruise_collection.delete_many({})
        print(f"Deleted {result.deleted_count} cruises")
    else:
        print("Operation cancelled")
    client.close()

if __name__ == "__main__":
    print("Cruise Data Import Script")
    print("1. Import from Cruise_TFN_Data.json")
    print("2. Delete all cruises")
    
    choice = input("Enter your choice (1 or 2): ").strip()
    
    if choice == "1":
        import_cruises_from_json()
    elif choice == "2":
        delete_all_cruises()
    else:
        print("Invalid choice!")