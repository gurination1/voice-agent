import os
import requests
from dotenv import load_dotenv

def buy_exotel_number():
    load_dotenv()
    api_key = os.getenv("EXOTEL_API_KEY")
    api_token = os.getenv("EXOTEL_API_TOKEN")
    sid = os.getenv("EXOTEL_ACCOUNT_SID")
    subdomain = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.in")

    if not all([api_key, api_token, sid]):
        print("Error: Exotel credentials not found in environment variables.")
        return

    url = f"https://{api_key}:{api_token}@{subdomain}/v1/Accounts/{sid}/IncomingPhoneNumbers.json"
    
    data = {
        "AreaCode": "011",
        "PhoneNumberType": "mobile"
    }
    
    print(f"Purchasing number from Exotel...")
    response = requests.post(url, data=data)
    
    if response.status_code == 200:
        res_json = response.json()
        number = res_json.get("IncomingPhoneNumber", {}).get("PhoneNumber")
        if not number:
            print("Failed to parse number from response:", res_json)
            return
        
        print(f"Successfully purchased number: {number}")
        
        # Save to .env
        env_file = ".env"
        env_lines = []
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                env_lines = f.readlines()
        
        with open(env_file, "w") as f:
            found = False
            for line in env_lines:
                if line.startswith("EXOTEL_PHONE_NUMBER="):
                    f.write(f"EXOTEL_PHONE_NUMBER={number}\n")
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f"EXOTEL_PHONE_NUMBER={number}\n")
        print(f"Saved EXOTEL_PHONE_NUMBER={number} to .env")
    else:
        print(f"Failed to purchase number: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    buy_exotel_number()
