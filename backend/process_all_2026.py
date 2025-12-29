import os
import json
import traceback
# Assuming prototype_parser is in the same directory (backend/)
from prototype_parser import Sub5ColumnParser

INPUT_DIR = os.path.join(os.path.dirname(__file__), "data/sub5_archive/2026")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data/parsed_results/2026")

def process_all():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".htm") or f.lower().endswith(".html")]
    
    print(f"Found {len(files)} files to process in {INPUT_DIR}")
    
    files_processed = 0
    total_events = 0
    
    for filename in files:
        input_path = os.path.join(INPUT_DIR, filename)
        output_filename = os.path.splitext(filename)[0] + ".json"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        print(f"Processing {filename}...")
        try:
            parser = Sub5ColumnParser(input_path)
            events = parser.parse()
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(events, f, indent=4, ensure_ascii=False)
                
            print(f"  -> Saved {len(events)} events to {output_filename}")
            files_processed += 1
            total_events += len(events)
        except Exception as e:
            print(f"  -> FAILED processing {filename}: {e}")
            traceback.print_exc()
            
    print(f"\nProcessing Complete.")
    print(f"Total Files Processed: {files_processed}/{len(files)}")
    print(f"Total Events Extracted: {total_events}")

if __name__ == "__main__":
    process_all()
