import requests
import os
import time

EI_API_KEY = "ei_6c5580f38d3ce698b9e2c3bbe69a090562c70ec7c67a3ac3"
PROJECT_ID = "1084517"
BASE_URL = "https://studio.edgeimpulse.com"

headers = {
    "x-api-key": EI_API_KEY,
    "Accept": "application/json"
}

def check_project():
    response = requests.get(f"{BASE_URL}/api/projects", headers=headers)
    if response.status_code == 200:
        projects = response.json().get("projects", [])
        print(f"Found {len(projects)} projects:")
        for p in projects:
            print(f"  - {p['name']} (ID: {p.get('id', 'N/A')})")
        return True
    return False

def upload_sample(file_path, label):
    try:
        with open(file_path, "rb") as f:
            files = {
                "data": (os.path.basename(file_path), f, "image/jpeg")
            }
            data = {
                "label": label,
                "category": "training",
                "protected": False
            }
            
            response = requests.post(
                f"{BASE_URL}/api/training/data/{PROJECT_ID}",
                headers=headers,
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
    print("=== Edge Impulse Dataset Uploader V3 ===\n")
    print(f"Using API Key: {EI_API_KEY[:20]}...")
    print(f"Project ID: {PROJECT_ID}\n")
    
    if not check_project():
        print("Failed to check projects")
        return
    
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

if __name__ == "__main__":
    main()
