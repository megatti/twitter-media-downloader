import asyncio
import glob
import os
import warnings

import aiofiles
import aiohttp
import dateutil.parser
import peony
import slugify

from typing import List, Dict, Set, Union

TweetList = List[peony.data_processing.PeonyResponse]

def get_media(tweet: peony.data_processing.PeonyResponse, medias: List=[], 
              depth: int=1, max_depth: int=10):
    """Needs to deal with:
    - plain tweet
    - retweet
    - quote tweet
    - replies

    Needs recursion limit option
    Needs memoisation or something ;_;

    Returns
    -------
    medias - list of tuples: [(tweet object, a media in that tweet, media_index)]
    """
    medias = []  # Set so any duplicate things aren't double counted
    # first, get media from the tweet itself
    try:
        for media_index, media in enumerate(tweet.extended_entities.media):
            medias.append((tweet, media, media_index))
    except AttributeError:  # tweet has no media itself
        pass
    # Then, get media from the retweet - what about the retweeted tweets info i.e. username, date, etc.?
    # Lets deal with that later :)
    if depth < max_depth:
        try:
            medias = get_media(tweet.retweeted_status, medias=medias, depth=depth+1, max_depth=max_depth)
        except AttributeError:  # retweeted tweet has no media itself
            pass

        try:
            medias = get_media(tweet.quoted_status, medias=medias, depth=depth+1, max_depth=max_depth)
        except AttributeError:  # quoted tweet has no media itself
            pass

    return medias
    # Get media from the tweet that this tweet is replying to
    # Turns out this is a harder problem than expected :/
    # Ignore replies for now


def get_media_details(tweets: TweetList, mode: str) -> List[Dict[str, Union[str, int]]]:
    """
    Returns a list of dictionaries, each dictionary containing info on the media in the tweet.
    For quote tweets, returns info on both the quote tweet itself and the quoted tweet.
    This occurs recursively until the "bottom" tweet is reached, or until some level of recursion.
    Same applies to replies.
    
    Parameters
    ----------
    client - peony.PeonyClient object
    tweets  - A list of tweets / statuses. Each tweet *must* have extended_mode = True
    
    Returns
    -------
    result_list - list of dictionaries containing info about media in the tweets.
    """
    result_list = []
    
    for base_tweet in tweets:
        medias = get_media(base_tweet)  # Retweets might expand with their base plus retweeted tweet's media
        for (tweet, media, media_index) in medias:
            media_info_dict: Dict[str, Union[str, int]] = {}
                
            media_info_dict["author"] = slugify.slugify(tweet.user.screen_name)  # Their @xxxx handle (without the @)
            media_info_dict["date"] = tweet.created_at
            media_info_dict["id"] = tweet.id
            media_info_dict["type"] = media.type
            media_info_dict["index"] = media_index

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

            result_list.append(media_info_dict)
        
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
                        base_folder: str =os.path.join(os.path.dirname(__file__), "..", "media")) -> None:
    if new_session:
        session = aiohttp.ClientSession()

    # 2 download locations
    all_folder = os.path.join(base_folder, "__all__", filename)
    artist_folder = os.path.join(base_folder, media_details['author'], filename)

    # Download to both locations at the same time, retry 5 times per image
    retry_count = 0
    while retry_count <= 5:
        retry_count += 1
        try:
            # Open both files at once
            async with aiofiles.open(all_folder, "wb") as base_file, aiofiles.open(artist_folder, "wb") as artist_file:
                async with session.get(media_details["url"], timeout=600) as response:
                    if response.ok:
                        # Write with a stream, so large videos don't destroy the memory (lol)
                        while True:
                            chunk = await response.content.read(5000000)  # 5MB chunks
                            if not chunk:  # No more data
                                break
                            await base_file.write(chunk)
                            await artist_file.write(chunk)
                        # Finished, so stop now
                        break
        except FileNotFoundError as e:
            # Try making the main folder and the artist folder
            os.makedirs(os.path.join(base_folder, "__all__"), exist_ok=True)
            os.makedirs(os.path.join(base_folder, media_details['author']), exist_ok=True)
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

    if retry_count > 5:
        # Didn't work - keep track of these?
        pass

    if new_session:
        await session.close()


class MediaDownloadClient(peony.PeonyClient):

    def __init__(self, user_id: str, *args, mode: str="both", 
                 base_folder: str=os.path.join(os.path.dirname(__file__), "..", "media"),
                 queuesize: int=50, **kwargs):
        self.base_folder = base_folder
        self.mode = mode
        self.user_id = user_id
        super().__init__(*args, **kwargs)

        # General startup actions, e.g. load image urls
        self.img_urls: Set[str] = set()
        self.dupes = 0
        self.media_queue: asyncio.Queue = asyncio.Queue(maxsize=queuesize)
        
        # Loading image_urls previously downloaded
        try:
            filename = glob.glob(os.path.join(self.base_folder, "img_urls*.txt"))[0]
            with open(filename, "r") as f:
                self.img_urls.update(line.strip() for line in f.readlines())
        except IndexError:
            warnings.warn("No img_urls.txt file found! Continuing without a history log...")
            # This should probably raise an exception or something :| hmmmm
        
    
    @peony.task
    async def add_media_to_queue(self, count: int =800, max_tweets: int =4000) -> None:
        # start going through the likes - split behaviour for likes vs timeline
        if self.mode == "likes":
            request = self.api.favorites.list.get(id=self.user_id, count=count, tweet_mode="extended")
        elif self.mode == "timeline":
            request = self.api.statuses.user_timeline.get(id=self.user_id, count=count, tweet_mode="extended", include_rts=True)
        
        responses = request.iterator.with_max_id()
        
        self.my_tweet_count = 0
        # responses is a list of Tweet objects
        async for tweets_list in responses:
            media_details_list = get_media_details(tweets_list, self.mode)  # pass in a list of tweets, get a list out
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
        while True:
            media_details = await self.media_queue.get()  # a single dictionary
            # Deal with ending the consumer
            if media_details is None:
                break
            
            # Otherwise, do the consuming
            filename = get_filename(media_details)
            
            await download_file(filename, media_details, self._session, 
                                base_folder=os.path.join(self.base_folder, self.mode))
            self.img_urls.add(media_details["url"])
