'''
 _______  __   __  _______  _______  __   __  _______  _______  _______
|       ||  | |  ||       ||       ||  | |  ||  _    ||       ||       |
|    _  ||  | |  ||    _  ||    _  ||  |_|  || |_|   ||   _   ||_     _|
|   |_| ||  |_|  ||   |_| ||   |_| ||       ||       ||  | |  |  |   |
|    ___||       ||    ___||    ___||_     _||  _   | |  |_|  |  |   |
|   |    |       ||   |    |   |      |   |  | |_|   ||       |  |   |
|___|    |_______||___|    |___|      |___|  |_______||_______|  |___|

'''
########################################################################
# A BOT THAT RETWETS IMAGES OF PUPPIES                                 #
# version: idk, probably a million?                                    #
# follow me on twitter woof                                            #
# made by me                                                           #
########################################################################

# import libraries needed
import os
import json
import tweepy

from time import sleep
from ssl import SSLError
from requests.exceptions import Timeout, ConnectionError
from urllib3.exceptions import ReadTimeoutError
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

# make a database
engine = create_engine(os.getenv("DATABASE_URI"))
db = scoped_session(sessionmaker(bind=engine))

# create an OAuthHandler
if not os.getenv("CONSUMER_KEY"):
    raise RuntimeError("CONSUMER_KEY is not set")

# create twitter api
consumer_key = os.getenv("CONSUMER_KEY")
consumer_secret = os.getenv("CONSUMER_SECRET")
access_token = os.getenv("ACCESS_TOKEN")
access_token_secret = os.getenv("ACCESS_TOKEN_SECRET")

auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_token_secret)
api = tweepy.API(auth)


def check_safety(status):
#check if a tweet is violent or contains porn

    # get tweet out of json package
    tweet_json = json.dumps(status._json)
    tweet = json.loads(tweet_json)

    # MAKE SAFETY LIST
    safe_list_db = db.execute("SELECT * FROM slist").fetchall()

    # make a list with bad words
    slist = []
    for item in safe_list_db:
        slist.append(item[0])

    # Make sure it's not a RT
    if (not status.retweeted) and ('RT @' not in status.text) and ('media' in status.entities):

        # check for porn or kpop on the tweet
        if not any(word in status.text.lower() for word in slist):

            # check for porn on the user description
            if tweet['user']['description'] != None:

                if not any(word in tweet['user']['description'].lower() for word in slist):

                    # check user name
                    if not any(word in tweet['user']['name'].lower() for word in slist):

                        if len(status.text) > 6:

                            for char in tweet['user']['description']:
                                if ord(char) > 256:
                                    return False

                            for char in tweet['user']['name']:
                                if ord(char) > 256:
                                    return False

                            if tweet['possibly_sensitive'] == False:

                                # say its safe
                                print('Got a safe tweet')
                                print(status.text)
                                return True

                            # SHOW REMOVED TWEETS
                            # if the tweet has kpop or porn on the username:
                            else:
                                print('FOUND A UNSAFE ONE!!! - possibly_sensitive')
                                print(status.text)
                                print(tweet['user']['name'])
                                print(tweet['user']['description'])
                                return False

                        else:
                            print("status is too short")
                            print(status.text)
                    # SHOW REMOVED TWEETS
                    # if the tweet has kpop or porn on the username:
                    else:
                        print('FOUND A UNSAFE ONE!!! - NAME')
                        print(status.text)
                        print(tweet['user']['name'])
                        print(tweet['user']['description'])
                        return False

                # if the tweet has kpop or porn on the user description:
                else:
                    print('FOUND A UNSAFE ONE!!! - DESCRIPTION')
                    print(status.text)
                    print(tweet['user']['name'])
                    print(tweet['user']['description'])
                    return False


            # if the user profile has no description:
            else:
                print('FOUND A UNSAFE ONE!!! - EMPTY DESCRIPTION')
                print(status.text)
                print(tweet['user']['name'])
                print(tweet['user']['description'])
                return False

        # if the tweet has kpop or porn on the text:
        else:
            print('FOUND A UNSAFE ONE!!! - TEXT')
            print(status.text)
            print(tweet['user']['name'])
            print(tweet['user']['description'])
            return False


# Creates a class for the listener
class MyStreamListener(tweepy.StreamListener):

    # if a new tweet gets found out...
    def on_status(self, status):

        # check if tweet is safe
        check = check_safety(status)

        # if its indeed safe
        if check == True:

            # tries to retweet the tweet - or just gives up
            try:
                print('about to retweet')
                api.retweet(status.id)
                print('RETWEETED!!!')
                sleep(1800) # for tweeting every 50 mins
                print('done sleeping!')
            except:
                print('passing...')
                pass


    # if there is any error
    def on_error(self, status_code):

        # Being rate limited for making too many requests.
        if status_code == 420:
            print('ERROR 420: Too many requests')
            sleep(300)
            print('Back to work!')
            return True

        # Cannot retweet the same Tweet more than once
        if status_code == 327:
            print('ERROR 327: You have already retweeted this Tweet')
            return True


# Start a stream listener to look for tweets with puppies
myStreamListener = MyStreamListener()
stream = tweepy.Stream(auth, myStreamListener)

while not stream.running:
    try:
        # start stream
        print("Started listening to stream...")
        stream.filter(track=['puppy'])

    except (Timeout, SSLError, ReadTimeoutError, ConnectionError) as e:
        # if there is a connection error
        print("Network error. Keep calm and carry on.", str(e))
        sleep(300)

    except Exception as e:
        # if there is another kind of error
        print(e)

    finally:
        # wars about the crash
        print("Stream has crashed. System will restart twitter stream soon!")

# if error escapes jail...
print("This error was so bad I have no idea what it was!")
