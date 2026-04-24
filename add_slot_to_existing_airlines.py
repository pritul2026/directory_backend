#!/usr/bin/env python3
"""
Script to add slug field to existing airline documents in MongoDB
This script ONLY adds the 'slug' field, doesn't modify any other data
"""

import os
import re
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in your .env file")

# Helper function to generate slug (exact same as your API)
def generate_slug(name: str) -> str:
    """Generate URL-friendly slug from name"""
    if not name:
        return ""
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)   # special chars remove
    slug = re.sub(r'[\s-]+', '-', slug)        # spaces aur multiple - ko single - mein
    return slug.strip('-')


async def add_slug_to_existing_airlines():
    """Add slug field to all airline documents that don't have it"""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGO_URI)
    db = client['directory_db']
    airlines_collection = db["airlines"]
    
    print("🔍 Connecting to MongoDB...")
    
    # Find all documents without slug field OR with empty slug
    cursor = airlines_collection.find({
        "$or": [
            {"slug": {"$exists": False}},
            {"slug": ""},
            {"slug": None}
        ]
    })
    
    documents = await cursor.to_list(length=None)
    
    if not documents:
        print("✅ All documents already have slug field!")
        client.close()
        return
    
    print(f"📊 Found {len(documents)} documents without slug field")
    
    updated_count = 0
    failed_count = 0
    
    for doc in documents:
        try:
            doc_id = doc['_id']
            name = doc.get('name', '')
            
            if not name:
                print(f"⚠️  Skipping document {doc_id}: No name field found")
                failed_count += 1
                continue
            
            # Generate slug from name
            slug = generate_slug(name)
            
            # Update only the slug field
            result = await airlines_collection.update_one(
                {"_id": doc_id},
                {"$set": {"slug": slug}}
            )
            
            if result.modified_count > 0:
                updated_count += 1
                print(f"✅ Updated: {name} -> slug: {slug}")
            else:
                print(f"⚠️  No change for: {name}")
                
        except Exception as e:
            print(f"❌ Failed for document {doc.get('_id', 'unknown')}: {str(e)}")
            failed_count += 1
    
    print("\n" + "="*50)
    print(f"📈 Summary:")
    print(f"   - Total documents without slug: {len(documents)}")
    print(f"   - Successfully updated: {updated_count}")
    print(f"   - Failed: {failed_count}")
    print("="*50)
    
    # Verify the update
    verify_cursor = airlines_collection.find({
        "$or": [
            {"slug": {"$exists": False}},
            {"slug": ""},
            {"slug": None}
        ]
    })
    remaining = await verify_cursor.to_list(length=None)
    
    if remaining:
        print(f"⚠️  Still {len(remaining)} documents without slug field")
    else:
        print("✅ All documents now have slug field!")
    
    client.close()


async def main():
    """Main function"""
    print("🚀 Starting slug migration script...")
    print("⚠️  This script will ONLY add 'slug' field to existing documents")
    print("⚠️  No other data will be modified\n")
    
    await add_slug_to_existing_airlines()
    
    print("\n✨ Migration complete!")


if __name__ == "__main__":
    asyncio.run(main())