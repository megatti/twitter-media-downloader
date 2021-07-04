# twitter_media_dl
A Python script for downloading media (images, gifs, and videos) from a Twitter user's Likes or Timeline.

## Installation

To install this application, clone the repository onto your machine. `twitter_media_dl.py` is the main file which should can be run from the command line with arguments to control the downloader.

The required libraries for the script can be installed with `pip install -r requirements.txt`.

The script uses a `.env` file to define the credentials for the downloader. To get credentials, a Twitter Developer App is needed. To create one, go to https://developer.twitter.com/en. Create an account and then a new Standalone App at https://developer.twitter.com/en/portal/projects-and-apps.

Create a file named `.env` in the twitter_media_dl folder. In this file, define the following keys and values as shown:

```
CONSUMER_KEY=<App Consumer Key>
CONSUMER_SECRET=<App Consumer Secret>
ACCESS_TOKEN=<App Access Token>
ACCESS_SECRET=<App Access Secret>
```

A `TWITTER_ID` key and value can also be defined in this .env file. This user ID will be used as the default if no ID is specified from the command line when running the file. The script should now be ready to run.
## Usage

Run the `twitter_media_dl.py` file from the command line. The following format can be used:

```
python twitter_media_dl.py [--user USER_ID] [--source {likes|timeline|both}]
```

A Twitter user ID must be specified either in the .env file or at the command line. The source argument defines whether the client will download media from the user's Likes or the user's Timeline (including the user's Retweets). If no source argument (or "both") is provided, then both the user's Likes *and* Timeline will be combed for media.

# Output

The downloaded media will be placed in a `media` directory, which is by default a sibling to the `twitter_media_dl` directory. Inside this directory will be a directory each for Likes and Timeline media. As the script downloads media, the URLs of each piece of media it downloads will be tracked, to ensure that it doesn't download the same piece of media multiple times. At the end of the process, these URLs will be saved into text files in this directory, named `{source}_urls-{current date}.txt`. Old versions of these files will be moved into backup directories for safety.

Inside the likes and timeline directories will be a directory for each original uploader of media, as well as an `__all__` folder containing all pieces of media downloaded. Each piece of media is saved with a title format of `{gif|img|video}{date}_{uploader}_{tweet_id}.{mp4|png|jpg}`.

## License

GNU GENERAL PUBLIC LICENSE Version 3

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)