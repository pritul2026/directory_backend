import os
import csv
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
airlines_collection = db["cruise"]

# CSV file path
csv_file_path = "/Users/pritulsinha/Desktop/directory_backend/data/Airline_TFN_Data (1).csv"

def import_airlines_from_csv():
    """Import airlines data from CSV to MongoDB (only those with phone numbers)"""
    
    imported_count = 0
    skipped_no_phone = 0
    skipped_exists = 0
    
    try:
        with open(csv_file_path, mode='r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            
            for row in csv_reader:
                airline_name = row.get('Airline Name', '').strip()
                phone_number = row.get('Phone Number', '').strip()
                
                # Skip if airline name is empty
                if not airline_name:
                    continue
                
                # Skip if phone number is "Not Found" or empty
                if phone_number == "Not Found" or not phone_number:
                    print(f"Skipped (no phone number): {airline_name}")
                    skipped_no_phone += 1
                    continue
                
                # Check if airline already exists
                existing_airline = airlines_collection.find_one({"name": airline_name})
                
                if existing_airline:
                    print(f"Skipped (already exists): {airline_name}")
                    skipped_exists += 1
                else:
                    # Create new airline document
                    airline_document = {
                        "name": airline_name,
                        "phone": phone_number,
                        "category": "Airline",
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
                    
                    airlines_collection.insert_one(airline_document)
                    print(f"Inserted: {airline_name} - Phone: {phone_number}")
                    imported_count += 1
        
        print(f"\n{'='*50}")
        print(f"Import Completed!")
        print(f"Inserted: {imported_count}")
        print(f"Skipped (no phone number): {skipped_no_phone}")
        print(f"Skipped (already exists): {skipped_exists}")
        print(f"{'='*50}")
        
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_file_path}")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        client.close()

def insert_manual_data():
    """Manual data insertion from the provided list (only those with phone numbers)"""
    
    airlines_data = [
        (8, "KLM Royal Dutch Airlines", "800-375-8723"),
        (236, "Qantas Airlines", "800-227-4500"),
        (457, "Delta Airlines", "800-221-1212"),
        (458, "Delta Airlines Skymiles", "800-323-2323"),
        # (1087, "Cathay Pacific Airlines", ""),  # Not Found - Skipped
        # (1101, "Cebu Pacific Airlines", ""),    # Not Found - Skipped
        (1285, "China Eastern Airlines", "626-583-1500"),
        (1288, "China Southern Airlines", "323-653-8088"),
        (1624, "Condor Airlines", "866-960-7915")
    ]
    
    count = 0
    skipped = 0
    
    for airline_id, name, phone in airlines_data:
        # Skip if phone is empty
        if not phone:
            print(f"Skipped (no phone number): {name}")
            skipped += 1
            continue
            
        # Check if exists
        existing = airlines_collection.find_one({"name": name})
        
        if not existing:
            airline_document = {
                "name": name,
                "phone": phone,
                "category": "Airline",
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
            
            airlines_collection.insert_one(airline_document)
            print(f"Inserted: {name} - Phone: {phone}")
            count += 1
        else:
            print(f"Skipped (already exists): {name}")
            skipped += 1
    
    print(f"\n{'='*50}")
    print(f"Total Inserted: {count}")
    print(f"Total Skipped: {skipped}")
    print(f"{'='*50}")
    client.close()

def delete_all_airlines():
    """Delete all airlines from collection (use with caution!)"""
    confirm = input("Are you sure you want to delete ALL airlines? (yes/no): ")
    if confirm.lower() == "yes":
        result = airlines_collection.delete_many({})
        print(f"Deleted {result.deleted_count} airlines")
    else:
        print("Operation cancelled")
    client.close()

if __name__ == "__main__":
    print("Choose option:")
    print("1. Import from CSV file (only airlines with phone numbers)")
    print("2. Insert manual data (only airlines with phone numbers)")
    print("3. Delete all airlines")
    
    choice = input("Enter your choice (1, 2, or 3): ").strip()
    
    if choice == "1":
        import_airlines_from_csv()
    elif choice == "2":
        insert_manual_data()
    elif choice == "3":
        delete_all_airlines()
    else:
        print("Invalid choice!")