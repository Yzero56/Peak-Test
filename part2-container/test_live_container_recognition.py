import unittest
from unittest.mock import patch

import cv2
import numpy as np

from live_container_recognition import fetch_jpg, make_jpg_url


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


class LiveRecognitionTests(unittest.TestCase):
    def test_camera_address_conversion(self):
        self.assertEqual(make_jpg_url("192.168.4.1"), "http://192.168.4.1/jpg")
        self.assertEqual(make_jpg_url("xiao.local/"), "http://xiao.local/jpg")
        self.assertEqual(make_jpg_url("http://xiao.local/stream"), "http://xiao.local/jpg")

    def test_fetch_jpg_decodes_camera_image(self):
        source = np.full((24, 32, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", source)
        self.assertTrue(ok)
        with patch("urllib.request.urlopen", return_value=FakeResponse(encoded.tobytes())):
            frame = fetch_jpg("http://camera/jpg")
        self.assertEqual(frame.shape, (24, 32, 3))


if __name__ == "__main__":
    unittest.main()
