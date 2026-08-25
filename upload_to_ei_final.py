import requests
import os
import time

EI_API_KEY = "ei_6c5580f38d3ce698b9e2c3bbe69a090562c70ec7c67a3ac3"
BASE_URL = "https://studio.edgeimpulse.com"

headers = {
    "x-api-key": EI_API_KEY,
    "Accept": "application/json"
}

print("=== Step 1: Check API Access ===")
response = requests.get(f"{BASE_URL}/api/projects", headers=headers)
if response.status_code == 200:
    projects = response.json().get("projects", [])
    if projects:
        project = projects[0]
        project_id = project.get('id')
        project_name = project.get('name')
        print(f"OK Found project: {project_name} (ID: {project_id})")
    else:
        print("FAIL No projects found")
        exit(1)
else:
    print(f"FAIL API Access Failed: {response.status_code}")
    print(response.text[:200])
    exit(1)

print(f"\n=== Step 2: Upload Dataset ===")
dataset_dir = "xiao_dataset"
if not os.path.exists(dataset_dir):
    print(f"FAIL Dataset directory not found: {dataset_dir}")
    exit(1)

files = sorted([f for f in os.listdir(dataset_dir) if f.endswith(".jpg")])
print(f"Found {len(files)} files\n")

success_count = 0
for i, filename in enumerate(files, 1):
    file_path = os.path.join(dataset_dir, filename)
    parts = filename.replace(".jpg", "").split(".")
    label = parts[0]
    
    try:
        with open(file_path, "rb") as f:
            files_data = {"data": (os.path.basename(file_path), f, "image/jpeg")}
            data = {"label": label, "category": "training", "protected": False}
            
            response = requests.post(
                f"{BASE_URL}/api/training/data/{project_id}",
                headers=headers,
                files=files_data,
                data=data
            )
            
            if response.status_code in [201, 200]:
                success_count += 1
                print(f"[{i}/{len(files)}] OK {filename}")
            else:
                print(f"[{i}/{len(files)}] FAIL {filename} - {response.status_code}")
    except Exception as e:
        print(f"[{i}/{len(files)}] FAIL {filename} - {str(e)[:50]}")
    
    if i < len(files):
        time.sleep(0.2)

print(f"\n=== Upload Complete ===")
print(f"Success: {success_count}/{len(files)}")
print(f"Project: https://studio.edgeimpulse.com/studio/{project_id}")

if success_count == len(files):
    print(f"\nOK All files uploaded successfully!")
    print(f"Next: Go to project and create impulse")
