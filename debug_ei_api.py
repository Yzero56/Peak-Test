import requests
import json

EI_API_KEY = "ei_0729edcb95ba9aca57c4913fc8d37cf41eadde68c6e4c009"
PROJECT_ID = "1084517"
BASE_URL = "https://studio.edgeimpulse.com/v1/api"

headers = {
    "x-api-key": EI_API_KEY,
    "Accept": "application/json"
}

print("=== Edge Impulse API Debug ===\n")

# Test 1: Check project access
print("Test 1: Project access check")
response = requests.get(f"{BASE_URL}/projects/{PROJECT_ID}", headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.text[:200] if response.text else 'Empty'}\n")

# Test 2: List all projects
print("Test 2: List all projects")
response = requests.get(f"{BASE_URL}/projects", headers=headers)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    projects = response.json().get("projects", [])
    print(f"Found {len(projects)} projects")
    for p in projects[:3]:
        print(f"  - {p['name']} (ID: {p.get('id', 'N/A')})")
print()

# Test 3: Check data endpoint (try different URLs)
print("Test 3: Data endpoint test")
endpoints = [
    f"{BASE_URL}/projects/{PROJECT_ID}/data",
    f"{BASE_URL}/projects/{PROJECT_ID}/raw-data",
    f"{BASE_URL}/data/{PROJECT_ID}"
]

for endpoint in endpoints:
    try:
        # Try GET request (should return list of existing data)
        response = requests.get(endpoint, headers=headers, timeout=5)
        print(f"GET {endpoint}: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                print(f"  Keys: {list(data.keys())}")
                if "data" in data:
                    print(f"  Data items: {len(data['data'])}")
    except Exception as e:
        print(f"GET {endpoint}: Error - {str(e)[:100]}")

print("\n=== Debug Complete ===")
