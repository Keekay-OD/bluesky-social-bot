#!/usr/bin/env python3
from atproto import Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/app/.env')

handle = os.getenv('BLUESKY_HANDLE')
password = os.getenv('BLUESKY_PASSWORD')

print(f"Testing login with:")
print(f"Handle: {handle}")
print(f"Password length: {len(password)} characters")

try:
    client = Client()
    client.login(handle, password)
    print("✅ Login successful!")
    print(f"Logged in as: {client.me.handle}")
except Exception as e:
    print(f"❌ Login failed: {e}")
    print(f"Error type: {type(e).__name__}")