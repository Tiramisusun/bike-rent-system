from dotenv import load_dotenv
load_dotenv()  

import os

class Settings:
    def __init__(self):
        self.openweather_api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.openweather_city = os.getenv("OPENWEATHER_CITY", "Dublin")
        self.openweather_units = os.getenv("OPENWEATHER_UNITS", "metric")

settings = Settings()