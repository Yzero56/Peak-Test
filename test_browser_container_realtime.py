import unittest

import browser_container_realtime as realtime


class FakeService:
    def recognize(self):
        raise ValueError("용기 없음")


class RealtimeAppTests(unittest.TestCase):
    def test_page_and_no_detection_response(self):
        client = realtime.create_app(FakeService()).test_client()
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("실시간 용기 자동 인식".encode(), page.data)
        response = client.post("/recognize-next")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "no_detection")


if __name__ == "__main__":
    unittest.main()
