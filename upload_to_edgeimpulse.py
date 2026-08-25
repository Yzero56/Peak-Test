import requests
import os
import time

EI_API_KEY = "ei_0729edcb95ba9aca57c4913fc8d37cf41eadde68c6e4c009"
PROJECT_ID = "1084517"
BASE_URL = "https://studio.edgeimpulse.com/v1/api"

headers = {
    "x-api-key": EI_API_KEY,
    "Accept": "application/json"
}

def upload_sample(file_path, label):
    try:
        with open(file_path, "rb") as f:
            files = {
                "data": (os.path.basename(file_path), f, "image/jpeg")
            }
            data = {
                "label": label,
                "protected": False
            }
            
            response = requests.post(
                f"{BASE_URL}/projects/{PROJECT_ID}/data",
                headers=headers,
                files=files,
                data=data
            )
            
            if response.status_code == 201:
                return True, None
            else:
                return False, response.text
    except Exception as e:
        return False, str(e)

def main():
    print("=== Edge Impulse Dataset Uploader ===")
    print(f"Project ID: {PROJECT_ID}")
    
    dataset_dir = "dataset"
    if not os.path.exists(dataset_dir):
        print(f"Dataset directory not found: {dataset_dir}")
        return
    
    files = sorted([f for f in os.listdir(dataset_dir) if f.endswith(".jpg")])
    print(f"Found {len(files)} files to upload")
    
    success_count = 0
    for i, filename in enumerate(files, 1):
        file_path = os.path.join(dataset_dir, filename)
        parts = filename.replace(".jpg", "").split(".")
        label = parts[0]
        
        success, error = upload_sample(file_path, label)
        if success:
            success_count += 1
            print(f"[{i}/{len(files)}] OK: {filename} (label: {label})")
        else:
            print(f"[{i}/{len(files)}] FAIL: {filename} - {error}")
        
        if i < len(files):
            time.sleep(0.15)
    
    print(f"\n=== Upload Complete ===")
    print(f"Success: {success_count}/{len(files)}")
    print(f"Project: https://studio.edgeimpulse.com/studio/{PROJECT_ID}")

if __name__ == "__main__":
    main()
