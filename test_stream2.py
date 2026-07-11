import os, requests
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("EXOTEL_API_KEY")
api_token = os.getenv("EXOTEL_API_TOKEN")
sid = "gurdharam1"
exotel_number = "08047286472"

url = f"https://api.exotel.com/v1/Accounts/{sid}/Calls/connect.json"
data = {
    "From": "+919041172159",
    "CallerId": exotel_number,
    "StreamType": "bidirectional",
    "StreamUrl": "wss://ai-calling-production-f58d.up.railway.app/audio-stream"
}
response = requests.post(url, auth=(api_key, api_token), data=data)
print(response.status_code, response.text)
