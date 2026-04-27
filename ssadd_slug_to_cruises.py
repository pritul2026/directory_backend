import os
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime, timezone
import re

load_dotenv()

# MongoDB Connection
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in .env file")

client = MongoClient(MONGO_URI)
db = client['directory_db']
cruise_collection = db["cruise"]

def generate_slug(name: str) -> str:
    """Same slug generator jo airlines mein use ho raha hai"""
    if not name:
        return ""
    
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)   # special chars remove
    slug = re.sub(r'[\s-]+', '-', slug)        # multiple spaces/dashes ko single dash
    return slug.strip('-')


def add_slug_to_all_cruises():
    """Sab cruises mein slug add ya update karega"""
    
    print("🚢 Starting slug generation for all cruises...\n")
    
    # Saare cruises fetch karo (active + inactive dono)
    cruises = list(cruise_collection.find({}))
    
    if not cruises:
        print("❌ No cruises found in database!")
        return
    
    updated_count = 0
    skipped_count = 0
    
    for cruise in cruises:
        cruise_id = cruise["_id"]
        name = cruise.get("name", "").strip()
        current_slug = cruise.get("slug")
        
        if not name:
            print(f"⚠️  Skipped (no name): {cruise_id}")
            skipped_count += 1
            continue
        
        new_slug = generate_slug(name)
        
        # Agar slug already hai aur sahi hai to skip
        if current_slug == new_slug:
            print(f"✅ Already has correct slug: {name}")
            skipped_count += 1
            continue
        
        # Update document with slug
        result = cruise_collection.update_one(
            {"_id": cruise_id},
            {
                "$set": {
                    "slug": new_slug,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.modified_count > 0:
            print(f"✅ Added/Updated slug: {name} → {new_slug}")
            updated_count += 1
        else:
            print(f"⚠️  No change: {name}")
            skipped_count += 1
    
    print("\n" + "="*60)
    print("🎉 SLUG GENERATION COMPLETED!")
    print(f"Total Cruises Processed : {len(cruises)}")
    print(f"✅ Slugs Added/Updated : {updated_count}")
    print(f"⚠️  Skipped             : {skipped_count}")
    print("="*60)


def add_slug_to_specific_cruises():
    """Agar sirf kuch specific cruises mein slug add karna ho"""
    # Yahan specific names daal sakte ho
    specific_names = ["Norwegian Cruise Line", "Carnival Cruise", "Royal Caribbean Cruise Lines"]
    
    for name in specific_names:
        cruise = cruise_collection.find_one({"name": name})
        if cruise:
            slug = generate_slug(name)
            cruise_collection.update_one(
                {"_id": cruise["_id"]},
                {"$set": {"slug": slug, "updated_at": datetime.now(timezone.utc)}}
            )
            print(f"✅ Updated: {name} → {slug}")
        else:
            print(f"❌ Not found: {name}")


if __name__ == "__main__":
    print("Cruise Slug Generator Script")
    print("1. Add/Update slug for ALL cruises")
    print("2. Add slug for specific cruises only")
    print("3. Exit")
    
    choice = input("\nEnter your choice (1/2/3): ").strip()
    
    if choice == "1":
        confirm = input("\n⚠️  This will update ALL cruises. Are you sure? (yes/no): ")
        if confirm.lower() == "yes":
            add_slug_to_all_cruises()
    elif choice == "2":
        add_slug_to_specific_cruises()
    elif choice == "3":
        print("Goodbye!")
    else:
        print("Invalid choice!")
    
    client.close()