import abc
import asyncio
import datetime
import glob
import os
import warnings

from typing import Any, List, Dict, Set, Tuple, Union

import aiohttp
import dateutil.parser
import peony
import slugify


TweetList = List[peony.data_processing.PeonyResponse]
MediaList = List[Tuple[peony.data_processing.PeonyResponse, peony.data_processing.JSONData, int]]

def get_media(tweet: peony.data_processing.PeonyResponse, medias: List=None,
              depth: int=1, max_depth: int=10) -> MediaList:
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
    # First, get media from the tweet itself
    if medias is None:
        medias = []

    try:
        for media_index, media in enumerate(tweet.extended_entities.media):
            medias.append((tweet, media, media_index))
    except AttributeError:  # tweet has no media itself
        pass
    # Then, get media from the retweet
    # What about the retweeted tweet's info i.e. username, date, etc.?
    # Lets deal with that later :)
    if depth < max_depth:
        try:
            medias = get_media(tweet.retweeted_status, medias=medias,
                               depth=depth+1, max_depth=max_depth)
        except AttributeError:  # retweeted tweet has no media itself
            pass

        try:
            medias = get_media(tweet.quoted_status, medias=medias,
                               depth=depth+1, max_depth=max_depth)
        except AttributeError:  # quoted tweet has no media itself
            pass

    return medias
    # Get media from the tweet that this tweet is replying to
    # Turns out this is a harder problem than expected :/
    # Ignore replies for now


def get_media_details(tweets: TweetList) -> List[Dict[str, Union[str, int]]]:
    """
    Returns a list of dictionaries, each dictionary containing info on the media in the tweet.
    For quote tweets, returns info on both the quote tweet itself and the quoted tweet.
    This occurs recursively until the "bottom" tweet is reached, or until some level of recursion.
    Same applies to replies.

    Parameters
    ----------
    tweets  - A list of tweets / statuses. Each tweet *must* have extended_mode = True

    Returns
    -------
    result_list - list of dictionaries containing info about media in the tweets.
    """
    result_list = []

    for base_tweet in tweets:
        medias = get_media(base_tweet)  # Retweets might expand with retweeted tweet's media
        for (tweet, media, media_index) in medias:
            media_info_dict: Dict[str, Union[str, int]] = {}

            media_info_dict["author"] = slugify.slugify(tweet.user.screen_name)  # Their @xxx handle
            media_info_dict["date"] = tweet.created_at
            media_info_dict["id"] = tweet.id
            media_info_dict["type"] = media.type
            media_info_dict["index"] = media_index

            # Deal with images
            if media.type == "photo":
                media_info_dict["url"] = media.media_url_https + ":orig"  # Highest quality

            # animated_gif and video are treated the same
            elif media.type == "animated_gif" or media.type == "video":
                max_bitrate = -1
                # Find highest quality variant
                for variant in media.video_info.variants:
                    #  some variants have a different content type (m3u8) - ignore these
                    #  m3u8 is a text-based playlist file - contains some info but it's weird :(
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
                        base_folder: str =os.path.join(os.path.dirname(__file__), "..", "media")
                        ) -> Tuple[str, str]:
    """
    Downloads a piece of media from Twitter. The item is downloaded to two folders
    under base_folder: an "__all__" folder used to collect all pieces of media, and
    an "{author}" folder used to collect all media from a specific Twitter user.

    Parameters
    ----------
    filename: str
        Filename to give to the downloaded file.
    media_details: dict
        Dictionary containing relevant information about the file to download.
        The used information is the media's author and the url of the media to
        download from.
    session: aiohttp.ClientSession
        An aiohttp session to use when making the request for the data to download.

    new_session: bool, default = False
        Whether to use a new aiohttp session or not, which would require closing afterwards.
        Used mainly for testing purposes.
    base_folder: str, default = os.path.join(os.path.dirname(__file__), "..", "media")
        Base folder in which to place the downloaded file.
        Defaults to a sibling folder named 'media'.

    Returns
    -------
    (all_folder, artist_folder): (str, str)
        Returns the locations of the files that were downloaded as a tuple pair.
    """
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
            with open(all_folder, "wb") as base_file, open(artist_folder, "wb") as artist_file:
                async with session.get(media_details["url"], timeout=600) as response:
                    if response.ok:
                        # Write with a stream, so large videos don't destroy the memory
                        async for chunk in response.content.iter_any():
                            base_file.write(chunk)
                            artist_file.write(chunk)
                        break
        except FileNotFoundError:
            # Try making the main folder and the artist folder
            os.makedirs(os.path.join(base_folder, "__all__"), exist_ok=True)
            os.makedirs(os.path.join(base_folder, media_details['author']), exist_ok=True)
        except asyncio.TimeoutError:
            # Timed out :/
            # What to do, what to do...
            # Maybe delay for a bit?
            asyncio.sleep(10)
        except aiohttp.client_exceptions.ClientConnectorError:
            # This is a weird error that I don't really understand the cause of :)))
            # But it keeps coming up so I'm just going to tell it to retry
            asyncio.sleep(10)
        except aiohttp.client_exceptions.ClientPayloadError:
            # Another strange error that I have just started to get
            # yayyyy
            asyncio.sleep(10)

    if retry_count > 5:
        # Didn't work - keep track of these to retry after?
        pass

    if new_session:
        await session.close()

    return (all_folder, artist_folder)


client_type: Any = type(peony.PeonyClient)
class MDCMeta(abc.ABCMeta, client_type):
    """Metaclass for the MediaDownloadClient abstract class, based on a peony client."""


class MediaDownloadClient(peony.BasePeonyClient, abc.ABC, metaclass=MDCMeta):
    def __init__(self, user_id: str, *args,
                 base_folder: str=os.path.join(os.path.dirname(__file__), "..", "media"),
                 queuesize: int=100, **kwargs):
        self.base_folder = base_folder
        self.user_id = user_id
        self.tweet_count = 0
        self.dupes = 0
        self.media_count = 0
        self.media_queue: asyncio.Queue = asyncio.Queue(maxsize=queuesize)
        super().__init__(*args, **kwargs)

        # Load image urls
        self.media_urls: Set[str] = set()
        self.load_history()


    def load_history(self, search_folder=None):
        """Loads history of urls of media downloaded from a text file."""
        if not search_folder:
            search_folder = self.base_folder

        try:
            # Get latest history file
            logfile = glob.glob(os.path.join(search_folder, f"{self.tweet_source}_urls*.txt"))[-1]
            with open(logfile, "r") as file:
                self.media_urls.update(line.strip() for line in file.readlines())
        except IndexError:
            warnings.warn(f"No {self.tweet_source}_urls.txt file found!"
                          " Continuing with no history...")


    def save_history(self):
        """Saves self.urls to a text file."""
        # Move old history to backup folder
        os.makedirs(os.path.join(self.base_folder, f"{self.tweet_source}_urls_backups"),
                    exist_ok=True)
        current_media_urls = glob.glob(os.path.join(self.base_folder,
                                                    f"{self.tweet_source}_urls-*.txt"))
        for logfile in current_media_urls:  # could be multiple files
            dest_file = os.path.join(self.base_folder, f"{self.tweet_source}_urls_backups",
                                     os.path.basename(logfile))
            os.rename(logfile, dest_file)

        # Save new history - yyyymmddHHMMSS
        current_time = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
        # Make new version's filename
        new_filename = os.path.join(self.base_folder,
                                    f"{self.tweet_source}_urls-{current_time}.txt")
        with open(new_filename, "w") as file:  # Save as a text file to read later
            for url in self.media_urls:
                file.write(url + "\n")

        return new_filename


    def print_progress(self):
        """Prints progress of downloading to output.
        Prints source, number of pieces of media downloaded, and size of queue."""
        prefix = f"Crawling {self.tweet_source}. ".ljust(17)
        print(f"{prefix}{self.media_queue.qsize()} tweet(s) in queue,"
              f" {self.media_count} items downloaded.", end="\r")


    @abc.abstractmethod
    def send_request(self, count):
        pass


    @peony.task
    async def add_media_to_queue(self, count: int =800, max_tweets: int =4000) -> None:
        # Start going through the tweets
        request = self.send_request(count)
        responses = request.iterator.with_max_id()

        # responses is a list of Tweet objects
        async for tweets_list in responses:
            # In: list(tweets), out: list(media_details)
            media_details_list = get_media_details(tweets_list)
            for media_details in media_details_list:
                # Skip ones that have already been downloaded
                if media_details["url"] in self.media_urls:
                    self.dupes += 1  # Keep track of number of duplicates
                    continue  # URL has already been downloaded, so continue to next one

                await self.media_queue.put(media_details)  # put in dictionary of media info
                self.print_progress()

            self.tweet_count += len(tweets_list)  # keep track of the number of tweets processed
            if self.tweet_count >= max_tweets:
                break
        # Finally, stick a None in the queue to end the process
        await self.media_queue.put(None)


    @peony.task
    async def download_media_from_queue(self):
        while True:
            media_details = await self.media_queue.get()  # a single dictionary
            # Deal with ending the consumer
            if media_details is None:
                self.print_progress()
                # Done with progress text, so go to next line
                print(f"\n{self.tweet_source.capitalize()} done!")
                break

            # Otherwise, consume the next piece of media
            filename = get_filename(media_details)
            await download_file(filename, media_details, self._session,
                                base_folder=os.path.join(self.base_folder, self.tweet_source))

            self.media_urls.add(media_details["url"])
            self.media_count += 1
            # Update progress string
            self.print_progress()


class LikesDownloadClient(MediaDownloadClient):
    def __init__(self, *args, **kwargs):
        self.tweet_source = "likes"
        super().__init__(*args, **kwargs)


    def send_request(self, count):
        return self.api.favorites.list.get(id=self.user_id, count=count,
                                           tweet_mode="extended")


class TimelineDownloadClient(MediaDownloadClient):
    def __init__(self, *args, **kwargs):
        self.tweet_source = "timeline"
        super().__init__(*args, **kwargs)


    def send_request(self, count):
        return self.api.statuses.user_timeline.get(id=self.user_id, count=count,
                                                   tweet_mode="extended", include_rts=True)
