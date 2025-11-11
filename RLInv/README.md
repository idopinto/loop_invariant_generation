# loop_invariant_generation

## Java Version Requirements

Different UAutomizer versions require different Java versions:
- **UAutomizer23** (0.2.2-dev-2329fc7): Java 11
- **UAutomizer24** (0.2.4-dev-0e0057c): Java 11
- **UAutomizer25** (0.3.0-dev-d790fec): Java 21
- **UAutomizer26** (0.3.0-dev-9c83a1c48e): Java 21

Java installations are located at `/cs/labs/guykatz/idopinto12/java/`:
- Java 11: `jdk-11.0.23`
- Java 21: `jdk-21.0.1`

The `Ultimate.py` scripts automatically detect and use the correct Java version based on the UAutomizer directory. No manual switching is required.

### Bug Fixes

Fixed syntax warnings in `Ultimate.py` by converting regex patterns to raw strings (using `r"..."` instead of `"..."`) in UAutomizer23 and UAutomizer24.