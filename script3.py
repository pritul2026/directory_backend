#!/usr/bin/env python3
"""
ONLY add real email addresses to airlines - No other fields modified
"""

import os
import re
import json
import time
from pymongo import MongoClient
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY not found")
    exit(1)

client = MongoClient(MONGO_URI)
db = client['directory_db']
collection = db["airlines"]
groq_client = Groq(api_key=GROQ_API_KEY)

MODEL = "llama-3.3-70b-versatile"

def get_airline_email(airline_name):
    """Get ONLY real email address for the airline"""
    
    prompt = f"""For the airline "{airline_name}", find their REAL customer support email address.

Return ONLY valid JSON with this exact format:
{{"email": "customer@support.email"}}

Rules:
- Find the official customer service email from their website
- Use empty string "" if absolutely no email found
- DO NOT use generic emails like info@, contact@ unless confirmed
- Prefer support@, customer.service@, help@ emails
- Return ONLY the JSON, no other text

Example for "Emirates":
{{"email": "customer.service@emirates.com"}}"""

    try:
        completion = groq_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You return ONLY valid JSON. No explanations."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=150
        )
        
        response = completion.choices[0].message.content.strip()
        response = re.sub(r'^```json\s*', '', response)
        response = re.sub(r'^```\s*', '', response)
        response = re.sub(r'\s*```$', '', response)
        
        data = json.loads(response)
        email = data.get("email", "").strip()
        
        # Basic email validation
        if email and re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            return email
        return ""
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return ""

def add_emails_only(limit=None, dry_run=False):
    """Only add real email addresses to airlines with missing email"""
    
    # Find airlines with missing or empty email
    query = {
        "$or": [
            {"email": {"$exists": False}},
            {"email": ""},
            {"email": None}
        ]
    }
    
    cursor = collection.find(query)
    if limit:
        cursor = cursor.limit(limit)
    
    airlines = list(cursor)
    
    if not airlines:
        print("✅ All airlines already have email addresses!")
        return
    
    print(f"📊 Found {len(airlines)} airlines missing email addresses")
    print(f"✏️  Will ONLY add email field - keeping everything else intact\n")
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")
    
    updated = 0
    skipped = 0
    
    for idx, airline in enumerate(airlines, 1):
        print(f"[{idx}/{len(airlines)}] Processing: {airline['name']}")
        
        # Get real email
        email = get_airline_email(airline['name'])
        
        if not email:
            print(f"   ⚠️ Could not find real email, skipping...\n")
            skipped += 1
            continue
        
        print(f"   📧 Found email: {email}")
        
        if not dry_run:
            # ONLY update the email field
            result = collection.update_one(
                {"_id": airline["_id"]},
                {
                    "$set": {
                        "email": email,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                updated += 1
                print(f"   ✅ Email added successfully!\n")
            else:
                print(f"   ⚠️ No changes made\n")
        else:
            print(f"   🔍 [DRY RUN] Would add email: {email}\n")
            updated += 1
        
        time.sleep(0.5)  # Rate limiting
    
    # Summary
    print("="*60)
    print(f"📈 Summary:")
    print(f"   - Airlines processed: {len(airlines)}")
    print(f"   - ✅ Emails added: {updated}")
    print(f"   - ⚠️ Skipped (no email found): {skipped}")
    if dry_run:
        print(f"   🔍 DRY RUN - No actual changes")
    print("="*60)
    
    # Show example
    if not dry_run and updated > 0:
        sample = collection.find_one({"email": {"$ne": "", "$exists": True}})
        if sample:
            print(f"\n✅ Example of updated airline:")
            print(f"   Name: {sample.get('name')}")
            print(f"   Email: {sample.get('email')}")
            print(f"   (All other fields unchanged)")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='ONLY add real email addresses to airlines')
    parser.add_argument('--limit', type=int, help='Limit number of airlines')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    
    args = parser.parse_args()
    
    print("🚀 Starting email-only enrichment...")
    print("="*60)
    print("⚠️  ONLY adding email addresses - all other fields remain untouched")
    print("="*60)
    
    add_emails_only(limit=args.limit, dry_run=args.dry_run)