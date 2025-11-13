from dotenv import load_dotenv
import os
import requests
import json
load_dotenv()
API_KEY = os.getenv('ALLOY_API_KEY')

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'x-api-version': '2025-09',
    'Content-Type': 'application/json',
}

# Get chat_postMessage action schema
print("=== Get Slack chat_postMessage Action Schema ===")
resp = requests.get(
    'https://production.runalloy.com/connectors/slack/actions/chat_postMessage',
    headers=headers
)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    action = data.get('action', {})
    print(f"\nAction ID: {action.get('id')}")
    print(f"Display Name: {action.get('displayName')}")
    print(f"HTTP Method: {action.get('httpMethod')}")
    print(f"Path: {action.get('path')}")

    print(f"\nParameters:")
    for param in action.get('parameters', []):
        print(f"  - {param.get('name')} ({param.get('in')})")
        print(f"    Description: {param.get('description', 'N/A')}")
        print(f"    Required: {param.get('required', False)}")
        if param.get('schema'):
            print(f"    Schema: {json.dumps(param.get('schema'), indent=6)}")
        print()
