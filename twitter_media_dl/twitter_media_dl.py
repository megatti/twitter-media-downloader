import datetime
import glob
import os

import dotenv

from mediadownloadclient import LikesDownloadClient, TimelineDownloadClient

dotenv.load_dotenv()

# Load environment variables
try:
    TWITTER_ID = os.environ["TWITTER_ID"]
    CONSUMER_KEY = os.environ["CONSUMER_KEY"]
    CONSUMER_SECRET = os.environ["CONSUMER_SECRET"]
    ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
    ACCESS_TOKEN_SECRET = os.environ["ACCESS_TOKEN_SECRET"]
except KeyError:
    raise Exception("Not all required environment variables have been defined.")

base_folder = os.path.join(os.path.dirname(__file__), "..", "media")
kwargs = {"consumer_key": CONSUMER_KEY, 
            "consumer_secret": CONSUMER_SECRET, 
            "access_token": ACCESS_TOKEN, 
            "access_token_secret": ACCESS_TOKEN_SECRET, 
            "base_folder": base_folder}

try:
    print("Beginning to download likes media...")
    likes_client = LikesDownloadClient(TWITTER_ID, **kwargs)
    likes_client.run()
finally:
    print("Saving data...")
    likes_client.save_history()
            
try:
    print("Beginning to download likes media...")
    timeline_client = TimelineDownloadClient(TWITTER_ID, **kwargs)
    timeline_client.run()
finally:
    print("Saving data...")
    timeline_client.save_history()
