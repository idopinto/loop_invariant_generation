import json
from pathlib import Path
import logging
from tqdm import tqdm
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
root_dir = Path(__file__).parent.parent
logger = logging.getLogger(__name__)

def filter_training_data(json_file_path: str, output_file_path: str):
    logger.info(f"Filtering training data from {json_file_path} to {output_file_path}")
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    filtered_data = []
    for entry in tqdm(data, desc="Filtering training data"):
        if entry.get('result') in {"UNKNOWN", "ERROR", "TIMEOUT"}:
            continue
        if not entry.get('invariants'):
            continue
        filtered_data.append(entry)
    logger.info(f"Filtered {len(data)} entries to {len(filtered_data)} entries. {len(data) - len(filtered_data)} entries removed.")
    with open(output_file_path, 'w') as f:
        json.dump(filtered_data, f)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Filter training data")
    parser.add_argument("--uautomizer-version", type=str, default="25", help="UAutomizer version (default: 25)")
    args = parser.parse_args()
    json_file_path = root_dir / "dataset" / "training" / f"uautomizer{args.uautomizer_version}_training_k1_rewrite_" / f"uautomizer{args.uautomizer_version}_training_k1_rewrite_.json"
    output_file_path = root_dir / "dataset" / "training" / f"uautomizer{args.uautomizer_version}_training_k1_rewrite_filtered2.json"
    filter_training_data(json_file_path=json_file_path, output_file_path=output_file_path)