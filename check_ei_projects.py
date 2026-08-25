import requests
import os

EI_API_KEY = "ei_0729edcb95ba9aca57c4913fc8d37cf41eadde68c6e4c009"
BASE_URL = "https://studio.edgeimpulse.com/v1/api"

headers = {
    "x-api-key": EI_API_KEY,
    "Accept": "application/json"
}

def list_projects():
    response = requests.get(f"{BASE_URL}/projects", headers=headers)
    if response.status_code != 200:
        print(f"Error listing projects: {response.status_code}")
        print(response.text)
        return []
    
    projects = response.json().get("projects", [])
    print(f"=== Your Edge Impulse Projects ===\n")
    
    if not projects:
        print("No projects found. You need to create a project at:")
        print("https://studio.edgeimpulse.com/")
        return []
    
    for i, project in enumerate(projects, 1):
        print(f"{i}. {project['name']}")
        print(f"   ID: {project['id']}")
        print(f"   Created: {project.get('created_at', 'N/A')}")
        print()
    
    return projects

def main():
    projects = list_projects()
    
    if projects:
        print("\nChoose a project to upload your dataset:")
        print("Note down the project ID and I'll help you upload the data.")

if __name__ == "__main__":
    main()
