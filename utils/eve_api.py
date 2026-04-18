# eve_api.py - ESI API helpers
import requests
def get_character_info(char_id):
    r=requests.get(f'https://esi.evetech.net/latest/characters/{char_id}/')
    return r.json() if r.ok else {}
