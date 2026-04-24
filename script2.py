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
airlines_collection = db["airlines"]

MODEL_NAME = "phi4-mini:latest"  # Tera installed model

def generate_airline_description(airline_name, phone_number):
    """Generate detailed description for airline"""
    
    prompt = f"""You are a content writer for a customer service directory website. Write a detailed, helpful, and realistic customer service guide for {airline_name}.

Phone number: {phone_number}

Write a comprehensive article similar to GetHuman.com style. Include these sections:

1. **Opening with best phone number** - Highlight {phone_number} as the best number to call
2. **How to reach a live person** - Tips and phone menu navigation
3. **Hours of operation** - Realistic customer service hours
4. **Wait times** - Average hold times, best/worst days to call
5. **Alternate phone numbers** - For reservations, baggage, frequent flyer program
6. **Best time to call** - Based on busy/least busy days
7. **Common reasons customers call** - List 5-6 common issues
8. **Sample customer calls** - 3-4 realistic call examples
9. **FAQ section** - 4-5 frequently asked questions with answers
10. **Other contact methods** - Social media, website, email
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
        print(f"Error: {e}")
        return None

def generate_and_save_all_airlines():
    """Generate descriptions for all airlines"""
    
    # Get all airlines with phone numbers
    airlines = list(airlines_collection.find({"phone": {"$ne": "", "$exists": True}}))
    
    if not airlines:
        print("No airlines found in database!")
        return
    
    print(f"\n🚀 Using model: {MODEL_NAME}")
    print(f"📊 Found {len(airlines)} airlines to process\n")
    
    success_count = 0
    fail_count = 0
    
    for idx, airline in enumerate(airlines, 1):
        name = airline['name']
        phone = airline['phone']
        
        print(f"{idx}/{len(airlines)} ✈️  Generating description for: {name}")
        print(f"   📞 Phone: {phone}")
        
        # Generate description
        description = generate_airline_description(name, phone)
        
        if description:
            # Update only the description field
            airlines_collection.update_one(
                {"_id": airline['_id']},
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
        
        print()  # Empty line for readability
        time.sleep(2)  # Delay between generations
    
    print(f"\n{'='*50}")
    print(f"🎉 COMPLETED!")
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed: {fail_count}")
    print(f"{'='*50}")

def generate_for_specific_airlines():
    """Generate for specific airlines only"""
    
    specific_airlines = [
        ("KLM Royal Dutch Airlines", "800-375-8723"),
        ("Delta Airlines", "800-221-1212"),
        ("United Airlines", "800-864-8331"),
        ("American Airlines", "800-433-7300"),
        ("Emirates Airlines", "800-777-3999")
    ]
    
    print(f"\n🚀 Using model: {MODEL_NAME}\n")
    
    for name, phone in specific_airlines:
        print(f"✈️  Generating for: {name}")
        print(f"   📞 Phone: {phone}")
        
        description = generate_airline_description(name, phone)
        
        if description:
            # Check if exists
            existing = airlines_collection.find_one({"name": name})
            
            if existing:
                airlines_collection.update_one(
                    {"name": name},
                    {"$set": {
                        "description": description,
                        "updated_at": datetime.now(timezone.utc)
                    }}
                )
                print(f"   ✅ Updated description ({len(description)} chars)")
            else:
                # Create new document
                doc = {
                    "name": name,
                    "phone": phone,
                    "description": description,
                    "category": "Airline",
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
                airlines_collection.insert_one(doc)
                print(f"   ✅ Created new airline with description ({len(description)} chars)")
        else:
            print(f"   ❌ Failed to generate")
        
        print()
        time.sleep(2)

def test_single_airline():
    """Test with one airline and show preview"""
    
    name = input("Enter airline name: ").strip()
    phone = input("Enter phone number: ").strip()
    
    if not name or not phone:
        print("❌ Both name and phone required!")
        return
    
    print(f"\n✈️  Generating description for: {name}")
    print(f"📞 Phone: {phone}")
    print("⏳ Please wait (30-60 seconds)...\n")
    
    description = generate_airline_description(name, phone)
    
    if description:
        print("✅ DESCRIPTION GENERATED!\n")
        print("="*60)
        # Show first 1000 characters as preview
        preview = description[:1000]
        print(preview)
        if len(description) > 1000:
            print(f"\n... (and {len(description)-1000} more characters)")
        print("="*60)
        print(f"\n📊 Total length: {len(description)} characters")
        
        # Ask to save
        save = input("\n💾 Save to database? (y/n): ").strip().lower()
        if save == 'y':
            existing = airlines_collection.find_one({"name": name})
            
            if existing:
                airlines_collection.update_one(
                    {"name": name},
                    {"$set": {
                        "description": description,
                        "updated_at": datetime.now(timezone.utc)
                    }}
                )
                print("✅ Updated in database!")
            else:
                doc = {
                    "name": name,
                    "phone": phone,
                    "description": description,
                    "category": "Airline",
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
                airlines_collection.insert_one(doc)
                print("✅ Saved to database!")
    else:
        print("❌ Failed to generate description")

def view_description(airline_name):
    """View existing description for an airline"""
    airline = airlines_collection.find_one({"name": airline_name})
    
    if airline:
        desc = airline.get('description', 'No description available')
        print(f"\n📖 Description for {airline_name}:")
        print("="*60)
        print(desc[:2000])  # Show first 2000 chars
        if len(desc) > 2000:
            print(f"\n... (and {len(desc)-2000} more characters)")
        print("="*60)
    else:
        print(f"❌ Airline '{airline_name}' not found")

def show_sample_airlines():
    """Show existing airlines in database"""
    airlines = list(airlines_collection.find({}, {"name": 1, "phone": 1, "description": 1}).limit(10))
    
    if airlines:
        print("\n📋 Airlines in database:")
        print("-" * 60)
        for airline in airlines:
            has_desc = "✅" if airline.get('description') else "❌"
            desc_len = len(airline.get('description', '')) if airline.get('description') else 0
            print(f"{has_desc} {airline['name']}")
            print(f"   📞 {airline.get('phone', 'No phone')}")
            if desc_len:
                print(f"   📝 Description length: {desc_len} chars")
            print()
    else:
        print("\n⚠️ No airlines found in database!")

if __name__ == "__main__":
    print("\n" + "="*50)
    print("✈️  Airline Description Generator")
    print("="*50)
    
    print("\nChoose option:")
    print("1. Generate for ALL airlines in database")
    print("2. Generate for specific airlines only")
    print("3. Generate & test for ONE airline")
    print("4. View description of an airline")
    print("5. Show sample airlines")
    
    choice = input("\nEnter choice (1/2/3/4/5): ").strip()
    
    if choice == "1":
        confirm = input("\n⚠️ This will update ALL airlines. Continue? (yes/no): ")
        if confirm.lower() == 'yes':
            generate_and_save_all_airlines()
    elif choice == "2":
        generate_for_specific_airlines()
    elif choice == "3":
        test_single_airline()
    elif choice == "4":
        name = input("Enter airline name: ")
        view_description(name)
    elif choice == "5":
        show_sample_airlines()
    else:
        print("Invalid choice!")