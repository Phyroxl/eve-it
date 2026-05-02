import json
import os
import time
from pathlib import Path

def check_session():
    session_file = Path("config/esi_session.json")
    if not session_file.exists():
        print("Session file does NOT exist.")
        return

    try:
        data = json.loads(session_file.read_text(encoding='utf-8'))
        print(f"Character ID: {data.get('char_id')}")
        print(f"Character Name: {data.get('char_name')}")
        print(f"Has Access Token: {bool(data.get('access_token'))}")
        print(f"Has Refresh Token: {bool(data.get('refresh_token'))}")
        expires_at = data.get('expires_at', 0)
        remaining = expires_at - time.time()
        print(f"Expires in: {int(remaining)}s")
        print(f"Scopes: {data.get('scopes')}")
        
        # Check refresh token length or format (sanitized)
        rt = data.get('refresh_token', '')
        if rt:
            print(f"Refresh Token prefix: {rt[:5]}... (len: {len(rt)})")
        else:
            print("Refresh Token is EMPTY or NONE")
            
    except Exception as e:
        print(f"Error reading session: {e}")

if __name__ == "__main__":
    check_session()
