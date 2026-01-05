import json

with open('ui/public/data.json', 'r') as f:
    data = json.load(f)

print(f"Total results: {len(data)}")
bangor_christian = [r for r in data if 'Bangor Christian' in r.get('team', '')]
print(f"Bangor Christian results: {len(bangor_christian)}")
if bangor_christian:
    print(f"Sample team name: {bangor_christian[0]['team']}")

mci_central = [r for r in data if 'Maine Central' in r.get('team', '') and 'Central' in r.get('team', '')]
print(f"Maine Central results: {len(mci_central)}")
if mci_central:
    print(f"Sample team name: {mci_central[0]['team']}")
