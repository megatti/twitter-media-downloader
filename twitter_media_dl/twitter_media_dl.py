import argparse
import logging
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
    BEARER_TOKEN = os.environ["BEARER_TOKEN"]
except KeyError as keyerror:
    raise Exception("Not all required environment variables have been defined.") from keyerror

# Parse command line arguments
sources = ("likes", "timeline", "both")
log_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
copy_options = ("copy", "symlink", "hardlink")
description = "Download media from Twitter attached to a user's Likes and/or Timeline."
parser = argparse.ArgumentParser(description=description)
parser.add_argument("-u", "--user", default=TWITTER_ID, dest="user_id")
parser.add_argument("-m", "--source", default="both", dest="tweet_source", choices=sources)
parser.add_argument("-o", "--output", default="media", dest="output_folder")
parser.add_argument("-l", "--log-level", default="WARNING", dest="log_level", choices="log_levels")
parser.add_argument("-p", "--show-progress", dest="show_progress",
                    action="store_true")  # defaults to False
parser.add_argument("-c", "--copytype", default="copy", dest="copytype", choices=copy_options)

cmd_args = parser.parse_args()

logging.basicConfig(format="%(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(cmd_args.log_level)

base_folder = os.path.join(os.path.dirname(__file__), "..", "media")
kwargs = {"consumer_key": CONSUMER_KEY,
          "consumer_secret": CONSUMER_SECRET,
          "bearer_token": BEARER_TOKEN,
          "auth": peony.oauth.OAuth2Headers,
          "base_folder": base_folder,
          "log_level": cmd_args.log_level,
          "show_progress": cmd_args.show_progress,
          "copytype": cmd_args.copytype}

if cmd_args.tweet_source in ("both", "likes"):
    try:
        logger.info("Beginning to download likes media...")
        likes_client = LikesDownloadClient(cmd_args.user_id, **kwargs)
        likes_client.run()
    finally:
        logger.info("Saving data...")
        likes_client.save_history()

if cmd_args.tweet_source in ("both", "timeline"):
    try:
        logger.info("Beginning to download timeline media...")
        timeline_client = TimelineDownloadClient(cmd_args.user_id, **kwargs)
        timeline_client.run()
    finally:
        logger.info("Saving data...")
        timeline_client.save_history()
