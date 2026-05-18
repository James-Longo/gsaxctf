import re
TEAM_MAPPING = {
    "Greater Houlton": "Houlton High School",
    "Houlton": "Houlton High School",
}
def normalize_team_name(name, all_teams=None):
    if not name: return "Unknown"
    name = name.strip()
    name = re.sub(r'^\d+[-\s]*', '', name)
    if "unattach" in name.lower() or name.lower() == "un":
        return "Unattached"
    name = re.sub(r'\s+\d{4}$', '', name)
    if re.match(r'^:?\d+[:.]\d+', name) or re.match(r'^\d+-\d+\.?\d*$', name):
        return "Unknown"
    name = re.sub(r'^(M|JR|W|FR|SO|SR)\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+J[\d\.\-\':]+.*', '', name)
    name = name.strip()
    if "," in name:
        name = name.split(',')[0].strip()

    ms_tokens = ["ms", "middle", "junior high", "jh", "elementary", "elem", "elementa", "primary", "interme"]
    is_ms_token = any(f" {t}" in name.lower() or name.lower().endswith(f" {t}") or name.lower().endswith(t) for t in ms_tokens)
    
    for key, val in TEAM_MAPPING.items():
        if is_ms_token:
            if name.lower() == key.lower():
                return val
            continue
        if name.lower().startswith(key.lower()):
            return val

    return name

variants = [
    "HoultonGHCAHodgdon",
    "HoultonGHCA",
    "Houlton High School",
    "HoultonHodgdonGHCA",
    "HoultonHodg",
    "Houlton",
    "HoultonME",
    "Houlton MS"
]

for v in variants:
    print(f"{v}: {normalize_team_name(v)}")
