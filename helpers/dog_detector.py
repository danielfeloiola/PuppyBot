'''
________/\\\\\\\\\__/\\\________/\\\__/\\\\\\\\\\\\\\\__/\\\\\\\\\\\\\\\_
 _____/\\\////////__\/\\\_______\/\\\_\///////\\\/////__\/\\\///////////__
  ___/\\\/___________\/\\\_______\/\\\_______\/\\\_______\/\\\_____________
   __/\\\_____________\/\\\_______\/\\\_______\/\\\_______\/\\\\\\\\\\\_____
    _\/\\\_____________\/\\\_______\/\\\_______\/\\\_______\/\\\///////______
     _\//\\\____________\/\\\_______\/\\\_______\/\\\_______\/\\\_____________
      __\///\\\__________\//\\\______/\\\________\/\\\_______\/\\\_____________
       ____\////\\\\\\\\\__\///\\\\\\\\\/_________\/\\\_______\/\\\\\\\\\\\\\\\_
        _______\/////////_____\/////////___________\///________\///////////////_
'''
# Dog detector
# Uses Keras/TensorFlow to detect a dog in the image


# imports
#from sklearn.datasets import load_files
from keras.utils import np_utils
import numpy as np
#from keras.applications.resnet50 import ResNet50
from tensorflow.keras.applications.resnet50 import ResNet50
from keras.preprocessing import image
from tensorflow.keras.applications.resnet50 import preprocess_input, decode_predictions
from tqdm import tqdm
import cv2

# define ResNet50 model
ResNet50_model = ResNet50(weights='imagenet')


def path_to_tensor(img_path):
    # loads RGB image as PIL.Image.Image type
    img = image.load_img(img_path, target_size=(224, 224))
    # convert PIL.Image.Image type to 3D tensor with shape (224, 224, 3)
    x = image.img_to_array(img)
    # convert 3D tensor to 4D tensor with shape (1, 224, 224, 3) and return 4D tensor
    return np.expand_dims(x, axis=0)


def ResNet50_predict_labels(img_path):
    # returns prediction vector for image located at img_path
    img = preprocess_input(path_to_tensor(img_path))
    return np.argmax(ResNet50_model.predict(img))


def dog_detector(img_path):
    # We use these ideas to complete the `dog_detector` function below,
    # which returns `True` if a dog is detected in an image (and `False` if not).
    prediction = ResNet50_predict_labels(img_path)
    return ((prediction <= 268) & (prediction >= 151))
