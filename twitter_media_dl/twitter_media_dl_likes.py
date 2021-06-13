import aiofiles
import aiohttp
import asyncio
import datetime
import dateutil.parser
import dotenv
import glob
import os
import peony
import slugify
import warnings

from typing import List, Dict, Set, Union, TextIO

TweetList = List[peony.data_processing.PeonyResponse]

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

def get_media_details(tweets: TweetList) -> List[Dict[str, Union[str, int]]]:
    """
    Returns a list of dictionaries, each dictionary containing info on the media in the tweet.
    
    Parameters
    ----------
    client - peony.PeonyClient object
    tweets  - A list of tweets / statuses. Each tweet *must* have extended_mode = True
    
    Returns
    -------
    result_list - list of dictionaries containing info about media in the tweets.
    """
    result_list = []
    
    for tweet in tweets:
        try:
            # this is where the media on a tweet in extended_mode is
            # for media_index, media in enumerate(tweet.data.extended_entities.media, 1):
            for media_index, media in enumerate(tweet.extended_entities.media, 1):
                media_info_dict: Dict[str, Union[str, int]] = {}
                
                # media_info_dict["author"] = slugify.slugify(tweet.data.user.screen_name)  # Their @xxxx handle (without the @)
                # media_info_dict["date"] = tweet.data.created_at
                media_info_dict["author"] = slugify.slugify(tweet.user.screen_name)  # Their @xxxx handle (without the @)
                media_info_dict["date"] = tweet.created_at
                media_info_dict["id"] = tweet.id
                
                # Deal with images
                if media.type == "photo":
                    media_info_dict["url"] = media.media_url_https + ":orig"  # To get the highest quality

                # animated_gif and video are treated the same
                elif media.type == "animated_gif" or media.type == "video":
                    max_bitrate = -1
                    # To find highest quality variant
                    for variant in media.video_info.variants:
                        #  some variants have a different content type (m3u8) - ignore these
                        #  m3u8 is a text-based playlist file apparently - contains some info but it's weird :(
                        if variant.content_type == "video/mp4" and variant.bitrate > max_bitrate:
                            max_bitrate = variant.bitrate
                            max_url = variant.url
                    media_info_dict["url"] = max_url

                media_info_dict["type"] = media.type
                media_info_dict["index"] = media_index
                result_list.append(media_info_dict)

        except AttributeError as e:
            # print("No extended_entities on this tweet.")
            # print(e)
            pass
        
    return result_list

def get_filename(media_info: Dict[str, str]) -> str:
    """
    Transform the tweet's information into an appropriate filename to help with recognising
    the file afterwards.
    Changes depending on whether the media is an image, video, or gif.
    The general format is:
    "[type][date][time]_[artist].mp4" OR "[type][date][time]_[artist]_[number]_[url].[png/jpg]"

    Examples:
    - video2021-01-30-020601_mrkipler1.mp4
    - img2020-08-02-154843_unrealrui_1_EebTdf4WoAATXof.png
    - gif2020-03-21-122608_rabbitbrush4.mp4
    
    """
    date = dateutil.parser.parse(media_info["date"]).strftime("%Y-%m-%d-%H%M%S")
    artist = media_info["author"]
    index = media_info["index"]
    url_type = media_info["url"].split("/")[-1].split(":")[0]
    id_ = media_info["id"]
    if media_info["type"] == "photo":
        filename = f"img{date}_{artist}_{index}_{id_}_{url_type}"
        
    elif media_info["type"] == "video":
        filename = f"video{date}_{artist}_{id_}.mp4"
        
    elif media_info["type"] == "animated_gif":
        filename = f"gif{date}_{artist}_{id_}.mp4"
        
    return filename


async def download_file(filename: str, media_details: Dict[str, str], 
                        session: aiohttp.ClientSession, new_session: bool =False, 
                        base_folder: str ="..\\media\\Likes") -> None:
    if new_session:
        session = aiohttp.ClientSession()
    # 2 final locations
    all_folder = f"{base_folder}\\__all__\\{filename}"
    artist_folder = f"{base_folder}\\{media_details['author']}\\{filename}"

    # Download to both locations at the same time :O
    retry_count = 0
    while retry_count <= 5:
        retry_count += 1
        try:
            # Open both files at once
            async with aiofiles.open(all_folder, "wb") as all_file, aiofiles.open(artist_folder, "wb") as artist_file:
                async with session.get(media_details["url"], timeout=600) as response:
                    if response.ok:
                        # Write with a stream, so large videos don't destroy the memory (lol)
                        while True:
                            chunk = await response.content.read(5000000)  # 5MB chunks
                            if not chunk:  # No more data
                                break
                            await all_file.write(chunk)
                            await artist_file.write(chunk)
                        # Finished, so stop now
                        break
        except FileNotFoundError as e:
            # Try making the main folder and the artist folder
            os.makedirs(f"{base_folder}\\__all__\\", exist_ok=True)
            os.makedirs(f"{base_folder}\\{media_details['author']}\\", exist_ok=True)
        except asyncio.TimeoutError as e:
            # Timed out :/
            # What to do, what to do...
            # Maybe delay for a bit?
            asyncio.sleep(10)
            pass
        except aiohttp.client_exceptions.ClientConnectorError as e:
            # This is a weird error that I don't really understand the cause of :)))
            # But it keeps coming up so I'm just going to tell it to retry
            asyncio.sleep(10)
        except aiohttp.client_exceptions.ClientPayloadError as e:
            # Another strange error that I have just started to get
            # yayyyy
            asyncio.sleep(10)
    if new_session:
        await session.close()


class ImageDownloadClient(peony.PeonyClient):
    
    def startup(self, queue_maxsize: int =50, base_folder: str ="..\\media") -> None:
        # General startup actions, e.g.:
        # - Load image urls
        # - Create a copy of the old img_urls? as a backup
        # - Setting count numbers and stuff? idk lol
        self.img_urls: Set[str] = set()
        self.dupes = 0
        self.media_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        
        # Loading image_urls previously downloaded
        try:
            filename = glob.glob("{base_folder}\\img_urls*.txt")[0]
            with open(filename, "r") as f:
                self.img_urls.update(line.strip() for line in f.readlines())
        except IndexError:
            warnings.warn("No img_urls.txt file found! Continuing without a history log...")
            # This should probably raise an exception or something :| hmmmm
        
        # Finish
        self.startup_done = True
        
        
    def check_startup(self) -> None:
        # Check that self.startup was called
        if not getattr(self, "startup_done", False):
            warnings.warn("Startup never called! Calling ImageDownloadClient.startup() now...")
            self.startup()
        
    
    @peony.task
    async def add_media_to_queue(self, user_id: str =TWITTER_ID, count: int =300, max_tweets: int =4000) -> None:
        self.check_startup()  # if startup() hasn't been called, call it
        # start going through the likes
        request = self.api.favorites.list.get(id=user_id, count=count, tweet_mode="extended")
        responses = request.iterator.with_max_id()
        
        # self.my_tweet_count = getattr(self, "my_tweet_count", 0)  # this way it can continue if it starts the task again
        self.my_tweet_count = 0
        # what is tweets? I think it's a list of things
        async for tweets_list in responses:
            media_details_list = get_media_details(tweets_list)  # pass in a list of tweets, get a list out
            for media_details in media_details_list:
                # Skip ones that have already been downloaded
                if media_details["url"] in self.img_urls:
                    self.dupes += 1  # Keep track of number of duplicates
                    continue  # URL has already been downloaded, so stop here
                else:
                    await self.media_queue.put(media_details)  # details is a dictionary of media info
            
            self.my_tweet_count += len(tweets_list)  # keep track of the number of tweets processed
            print(f"Processed to tweet {self.my_tweet_count}")
            if self.my_tweet_count >= max_tweets:
                break
        # Finally, stick a None in the queue to end the process
        await self.media_queue.put(None)


    @peony.task
    async def download_media_from_queue(self):
        self.check_startup()
        while True:
            media_details = await self.media_queue.get()  # a single dictionary
            # Deal with ending the consumer
            if media_details is None:
                break
            
            # Otherwise, do the consuming
            filename = get_filename(media_details)
            
            await download_file(filename, media_details, self._session)
            self.img_urls.add(media_details["url"])


if __name__ == "__main__":
    try:
        print("Beginning to download media...")
        kwargs = {"consumer_key":CONSUMER_KEY, 
                  "consumer_secret":CONSUMER_SECRET, 
                  "access_token":ACCESS_TOKEN, 
                  "access_token_secret":ACCESS_TOKEN_SECRET}
        my_client = ImageDownloadClient(**kwargs)
        my_client.startup()
        my_client.run()
    finally:
        print("Saving data...")

        # Move current history to backup folder
        base_folder = "..\\media"  # Sibling directory
        os.makedirs(f"{base_folder}\\img_urls_backups", exist_ok=True)
        current_img_urls = glob.glob(".\\img_urls-*.txt")
        for img_url_file in current_img_urls:  # could be multiple files?? shouldn't be though
            os.rename(img_url_file, f"{base_folder}\\img_urls_backups\\{img_url_file}")
        
        # Save current version
        current_time = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
        new_filename = f"img_urls-{current_time}.txt" # Make new version's filename
        with open(new_filename, "w") as file:  # Save as a text file to read later
            for url in my_client.img_urls:
                file.write(url + "\n")