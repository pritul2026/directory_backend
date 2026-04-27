#!/usr/bin/env python3
"""
Cruise Enrichment Script - Smart Order:
1. First Groq → Structured fields (email, hours, tips, etc.)
2. Then Ollama → Long Description (only if description is missing)
"""

import os
import re
import json
import time
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv
from groq import Groq
import ollama

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY not found in .env")
    exit(1)

client = MongoClient(MONGO_URI)
db = client['directory_db']
cruise_collection = db["cruise"]

groq_client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

OLLAMA_MODEL = "phi4-mini:latest"   # Change if you want another model

def clean_json_response(text):
    text = re.sub(r'^```json\s*', '', text.strip())
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text

def enrich_structured_fields_groq(cruise_name, phone_number):
    """Step 1: Groq se saare structured fields le aao"""
    prompt = f"""You are an expert customer service researcher.
Find accurate information for cruise line: "{cruise_name}"

Phone: {phone_number}

Return ONLY valid JSON in this exact format:

{{
  "website": "official website or empty string",
  "email": "official customer service email or empty string",
  "hours": "Customer service operating hours (e.g. Mon-Sun 7AM-11PM EST)",
  "average_hold_time": 18,
  "best_time_to_call": "Best days and time to call",
  "phone_menu_tips": "Detailed phone menu navigation tips to reach human agent",
  "common_issues": ["List of 5-7 common customer issues"],
  "notes": "Any important notes or special instructions"
}}

Rules:
- Be as accurate as possible.
- Use real information.
- average_hold_time should be integer (in minutes).
- common_issues must be array of strings.
- If information not found, use "" or [] or 0 accordingly.
- Return ONLY JSON, no extra text."""

    try:
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You always return clean valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=900
        )
        
        response = completion.choices[0].message.content.strip()
        cleaned = clean_json_response(response)
        data = json.loads(cleaned)
        
        return {
            "website": str(data.get("website", "")).strip(),
            "email": str(data.get("email", "")).strip(),
            "hours": str(data.get("hours", "")).strip(),
            "average_hold_time": int(data.get("average_hold_time", 0)),
            "best_time_to_call": str(data.get("best_time_to_call", "")).strip(),
            "phone_menu_tips": str(data.get("phone_menu_tips", "")).strip(),
            "common_issues": data.get("common_issues", []),
            "notes": str(data.get("notes", "")).strip()
        }
        
    except Exception as e:
        print(f"   ❌ Groq Error: {e}")
        return None


def generate_description_ollama(cruise_name, phone_number):
    """Step 2: Ollama se long detailed description"""
    prompt = f"""Write a detailed, professional and helpful customer service guide for **{cruise_name}** cruise line.

Main Contact Number: {phone_number}

Write in GetHuman style. Include these sections using proper HTML tags:

<h2>Best Way to Contact {cruise_name}</h2>
<h2>How to Reach a Live Person</h2>
<h2>Customer Service Hours</h2>
<h2>Average Wait Times & Best Time to Call</h2>
<h2>Common Reasons People Call</h2>
<h2>Phone Menu Tips</h2>
<h2>Frequently Asked Questions</h2>
<h2>Other Contact Methods</h2>
<h2>Helpful Tips</h2>

Make it natural, informative and 800-1300 words long.
Return ONLY the HTML formatted content. No extra explanation."""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.7, 'num_predict': 5000}
        )
        desc = response['message']['content'].strip()
        return desc if len(desc) > 200 else None
    except Exception as e:
        print(f"   ❌ Ollama Error: {e}")
        return None


def enrich_cruises(limit=None, dry_run=False):
    """Main Function - Pehle Groq, phir Ollama"""
    
    # Find cruises jo abhi bhi incomplete hain
    query = {
        "$or": [
            {"email": {"$in": ["", None]}},
            {"hours": {"$in": ["", None]}},
            {"description": {"$in": ["", None]}}
        ]
    }
    
    cursor = cruise_collection.find(query)
    if limit:
        cursor = cursor.limit(limit)
    
    cruises = list(cursor)
    
    if not cruises:
        print("✅ All cruises are already fully enriched!")
        return
    
    print(f"🚢 Starting enrichment for {len(cruises)} cruises")
    print(f"   Phase 1: Groq (Structured Data)")
    print(f"   Phase 2: Ollama (Long Description)\n")
    
    if dry_run:
        print("🔍 DRY RUN MODE ENABLED - No changes will be saved\n")

    success = 0

    for idx, cruise in enumerate(cruises, 1):
        name = cruise.get("name", "")
        phone = cruise.get("phone", "")
        
        print(f"[{idx}/{len(cruises)}] 🚢 {name}")

        update_fields = {"updated_at": datetime.now(timezone.utc)}

        # ==================== PHASE 1: Groq Structured Fields ====================
        print("   → Fetching structured data from Groq...")
        groq_data = enrich_structured_fields_groq(name, phone)
        
        if groq_data:
            for key, value in groq_data.items():
                # Update only if field is missing or empty
                if key not in cruise or not cruise.get(key):
                    update_fields[key] = value

        # ==================== PHASE 2: Ollama Description ====================
        if not cruise.get("description"):
            print("   → Generating long description with Ollama...")
            description = generate_description_ollama(name, phone)
            if description:
                update_fields["description"] = description

        # ==================== Save to Database ====================
        if len(update_fields) > 1:   # updated_at ke alawa kuch hai
            if not dry_run:
                result = cruise_collection.update_one(
                    {"_id": cruise["_id"]},
                    {"$set": update_fields}
                )
                if result.modified_count > 0:
                    success += 1
                    print(f"   ✅ Successfully enriched!\n")
                else:
                    print(f"   ⚠️ No changes made\n")
            else:
                print(f"   🔍 [DRY RUN] Would update {len(update_fields)-1} fields\n")
                success += 1
        else:
            print(f"   ⚠️ Nothing new to update\n")

        time.sleep(1.5)  # Safe delay between requests

    print("="*75)
    print(f"🎉 CRUISE ENRICHMENT COMPLETED!")
    print(f"   Processed : {len(cruises)} cruises")
    print(f"   ✅ Enriched: {success} cruises")
    print("="*75)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Enrich Cruise data - Groq first, then Ollama')
    parser.add_argument('--limit', type=int, help='Limit number of cruises to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen without saving')
    
    args = parser.parse_args()
    
    print("🚀 Cruise Smart Enrichment Started (Groq → Ollama)")
    print("="*75)
    enrich_cruises(limit=args.limit, dry_run=args.dry_run)