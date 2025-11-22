def is_trivial_invariant(invariant_text: str) -> bool:
    """
    Check if an invariant is trivial or not learnable from source code.
    
    Filters out invariants that:
    - Are exactly "1" (true in C)
    - Reference variables that don't exist in the source code (e.g., "!(cond == 0)" 
      when cond is only a function parameter, not a program variable)
    """
    # Normalize whitespace for comparison
    normalized = invariant_text.strip()
    
    # Filter out trivial invariants
    trivial_patterns = [
        "1",                    # Always true
        "!(cond == 0)",        # References cond which doesn't exist as program variable
    ]
    
    return normalized in trivial_patterns



    # INSERT_YOUR_CODE
import json

def filter_invariants_in_file(input_path: str, output_path: str):
    """
    Load the dataset JSON, remove trivial invariants using is_trivial_invariant,
    and re-save the filtered JSON.
    """
    with open(input_path, 'r') as f:
        data = json.load(f)

    filtered_data = []
    for entry in data:
        if "invariants" in entry and isinstance(entry["invariants"], list):
            filtered_invs = [
                inv for inv in entry["invariants"]
                if not is_trivial_invariant(inv.get("invariant", ""))
            ]
            entry = dict(entry)  # shallow copy
            entry["invariants"] = filtered_invs
        filtered_data.append(entry)

    with open(output_path, 'w') as f:
        json.dump(filtered_data, f, indent=2)

# Example usage:
filter_invariants_in_file(
    "/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/dataset/training/example_train.json",
    "/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/dataset/training/example_train.filtered.json"
)
