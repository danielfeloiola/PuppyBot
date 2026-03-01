# Dog detector
# Uses TensorFlow/Keras to detect a dog in the image

import numpy as np
from tensorflow.keras.applications.resnet50 import ResNet50, preprocess_input  # type: ignore[import]
from tensorflow.keras.utils import load_img, img_to_array  # type: ignore[import]

# Load ResNet50 pre-trained on ImageNet at import time
_model = ResNet50(weights='imagenet')


def dog_detector(img_path: str) -> bool:
    """Return True if a dog breed is detected in the image at img_path."""
    img = load_img(img_path, target_size=(224, 224))
    x = preprocess_input(np.expand_dims(img_to_array(img), axis=0))
    prediction = int(np.argmax(_model(x, training=False)))
    # ImageNet classes 151–268 correspond to dog breeds
    return 151 <= prediction <= 268
