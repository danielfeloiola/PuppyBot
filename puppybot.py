'''
 ______   __  __     ______   ______   __  __     ______     ______     ______
/\  == \ /\ \/\ \   /\  == \ /\  == \ /\ \_\ \   /\  == \   /\  __ \   /\__  _\
\ \  _-/ \ \ \_\ \  \ \  _-/ \ \  _-/ \ \____ \  \ \  __<   \ \ \/\ \  \/_/\ \/
 \ \_\    \ \_____\  \ \_\    \ \_\    \/\_____\  \ \_____\  \ \_____\    \ \_\
  \/_/     \/_____/   \/_/     \/_/     \/_____/   \/_____/   \/_____/     \/_/

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

# stuff
from time import sleep
from ssl import SSLError
from requests.exceptions import Timeout, ConnectionError
from urllib3.exceptions import ReadTimeoutError

# img stuff
from io import BytesIO
from PIL import Image
from PIL import ImageFile

# db stuff
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

# requests
import requests

# TF detector
from dog_app import dog_detector

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

# api setup
auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_token_secret)
api = tweepy.API(auth)


def check_safety(status):
    '''
    check if a tweet is adequate
    Looks for bad words on username, text and description
    checks if threre is a image on the tweet
    '''

    # get tweet out of json package
    tweet_json = json.dumps(status._json)
    tweet = json.loads(tweet_json)

    # get words from db
    safe_list_db = db.execute("SELECT * FROM slist").fetchall()

    # make a list with bad words
    slist = []

    # add the words from the db to the list
    for item in safe_list_db:
        slist.append(item[0])

    # start checking if its a safe tweet
    # returns false if the test fails

    # Make sure it's not a RT
    if status.retweeted:
        print('------------------------------------------')
        print("RT!")
        print('------------------------------------------')
        return False
    if 'RT @' in status.text:
        print('------------------------------------------')
        print("RT!")
        print('------------------------------------------')
        return False

    # check if there is indeed a picture in it
    if ('media' in status.entities):

        # looking for bad words

        # check for p*rn or kpop on the tweet
        if any(word in status.text.lower() for word in slist):
            print('')
            print('------------------------------------------')
            print('')
            print('unsafe - text')
            print(status.text)
            #print(tweet['user']['name'])
            #print(tweet['user']['description'])
            print('')
            print('------------------------------------------')
            print('')
            return False


        # check user name
        if any(word in tweet['user']['name'].lower() for word in slist):
            print('')
            print('------------------------------------------')
            print('')
            print('unsafe - name')
            #print(status.text)
            print(tweet['user']['name'])
            #print(tweet['user']['description'])
            print('')
            print('------------------------------------------')
            print('')
            return False

        #if any(word in tweet['user']['description'].lower() for word in slist):
        #print('')
        #print('------------------------------------------')
        #print('')
        #    print('unsafe -> description')
        #    #print(status.text)
        #    #print(tweet['user']['name'])
        #    print(tweet['user']['description'])
        #    print('')
        #    print('------------------------------------------')
        #    print('')
        #    return False

        # if the tweet is not marked as sensitive:
        if tweet['possibly_sensitive'] == False:
            print('not sensitive')

            return True

    else:

        print('------------------------------------------')
        print('')
        print("no image on the tweet")
        print('')
        print('------------------------------------------')

        return False


def check_dog(status):
    '''
    Checks if there is a dog on the image using TensorFlow
    '''

    for image in status.entities['media']:

        url = image['media_url']
        print("URL ------>" + url)
        filename = 'temp.png'

        # send a get request to get the image
        request = requests.get(url, stream=True)
        if request.status_code == 200:

            # read data from downloaded bytes and returns a PIL.Image.Image object
            i = Image.open(BytesIO(request.content))

            # Saves the image under the given filename
            i.save(filename)

            # call the detector function
            dog = dog_detector("temp.png")

            # if a dog is detected return true
            # else return false
            if dog == True:
                # say its safe
                print('GOT A DOGGO!')
                print(status.text)
                return True
            else:
                return False

        # if the request for the image fails return false
        else:
            print("unable to download image")
            return False


# Creates a class for the listener
class MyStreamListener(tweepy.StreamListener):

    # if a new tweet gets found out...
    def on_status(self, status):

        # check if tweet is safe
        check = check_safety(status)

        # if its indeed safe
        if check == True:

            dog_on_image = check_dog(status)
            if dog_on_image == True:


                # tries to retweet the tweet - or just gives up
                try:
                    print('about to retweet')
                    api.retweet(status.id)
                    print('RETWEETED!!!')
                    sleep(3600) # for tweeting every 30 mins
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
        # warns about the crash
        print("Stream has crashed. System will restart twitter stream soon!")

# if error escapes jail...
print("This error was so bad I have no idea what it was!")
