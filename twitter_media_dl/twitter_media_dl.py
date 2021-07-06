import argparse
import os

import dotenv
import peony.oauth

from mediadownloadclient import LikesDownloadClient, TimelineDownloadClient

dotenv.load_dotenv()

# Load environment variables
try:
    TWITTER_ID = os.environ["TWITTER_ID"]
    CONSUMER_KEY = os.environ["CONSUMER_KEY"]
    CONSUMER_SECRET = os.environ["CONSUMER_SECRET"]
    ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
    ACCESS_TOKEN_SECRET = os.environ["ACCESS_TOKEN_SECRET"]
    BEARER_TOKEN = os.environ["BEARER_TOKEN"]
except KeyError:
    raise Exception("Not all required environment variables have been defined.")

# Parse command line arguments
sources = ("likes", "timeline", "both")
description = "Download media from Twitter attached to a user's Likes and/or Timeline."
parser = argparse.ArgumentParser(description=description)
parser.add_argument("-u", "--user", default=TWITTER_ID, dest="user_id")
parser.add_argument("-m", "--source", default="both", dest="tweet_source", choices=sources)
parser.add_argument("-o", "--output", default="media", dest="output_folder")

cmd_args = parser.parse_args()
            
base_folder = os.path.join(os.path.dirname(__file__), "..", "media")
kwargs = {"consumer_key": CONSUMER_KEY, 
          "consumer_secret": CONSUMER_SECRET, 
          "bearer_token": BEARER_TOKEN, 
          "auth": peony.oauth.OAuth2Headers, 
          "base_folder": base_folder}

if cmd_args.tweet_source in ("both", "likes"):
    try:
        print("Beginning to download likes media...")
        likes_client = LikesDownloadClient(cmd_args.user_id, **kwargs)
        likes_client.run()
    finally:
        print("Saving data...")
        likes_client.save_history()

if cmd_args.tweet_source in ("both", "timeline"):
    try:
        print("Beginning to download timeline media...")
        timeline_client = TimelineDownloadClient(cmd_args.user_id, **kwargs)
        timeline_client.run()
    finally:
        print("Saving data...")
        timeline_client.save_history()
