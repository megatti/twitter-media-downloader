import asyncio
import filecmp
import os
import pickle
import unittest

import aiohttp
import dotenv
import twitter_media_dl.mediadownloadclient as mdc
import peony
import peony.oauth

from typing import Dict, List


class Test_MediaDownloadClient(unittest.TestCase):
    # Stop mypy from complaining >:/
    consumer_key: str
    consumer_secret: str
    bearer_token: str
    base_folder: str
    user_id: int
    example_tweet_ids: Dict[str, int]
    example_types: Dict[int, str]
    loop: asyncio.AbstractEventLoop
    client: peony.BasePeonyClient
    cached_tweets: Dict[str, peony.data_processing.PeonyResponse]
    delete_later: List[str]
   
    @classmethod
    def setUpClass(cls) -> None:
        try:
            dotenv.load_dotenv("twitter_media_dl\.env")
        finally:
            cls.consumer_key = os.environ["CONSUMER_KEY"]
            cls.consumer_secret = os.environ["CONSUMER_SECRET"]
            cls.bearer_token = os.environ["BEARER_TOKEN"]
            
        cls.base_folder = os.path.join(os.path.dirname(__file__), "tests", "media")
        cls.user_id = 19701628  # @BBC official account
        
        # Should add a "no_media" example to see what happens with no media
        cls.example_tweet_ids = {"single_image":1373486756306165763, 
                                 "multi_image":1412838462206615559, 
                                 "animated_gif":1371930768306540546, 
                                 "video":1372010047056711680, 
                                 "no_media":1373014297895448578}
        cls.example_types = {tweet_id: media_type for media_type, tweet_id in cls.example_tweet_ids.items()}

        cls.loop = asyncio.get_event_loop()
        
        # LikesDownloadClient will be used as the testing client in this case
        # There is no real reason other than it is the "original" client for this project
        # Both LikesD.C. and TimelineD.C. share most functionality due to inheritance
        # so testing one should test the other well
        # Any class specific functionality will be tested separately
        cls.client = mdc.LikesDownloadClient(cls.user_id, 
                                             consumer_key=cls.consumer_key, 
                                             consumer_secret=cls.consumer_secret,
                                             bearer_token=cls.bearer_token,
                                             auth=peony.oauth.OAuth2Headers, 
                                             base_folder=cls.base_folder)

        # Get the tweets once when setting up, then just use these for each test
        # Will hopefully help avoid rate limits :s
        # Hmm, might need to do something about tweets being deleted in the future...
        # Have a whole collecion of tweets that it chooses one at random from? :thinking:
        # Seems a bit odd to have randomness like that in unit tests though...
        cls.cached_tweets = {}
        id_list = list(cls.example_tweet_ids.values())
        tweets = cls.loop.run_until_complete(cls.client.api.statuses.lookup.get(id=id_list, tweet_mode="extended"))

        for tweet in tweets:
            cls.cached_tweets[cls.example_types[tweet.id]] = tweet

        cls.delete_later = []  # keep track of any files to delete after testing is complete

    
    @classmethod
    def tearDownClass(cls) -> None:
        # Delete any downloaded files
        for deleteable in cls.delete_later:
            try:
                os.remove(deleteable)
            except OSError:
                pass
        # Close the client to end it properly
        cls.loop.run_until_complete(cls.client.close())


    def test_get_media_details(self):
        # Loading the expected results which were saved to pickle files
        expected = dict()
        for media_type in self.example_tweet_ids.keys():
            with open(os.path.join("tests", "expected", f"{media_type}_media_details.pickle"), "rb") as f:
                expected[media_type] = pickle.load(f)

        # Check that the media titles match what they should be
        for media_type, tweet in self.cached_tweets.items():
            with self.subTest(media_type=media_type):
                result = mdc.get_media_details([tweet])
                self.assertEqual(result, expected[media_type])


    def test_get_filename(self):
        expected = {"single_image":["img2021-03-21-040855_sad-istfied_0_1373486756306165763_Ew-a7MFU8AANIL9.jpg"], 
                    "multi_image":["img2021-07-07-181833_dooblebugs_0_1412838462206615559_E5totsvVUAYexVX.png", 
                                   "img2021-07-07-181833_dooblebugs_1_1412838462206615559_E5towDIVUAM0xv9.png", 
                                   "img2021-07-07-181833_dooblebugs_2_1412838462206615559_E5toyv_VgAMmKwD.png", 
                                   "img2021-07-07-181833_dooblebugs_3_1412838462206615559_E5to1YdUYAI9eek.png"], 
                    "animated_gif":["gif2021-03-16-210559_dnoodels_1371930768306540546.mp4"], 
                    "video":["video2021-03-17-022100_megateyourbagel_1372010047056711680.mp4"], 
                    "no_media":[]}

        for media_type, tweet in self.cached_tweets.items():
            with self.subTest(media_type=media_type):
                media_details = mdc.get_media_details([tweet])
                result = []
                # Each media_details is a list for each media in a tweet
                for info in media_details:
                    result.append(mdc.get_filename(info))
                self.assertEqual(result, expected[media_type])

    
    def test_download_media(self):
        expected = {"img2021-03-21-040855_sad-istfied_0_1373486756306165763_Ew-a7MFU8AANIL9.jpg": "single_image_media.jpg", 
                    "img2021-07-07-181833_dooblebugs_0_1412838462206615559_E5totsvVUAYexVX.png": "multi_image_media1.png", 
                    "img2021-07-07-181833_dooblebugs_1_1412838462206615559_E5towDIVUAM0xv9.png": "multi_image_media2.png", 
                    "img2021-07-07-181833_dooblebugs_2_1412838462206615559_E5toyv_VgAMmKwD.png": "multi_image_media3.png", 
                    "img2021-07-07-181833_dooblebugs_3_1412838462206615559_E5to1YdUYAI9eek.png": "multi_image_media4.png", 
                    "gif2021-03-16-210559_dnoodels_1371930768306540546.mp4": "animated_gif_media.mp4", 
                    "video2021-03-17-022100_megateyourbagel_1372010047056711680.mp4": "video_media.mp4"}
        # Maybe wrap this in an async function somewhere :|
        for tweet in self.cached_tweets.values():
            media_details = mdc.get_media_details([tweet])
            # Each media_details is a list for each media in a tweet
            for info in media_details:
                filename = mdc.get_filename(info)
                all_file, artist_file = self.loop.run_until_complete(mdc.download_file(filename, info, None, new_session=True, base_folder=self.base_folder))
                self.delete_later.extend((all_file, artist_file))
                expected_file = os.path.join("tests", "expected", f"{expected[filename]}")
                with self.subTest(filename=filename):
                    self.assertTrue(filecmp.cmp(all_file, expected_file) and filecmp.cmp(artist_file, expected_file))
                

    def test_get_media(self):
        # Test e.g. quote tweet recursion works
        # Use quote tweet as example, then check length of medias result
        pass


    def test_save_history(self):
        # Add urls to current media_urls (assert that it actually adds them)
        media_details = mdc.get_media_details(self.cached_tweets.values())
        self.client.media_urls.update([media["url"] for media in media_details])
        self.assertTrue(len(self.client.media_urls) > 0)
        # Save data
        logfile = self.client.save_history()

        # Load data back into a set
        saved_data = set()
        with open(logfile, "r") as log:
            saved_data.update([url.strip() for url in log.readlines()])

        # Check that current data matches the saved data
        self.assertEqual(self.client.media_urls, saved_data)


    def test_load_history(self):
        # check that the set it loads to ends up having all of the urls
        expected_urls = {"https://pbs.twimg.com/media/E5totsvVUAYexVX.png:orig", 
                         "https://pbs.twimg.com/media/E5to1YdUYAI9eek.png:orig", 
                         "https://video.twimg.com/ext_tw_video/1372009605736194048/pu/vid/1280x720/l3Ujw1tsP7jWvOSg.mp4?tag=12", 
                         "https://video.twimg.com/tweet_video/EwoThfmWgAs-FAz.mp4", 
                         "https://pbs.twimg.com/media/Ew-a7MFU8AANIL9.jpg:orig", 
                         "https://pbs.twimg.com/media/E5toyv_VgAMmKwD.png:orig", 
                         "https://pbs.twimg.com/media/E5towDIVUAM0xv9.png:orig"}

        self.client.media_urls.clear()
        self.client.load_history(search_folder=os.path.join("tests", "expected"))

        self.assertEqual(expected_urls, self.client.media_urls, msg=self.client.media_urls)
    # Add tests for adding media to queue and getting media from queue? Not sure



if __name__ == "__main__":
    unittest.main()