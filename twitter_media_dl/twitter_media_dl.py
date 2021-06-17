import datetime
import glob
import os

import dotenv

from mediadownloadclient import MediaDownloadClient

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

try:
    print("Beginning to download media...")
    base_folder = os.path.join(os.path.dirname(__file__), "..", "media")
    kwargs = {"consumer_key": CONSUMER_KEY, 
              "consumer_secret": CONSUMER_SECRET, 
              "access_token": ACCESS_TOKEN, 
              "access_token_secret": ACCESS_TOKEN_SECRET, 
              "base_folder": base_folder}
    my_client = MediaDownloadClient(TWITTER_ID, **kwargs)
    my_client.run()
finally:
    print("Saving data...")

    # Move current history to backup folder
    backup_folder = "img_urls_backups"
    os.makedirs(os.path.join(base_folder, backup_folder), exist_ok=True)
    old_history = glob.glob(os.path.join(base_folder, "img_urls-*.txt"))
    for img_url in old_history:  # could be multiple files?? shouldn't be though
        filename = os.path.basename(img_url)
        destination = os.path.join(base_folder, backup_folder, filename)
        os.rename(img_url, destination)
    
    # Save new history
    current_time = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    new_filename = os.path.join(base_folder, f"img_urls-{current_time}.txt") # Make new version's filename
    with open(new_filename, "w") as file:  # Save as a text file to read later
        for url in my_client.img_urls:
            file.write(url + "\n")
            