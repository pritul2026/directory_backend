import ollama
import json
from pymongo import MongoClient
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
import time

load_dotenv()

# MongoDB connection
client = MongoClient(os.getenv("MONGO_URI"))
db = client['directory_db']
cruise_collection = db["cruise"]   # ← Changed to cruise

MODEL_NAME = "phi4-mini:latest"  # Tera model

def generate_cruise_description(cruise_name, phone_number):
    """Generate detailed description for Cruise Line"""
    
    prompt = f"""You are a content writer for a customer service directory website. Write a detailed, helpful, and realistic customer service guide for {cruise_name}.

Phone number: {phone_number}

Write a comprehensive article similar to GetHuman.com style. Include these sections:

1. **Opening with best phone number** - Highlight {phone_number} as the best number to call
2. **How to reach a live person** - Tips and phone menu navigation
3. **Hours of operation** - Realistic customer service hours
4. **Wait times** - Average hold times, best/worst days to call
5. **Alternate phone numbers** - For reservations, cancellations, baggage, loyalty program etc.
6. **Best time to call** - Based on busy/least busy days and seasons
7. **Common reasons customers call** - List 5-6 common issues (booking, cancellation, refund, boarding etc.)
8. **Sample customer calls** - 3-4 realistic call examples
9. **FAQ section** - 4-5 frequently asked questions with answers
10. **Other contact methods** - Website, email, app, social media
11. **Conclusion** - Summary and final tips

Make it sound authentic, professional, and helpful. Use natural language. Length should be 800-1200 words. Write in English.

IMPORTANT: Return ONLY the article text, no JSON, no extra formatting, just pure HTML formatted content with <h2> tags for sections, <p> for paragraphs, <ul> for lists.

Start directly with the content."""

    try:
        response = ollama.chat(model=MODEL_NAME, messages=[
            {'role': 'user', 'content': prompt}
        ], options={'temperature': 0.7, 'num_predict': 4000})
        
        description = response['message']['content'].strip()
        return description
        
    except Exception as e:
        print(f"Error generating description: {e}")
        return None

def generate_and_save_all_cruises():
    """Generate descriptions for ALL cruises in database"""
    
    cruises = list(cruise_collection.find({"phone": {"$ne": "", "$exists": True}}))
    
    if not cruises:
        print("No cruises found in database!")
        return
    
    print(f"\n🚢 Using model: {MODEL_NAME}")
    print(f"📊 Found {len(cruises)} cruises to process\n")
    
    success_count = 0
    fail_count = 0
    
    for idx, cruise in enumerate(cruises, 1):
        name = cruise['name']
        phone = cruise['phone']
        
        print(f"{idx}/{len(cruises)} 🚢 Generating description for: {name}")
        print(f"   📞 Phone: {phone}")
        
        description = generate_cruise_description(name, phone)
        
        if description:
            cruise_collection.update_one(
                {"_id": cruise['_id']},
                {"$set": {
                    "description": description,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            print(f"   ✅ Description added ({len(description)} characters)")
            success_count += 1
        else:
            print(f"   ❌ Failed to generate")
            fail_count += 1
        
        print()
        time.sleep(2)  # Avoid rate limit / overload
    
    print(f"\n{'='*60}")
    print(f"🎉 CRUISE DESCRIPTION GENERATION COMPLETED!")
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed: {fail_count}")
    print(f"{'='*60}")

def generate_for_specific_cruises():
    """Generate for specific cruise lines"""
    
    specific_cruises = [
        ("Carnival Cruise", "800-764-7419"),
        ("Royal Caribbean Cruise Lines", "800-256-6649"),
        # Add more here if you want
    ]
    
    print(f"\n🚢 Using model: {MODEL_NAME}\n")
    
    for name, phone in specific_cruises:
        print(f"🚢 Generating for: {name}")
        print(f"   📞 Phone: {phone}")
        
        description = generate_cruise_description(name, phone)
        
        if description:
            existing = cruise_collection.find_one({"name": name})
            
            if existing:
                cruise_collection.update_one(
                    {"name": name},
                    {"$set": {"description": description, "updated_at": datetime.now(timezone.utc)}}
                )
                print(f"   ✅ Updated description ({len(description)} chars)")
            else:
                doc = {
                    "name": name,
                    "phone": phone,
                    "description": description,
                    "category": "Cruise",
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
                cruise_collection.insert_one(doc)
                print(f"   ✅ Created new cruise with description")
        else:
            print(f"   ❌ Failed")
        
        print()
        time.sleep(2)

def test_single_cruise():
    """Test with one cruise"""
    name = input("Enter cruise name: ").strip()
    phone = input("Enter phone number: ").strip()
    
    if not name or not phone:
        print("❌ Name and phone both required!")
        return
    
    print(f"\n🚢 Generating description for: {name}")
    print(f"📞 Phone: {phone}")
    print("⏳ Generating... (30-60 seconds)\n")
    
    description = generate_cruise_description(name, phone)
    
    if description:
        print("✅ DESCRIPTION GENERATED!\n")
        print("="*70)
        print(description[:1200])   # Preview
        if len(description) > 1200:
            print(f"\n... (+ {len(description)-1200} more characters)")
        print("="*70)
        
        save = input("\nSave to database? (y/n): ").strip().lower()
        if save == 'y':
            existing = cruise_collection.find_one({"name": name})
            if existing:
                cruise_collection.update_one({"name": name}, {"$set": {"description": description, "updated_at": datetime.now(timezone.utc)}})
                print("✅ Updated in database!")
            else:
                doc = {
                    "name": name,
                    "phone": phone,
                    "description": description,
                    "category": "Cruise",
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
                cruise_collection.insert_one(doc)
                print("✅ Saved to database!")
    else:
        print("❌ Failed to generate")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚢 Cruise Description Generator (AI Powered)")
    print("="*60)
    
    print("\nChoose option:")
    print("1. Generate for ALL cruises in database")
    print("2. Generate for specific cruises")
    print("3. Test & Generate for ONE cruise")
    
    choice = input("\nEnter choice (1/2/3): ").strip()
    
    if choice == "1":
        confirm = input("\n⚠️ This will process ALL cruises. Continue? (yes/no): ")
        if confirm.lower() == 'yes':
            generate_and_save_all_cruises()
    elif choice == "2":
        generate_for_specific_cruises()
    elif choice == "3":
        test_single_cruise()
    else:
        print("Invalid choice!")