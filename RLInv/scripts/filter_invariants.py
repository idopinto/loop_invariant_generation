# def is_trivial_invariant(invariant_text: str) -> bool:
#     """
#     Check if an invariant is trivial or not learnable from source code.
    
#     Filters out invariants that:
#     - Are exactly "1" (true in C)
#     - Reference variables that don't exist in the source code (e.g., "!(cond == 0)" 
#       when cond is only a function parameter, not a program variable)
#     """
#     # Normalize whitespace for comparison
#     normalized = invariant_text.strip()
    
#     # Filter out trivial invariants
#     trivial_patterns = [
#         "1",                    # Always true
#         "!(cond == 0)",        # References cond which doesn't exist as program variable
#     ]
    
#     return normalized in trivial_patterns
