import tempfile
import unittest
from pathlib import Path

import numpy as np

from container_registry import ContainerDatabase


class ContainerDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = ContainerDatabase(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def test_register_match_and_register_another(self):
        first = self.database.recognize_or_register(np.array([1.0, 0.0]), 0.8, "김치")
        same = self.database.recognize_or_register(np.array([0.99, 0.01]), 0.8)
        other = self.database.recognize_or_register(np.array([0.0, 1.0]), 0.8, "물")

        self.assertEqual(first["container_id"], "Container_001")
        self.assertEqual(same["status"], "matched")
        self.assertEqual(same["container_id"], "Container_001")
        self.assertEqual(same["content"], "김치")
        self.assertEqual(other["container_id"], "Container_002")
        self.assertEqual(len(self.database.list_containers()), 2)
        feature_count = self.database.connection.execute(
            "SELECT COUNT(*) FROM container_features WHERE container_id = 'Container_001'"
        ).fetchone()[0]
        self.assertEqual(feature_count, 2)

    def test_update_content(self):
        self.database.recognize_or_register(np.array([1.0, 0.0]))
        self.assertTrue(self.database.update_content("Container_001", "반찬"))
        self.assertEqual(self.database.list_containers()[0]["content"], "반찬")


if __name__ == "__main__":
    unittest.main()
