import requests
import os
import time

EI_API_KEY = "ei_0729edcb95ba9aca57c4913fc8d37cf41eadde68c6e4c009"
PROJECT_ID = "1084517"
BASE_URL = "https://studio.edgeimpulse.com"

headers = {
    "x-api-key": EI_API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def upload_sample(file_path, label):
    try:
        with open(file_path, "rb") as f:
            # Create multipart form data
            files = {
                "data": (os.path.basename(file_path), f, "image/jpeg")
            }
            data = {
                "label": label,
                "category": "training",
                "protected": False,
                "discrete": False,
                "intervalMs": 1
            }
            
            response = requests.post(
                f"{BASE_URL}/api/training/data/{PROJECT_ID}",
                headers={"x-api-key": EI_API_KEY, "Accept": "application/json"},
                files=files,
                data=data
            )
            
            if response.status_code in [201, 200]:
                return True, None
            else:
                return False, f"{response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)

def main():
    print("=== Edge Impulse Dataset Uploader FINAL ===\n")
    print(f"Project ID: {PROJECT_ID}")
    print(f"Dataset: xiao_dataset\n")
    
    dataset_dir = "xiao_dataset"
    if not os.path.exists(dataset_dir):
        print(f"Dataset directory not found: {dataset_dir}")
        return
    
    files = sorted([f for f in os.listdir(dataset_dir) if f.endswith(".jpg")])
    print(f"Found {len(files)} files to upload\n")
    
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
            time.sleep(0.2)
    
    print(f"\n=== Upload Complete ===")
    print(f"Success: {success_count}/{len(files)}")
    if success_count > 0:
        print(f"\nNext steps:")
        print(f"1. Go to: https://studio.edgeimpulse.com/studio/{PROJECT_ID}")
        print(f"2. Create impulse with Image processing block")
        print(f"3. Add MobileNetV2 learning block")
        print(f"4. Train model")
        print(f"5. Download Arduino library")

if __name__ == "__main__":
    main()
