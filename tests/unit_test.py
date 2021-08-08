import aiohttp
import asyncio
import filecmp
import peony
from ..twitter_media_dl import peony_bot
import pickle
import unittest

import os
import dotenv

dotenv.load_dotenv()

class Test_Peony(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.consumer_key = os.environ["CONSUMER_KEY"]
        cls.consumer_secret = os.environ["CONSUMER_SECRET"]
        cls.bearer_token = os.environ["BEARER_TOKEN"]
        
        # Should add a "no_media" example to see what happens with no media
        cls.example_tweet_ids = {"single_image":1373486756306165763, 
                               "multi_image":1372798360164339723, 
                               "animated_gif":1371930768306540546, 
                               "video":1372010047056711680, 
                               "no_media":1373014297895448578}
        cls.loop = asyncio.get_event_loop()
        cls.client = peony.PeonyClient(consumer_key=cls.consumer_key,
                                       consumer_secret=cls.consumer_secret,
                                       access_token=cls.access_token,
                                       access_token_secret=cls.access_token_secret)

        # Get the tweets once when setting up, then just use these for each test
        # Will hopefully help avoid rate limits :s
        cls.cached_tweets = {}
        for media_type, tweet_id in cls.example_tweet_ids.items():
            cls.cached_tweets[media_type] = cls.loop.run_until_complete(
                cls.client.api.statuses.show.get(
                    id=cls.example_tweet_ids[media_type], tweet_mode="extended", count=1))


    def test_get_media_details(self):
        expected = dict()
        # Loading the expected results which were saved to pickle files
        for media_type in self.example_tweet_ids.keys():
            with open(f"expected\\{media_type}_media_details.pickle", "rb") as f:
                expected[media_type] = pickle.load(f)

        for media_type, tweet in self.cached_tweets.items():
            with self.subTest(media_type=media_type):
                result = peony_bot.get_media_details([tweet])
                print(result)
                self.assertEqual(result, expected[media_type])


    def test_get_filename(self):
        expected = {"single_image":["img2021-03-21-040855_sad-istfied_1_Ew-a7MFU8AANIL9.jpg"], 
                    "multi_image":["img2021-03-19-063329_k3ttan_1_Ew0o0_jVgAY-DLw.jpg", 
                                   "img2021-03-19-063329_k3ttan_2_Ew0o1KjVoAEXkyx.jpg", 
                                   "img2021-03-19-063329_k3ttan_3_Ew0o1VLVcAA1n91.jpg"], 
                    "animated_gif":["gif2021-03-16-210559_dnoodels.mp4"], 
                    "video":["video2021-03-17-022100_megateyourbagel.mp4"], 
                    "no_media":[]}

        for media_type, tweet in self.cached_tweets.items():
            with self.subTest(media_type=media_type):
                media_details = peony_bot.get_media_details([tweet])
                result = []
                # Each media_details is a list for each media in a tweet
                for info in media_details:
                    result.append(peony_bot.get_filename(info))
                self.assertEqual(result, expected[media_type])

    
    def test_download_media(self):
        expected = {"img2021-03-21-040855_sad-istfied_1_Ew-a7MFU8AANIL9.jpg": "single_image_media.jpg", 
                    "img2021-03-19-063329_k3ttan_1_Ew0o0_jVgAY-DLw.jpg": "multi_image_media1.jpg", 
                    "img2021-03-19-063329_k3ttan_2_Ew0o1KjVoAEXkyx.jpg": "multi_image_media2.jpg", 
                    "img2021-03-19-063329_k3ttan_3_Ew0o1VLVcAA1n91.jpg": "multi_image_media3.jpg", 
                    "gif2021-03-16-210559_dnoodels.mp4": "animated_gif_media.mp4", 
                    "video2021-03-17-022100_megateyourbagel.mp4": "video_media.mp4"}
        # Going to have to wrap this in an async function somewhere :|
        for media_type, tweet in self.cached_tweets.items():
            media_details = peony_bot.get_media_details([tweet])
            # Each media_details is a list for each media in a tweet
            for info in media_details:
                filename = peony_bot.get_filename(info)
                self.loop.run_until_complete(peony_bot.download_file(filename, info, None, new_session=True))
                with self.subTest(filename=filename):
                    self.assertTrue(filecmp.cmp(f"TwitterImages\\__all__\\{filename}", 
                                                f"expected\\{expected[filename]}"))


    @classmethod
    def tearDownClass(cls):
        cls.loop.run_until_complete(cls.client.close())

if __name__ == "__main__":
    unittest.main()