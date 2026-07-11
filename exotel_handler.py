import os
import requests
from dotenv import load_dotenv

load_dotenv()

def initiate_outbound_call(lead_phone_number: str, railway_url: str):
    api_key = os.getenv("EXOTEL_API_KEY")
    api_token = os.getenv("EXOTEL_API_TOKEN")
    sid = os.getenv("EXOTEL_ACCOUNT_SID")
    subdomain = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.in")
    exotel_number = os.getenv("EXOTEL_PHONE_NUMBER")
    
    if not railway_url.startswith("https://"):
        railway_url = f"https://{railway_url}"
        
    url = f"https://api.exotel.com/v1/Accounts/{sid}/Calls/connect.json"
    
    data = {
        "From": lead_phone_number,
        "CallerId": exotel_number,
        "StreamType": "bidirectional",
        "StreamUrl": f"wss://{railway_url.replace('https://', '')}/audio-stream",
        "StatusCallback": f"{railway_url}/call-status",
        "Record": "true"
    }
    
    response = requests.post(url, auth=(api_key, api_token), data=data)
    response.raise_for_status()
    return response.json()
