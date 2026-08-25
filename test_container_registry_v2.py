import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from browser_container_recognition_v2 import RecognitionServiceV2
from container_registry_v2 import ContainerDatabaseV2, select_representative_vectors


class ContainerDatabaseV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = ContainerDatabaseV2(Path(self.temp.name) / "v2.db")

    def tearDown(self):
        self.db.close(); self.temp.cleanup()

    def test_gallery_register_and_recognize_without_adding_vector(self):
        result = self.db.register_gallery(
            [np.array([1., 0.]), np.array([.8, .2])],
            [np.array([1., 0.]), np.array([.9, .1])])
        self.assertEqual(result["container_id"], "Container_001")
        match = self.db.recognize(np.array([.99, .01]), np.array([.99, .01]), threshold=.8)
        self.assertEqual(match["status"], "matched")
        self.assertEqual(match["container_id"], "Container_001")
        self.assertEqual(self.db.list_containers()[0]["vector_count"], 2)

    def test_unknown_does_not_auto_register(self):
        self.db.register_gallery([np.array([1., 0.])], [np.array([1., 0.])])
        result = self.db.recognize(np.array([0., 1.]), np.array([0., 1.]), threshold=.8)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(self.db.list_containers()), 1)

    def test_different_color_is_rejected_even_when_shape_matches(self):
        self.db.register_gallery([np.array([1., 0.])], [np.array([1., 0.])])
        result = self.db.recognize(np.array([1., 0.]), np.array([0., 1.]), threshold=.6)
        self.assertEqual(result["status"], "unknown")

    def test_near_duplicate_selection(self):
        vectors = [np.array([1., 0.]), np.array([.9999, .0001]), np.array([0., 1.])]
        self.assertEqual(len(select_representative_vectors(vectors, .98, 15)), 2)

    def test_color_vector_accepts_pil_image(self):
        image = Image.fromarray(np.full((32, 32, 3), [20, 80, 220], dtype=np.uint8))
        vector = RecognitionServiceV2._color_vector(image)
        self.assertGreater(vector.size, 0)
        self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=5)

    def test_identical_crops_are_not_diverse(self):
        crops = [np.full((80, 100, 3), 100, dtype=np.uint8) for _ in range(20)]
        diverse, count = RecognitionServiceV2._diverse_enough(crops)
        self.assertFalse(diverse)
        self.assertEqual(count, 0)


if __name__ == "__main__": unittest.main()
