import requests
import os
import time

EI_API_KEY = "ei_7a4c7d3bec97258eb23c7793238e714ebf52e482cc4b20a6"
BASE_URL = "https://studio.edgeimpulse.com"

headers = {
    "x-api-key": EI_API_KEY,
    "Accept": "application/json"
}

print("=== Edge Impulse Workflow ===\n")

# Step 1: Check projects
print("Step 1: Check projects")
response = requests.get(f"{BASE_URL}/api/projects", headers=headers)
if response.status_code != 200:
    print(f"FAIL API access: {response.status_code}")
    exit(1)

projects = response.json().get("projects", [])
if not projects:
    print("FAIL No projects found")
    exit(1)

project = projects[0]
project_id = project.get('id')
project_name = project.get('name')
print(f"OK Project: {project_name} (ID: {project_id})\n")

# Step 2: Upload dataset
print("Step 2: Upload dataset")
dataset_dir = "xiao_dataset"
if not os.path.exists(dataset_dir):
    print(f"FAIL Dataset not found: {dataset_dir}")
    exit(1)

files = sorted([f for f in os.listdir(dataset_dir) if f.endswith(".jpg")])
print(f"Found {len(files)} files\n")

success = 0
for i, filename in enumerate(files, 1):
    file_path = os.path.join(dataset_dir, filename)
    label = filename.replace(".jpg", "").split(".")[0]
    
    try:
        with open(file_path, "rb") as f:
            files_data = {"data": (filename, f, "image/jpeg")}
            data = {"label": label, "category": "training", "protected": False}
            
            response = requests.post(
                f"{BASE_URL}/api/training/data/{project_id}",
                headers=headers,
                files=files_data,
                data=data
            )
            
            if response.status_code in [201, 200]:
                success += 1
                print(f"[{i}/{len(files)}] OK {filename}")
            else:
                print(f"[{i}/{len(files)}] FAIL {filename} - {response.status_code}")
    except Exception as e:
        print(f"[{i}/{len(files)}] FAIL {filename} - {str(e)[:30]}")
    
    time.sleep(0.2)

print(f"\n=== Results ===")
print(f"Uploaded: {success}/{len(files)}")
print(f"Project: https://studio.edgeimpulse.com/studio/{project_id}")
print(f"\nNext steps:")
print(f"1. Open project link")
print(f"2. Create impulse (Image + MobileNetV2)")
print(f"3. Train model")
print(f"4. Download Arduino library")
