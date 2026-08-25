import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/run_vlm_image_test.py <image-path>")

    image_path = Path(sys.argv[1])
    if not image_path.is_file():
        raise SystemExit(f"image not found: {image_path}")

    with TestClient(app) as client:
        with image_path.open("rb") as image_file:
            upload = client.post(
                "/api/v1/food-images",
                files={"file": (image_path.name, image_file, "image/jpeg")},
            )
        upload.raise_for_status()
        image_id = upload.json()["id"]
        print(f"image upload: {upload.status_code}")

        created = client.post("/api/v1/analysis-jobs", json={"image_id": image_id})
        created.raise_for_status()
        job_id = created.json()["job_id"]
        print(f"analysis job: {created.status_code} ({job_id})")

        result = client.get(f"/api/v1/analysis-jobs/{job_id}")
        result.raise_for_status()
        job = result.json()
        print(f"analysis status: {job['status']}")
        print(f"analysis result: {job.get('result')}")

        if job["status"] != "succeeded":
            raise SystemExit(f"analysis failed: {job.get('error_code')}")

        applied = client.post(f"/api/v1/analysis-jobs/{job_id}/apply")
        applied.raise_for_status()
        item = applied.json()
        print(f"food item applied: {applied.status_code}")
        print(f"food name: {item['display_name']}")
        print(f"expires at: {item['expires_at']}")
        print(f"date source: {item['date_source']}")


if __name__ == "__main__":
    main()
