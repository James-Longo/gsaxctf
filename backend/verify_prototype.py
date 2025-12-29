import json
import os

def verify():
    output_path = "prototype_output.json"
    if not os.path.exists(output_path):
        print("Output file not found.")
        return

    with open(output_path, "r", encoding="utf-16") as f:
        data = json.load(f)

    print(f"Total events parsed: {len(data)}")
    
    for event in data:
        print(f"\nEvent: {event['event']} ({event['gender']})")
        print(f"  Relay: {event.get('is_relay', False)}")
        print(f"  Results found: {len(event['results'])}")
        
        # Show first 3 results
        for res in event['results'][:3]:
            if event.get('is_relay'):
                print(f"    - {res['school']}: {res['result']} (Athletes: {', '.join(res['athletes'])})")
            else:
                print(f"    - {res['athlete']} ({res['school']}): {res['result']}")

if __name__ == "__main__":
    verify()
