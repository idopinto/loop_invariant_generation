# UAutomizer Timing Determinism Guide

This guide explains how to make UAutomizer timing as deterministic as possible for benchmarking and evaluation, following SV-COMP reproducibility standards.

## Why Determinism Matters

Timing determinism is crucial for:
- Reliable benchmarking
- Fair comparison between different configurations
- Reproducible experiments
- Identifying performance regressions
- SV-COMP compliance and reproducibility

## SV-COMP Reproducibility Standards

SV-COMP (Software Verification Competition) emphasizes reproducibility through:

1. **BenchExec Framework**: SV-COMP uses BenchExec to measure and control computing resources, ensuring consistent execution conditions
2. **Dedicated Unloaded Machines**: Each verification run executes on a dedicated, unloaded machine to ensure precise measurements
3. **Standardized Resource Limits**: 
   - CPU: 8 cores
   - Memory: 15 GB
   - Timeout: 15 minutes (900 seconds)
4. **Public Availability**: All tools, benchmarks, and execution scripts are publicly available
5. **Transparent Execution Environment**: Controlled execution environment with specified hardware and software configurations

**Key Principle**: SV-COMP runs each verification on a **dedicated, unloaded machine** to minimize timing variability from system load and resource contention.

### What BenchExec Does for Reproducibility

BenchExec (the benchmarking framework used by SV-COMP) automatically:
- **Isolates processes**: Runs each verification in a controlled environment
- **Controls resources**: Enforces CPU, memory, and time limits
- **Minimizes interference**: Uses system-level isolation to prevent other processes from affecting measurements
- **Measures accurately**: Uses precise timing mechanisms (typically wall-clock time)

**Important Note**: BenchExec likely relies on system-level settings (CPU frequency, etc.) being configured by administrators, but the framework itself doesn't automatically set CPU frequency scaling. However, SV-COMP's execution environment (dedicated machines) ensures these settings are consistent.

### What You Can Do to Match SV-COMP Standards

Since you may not have BenchExec or dedicated machines, you can approximate SV-COMP conditions by:

1. **Minimizing System Load**: Run when system is idle (closest to "dedicated unloaded machine")
2. **Setting CPU to Performance Mode**: Ensures consistent CPU frequency
3. **Using CPU Affinity**: Pin processes to specific cores (simulates resource isolation)
4. **Setting Process Priority**: Use `nice` to give highest priority
5. **Warming Cache**: Pre-load files to reduce I/O variability

## Determinism Factors

**Key Factors (in order of impact):**
1. **System-Level Settings** (CPU frequency, Turbo Boost, CPU affinity) - Highest Impact
2. **JVM Settings** (Garbage collector, memory allocation) - High Impact
3. **Z3 Random Seed** - Medium-High Impact (see Section 4)
4. **System Load** - High Impact
5. **File System I/O** - Medium Impact
6. **Python Hash Randomization** - Low Impact

### 1. **System-Level Settings** (Highest Impact)

#### CPU Frequency Scaling
CPU frequency scaling causes significant timing variations. Set CPU to fixed performance mode:

```bash
# Check current governor
cpupower frequency-info

# Set to performance mode (requires root)
sudo cpupower frequency-set -g performance

# Verify
cpupower frequency-info
```

#### Disable CPU Turbo Boost
Turbo boost can cause variable performance:

```bash
# For Intel CPUs
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo

# Verify
cat /sys/devices/system/cpu/intel_pstate/no_turbo  # Should be 1
```

#### CPU Affinity / Process Isolation
Pin processes to specific CPU cores to avoid migration:

```bash
# Run with CPU affinity (e.g., CPUs 0-3)
taskset -c 0-3 python tests/test_uautomizer_timing_determinism.py

# Or isolate CPUs at boot (add to kernel parameters)
isolcpus=0-3
```

#### System Load
Minimize system load during testing:
- Close unnecessary applications
- Stop background services
- Use `nice` to set process priority:
  ```bash
  nice -n -20 python tests/test_uautomizer_timing_determinism.py
  ```

### 2. **JVM Settings** (High Impact)

UAutomizer runs on Java, and JVM settings significantly affect timing. The current settings in `Ultimate.ini`:

```
-Xmx12G    # Maximum heap size
-Xms512M   # Initial heap size
```

**Recommended JVM flags for determinism:**

```ini
-Xmx15G
-Xms4m
-XX:+UseG1GC                    # G1 garbage collector (more predictable)
-XX:MaxGCPauseMillis=200        # Limit GC pause time
-XX:+DisableExplicitGC          # Disable explicit GC calls
-XX:+UseStringDeduplication     # Reduce string allocation variability
-XX:+UnlockExperimentalVMOptions
-XX:+UseTransparentHugePages    # More predictable memory allocation
-XX:NewRatio=1                  # Control heap generations
-Djava.security.egd=file:/dev/./urandom  # Faster RNG
```

**Note:** These would need to be added to `Ultimate.py`'s `create_ultimate_base_call()` function or passed via environment variables.

### 3. **Environment Variables**

The test script automatically sets these when `deterministic_mode=True`:

```bash
export PYTHONHASHSEED=0          # Disable Python hash randomization
export PYTHONUNBUFFERED=1        # Unbuffered output
export _JAVA_OPTIONS="-XX:+UseG1GC -XX:MaxGCPauseMillis=200 ..."
```

### 4. **UAutomizer Configuration**

#### SMT Solver Settings - Z3 Random Seed

Z3 uses randomization internally for tie-breaking in heuristics, which can cause timing variations. To make Z3 deterministic, you can set the `random_seed` parameter.

**Current Z3 Command:**
```
z3 SMTLIB2_COMPLIANT=true -memory:2024 -smt2 -in -t:4000
```

**With Random Seed (for determinism):**
```
z3 SMTLIB2_COMPLIANT=true -memory:2024 -smt2 -in -t:4000 smt.random_seed=42
```

**Note**: The format is `smt.random_seed=42` (without a dash prefix). This is a Z3 command-line parameter that sets the SMT option.

**Alternative (SMT-LIB format):**
You can also set it via SMT-LIB option in the generated SMT scripts (if UAutomizer supports injecting SMT-LIB commands):
```smt
(set-option :random-seed 42)
```

**How to Apply to All Config Files:**

You can use a script to add `smt.random_seed=42` to all Z3 commands in your config files:

```bash
# Navigate to config directory
cd /cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/tools/uautomizer/config

# Add random seed to all Z3 commands (backup first!)
for file in *.epf; do
    # Replace Z3 command lines that don't already have random_seed
    sed -i.bak 's|z3 SMTLIB2_COMPLIANT\\=true -memory\\:2024 -smt2 -in -t\\:4000|z3 SMTLIB2_COMPLIANT\\=true -memory\\:2024 -smt2 -in -t\\:4000 smt.random_seed\\=42|g' "$file"
    sed -i.bak 's|z3 SMTLIB2_COMPLIANT\\=true -memory\\:2024 -smt2 -in|z3 SMTLIB2_COMPLIANT\\=true -memory\\:2024 -smt2 -in smt.random_seed\\=42|g' "$file"
done
```

**Example modification for a single config file:**
In `svcomp-Reach-32bit-Automizer_Default.epf`, change:
```
Command for external solver=z3 SMTLIB2_COMPLIANT=true -memory:2024 -smt2 -in -t:4000
```

To:
```
Command for external solver=z3 SMTLIB2_COMPLIANT=true -memory:2024 -smt2 -in -t:4000 smt.random_seed=42
```

**Note**: Make sure to escape the backslashes properly in the `.epf` file format (they use `\` for escaping spaces and colons).

**Note**: Setting a fixed seed (e.g., 42) ensures Z3 produces identical behavior across runs, improving timing determinism.

#### CVC4 Randomization
CVC4 may also use randomization, but doesn't have a direct seed parameter like Z3. Using the same CVC4 version helps.

#### Config File Consistency
- Use the same config files for all runs
- Ensure consistent settings across runs
- Avoid config files that change between runs

### 5. **File System**

#### Use tmpfs for Temporary Files
Reduces I/O variability:

```bash
# Mount tmpfs
sudo mount -t tmpfs -o size=2G tmpfs /tmp/uautomizer

# Use it for reports
python tests/test_uautomizer_timing_determinism.py \
    --reports_dir /tmp/uautomizer/reports
```

#### File System Caching
Warm up file system cache before testing:

```bash
# Read files once to cache them
cat dataset/evaluation/easy/c/benchmark24_conjunctive_1.c > /dev/null
```

### 6. **Network and External Services**

- Disable network during testing (if not needed)
- Avoid network mounts for input files
- Ensure no external services are accessed

## Implementation in Test Script

The test script (`test_uautomizer_timing_determinism.py`) includes:

1. **Automatic environment setup** via `setup_deterministic_environment()`
2. **System checks** via `check_system_determinism()`
3. **Recommendations** printed if determinism test fails

## Quick Start: Maximum Determinism

```bash
# 1. Set CPU to performance mode (requires root)
sudo cpupower frequency-set -g performance

# 2. Disable turbo boost (requires root)
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo

# 3. Run test with deterministic mode
python tests/test_uautomizer_timing_determinism.py \
    --num_runs 10 \
    --epsilon 0.05 \
    --cpu-affinity 0-3

# 4. Or use taskset manually
taskset -c 0-3 nice -n -20 python tests/test_uautomizer_timing_determinism.py
```

## Expected Results

With proper determinism setup:
- **Coefficient of Variation**: < 2-5%
- **Relative Range**: < 2-5%
- **All decisions**: Same across all runs
- **No errors**: All runs complete successfully

## Troubleshooting

### High Variation (> 10%)
1. Check CPU frequency scaling: `cpupower frequency-info`
2. Check system load: `htop` or `top`
3. Verify CPU affinity: `taskset -p $$`
4. Check for background processes

### Inconsistent Decisions
- This indicates non-determinism in the verification algorithm
- Check UAutomizer logs for warnings
- May indicate an issue with the verification setup

### Memory Issues
- Ensure sufficient memory available
- Check for swap usage: `free -h`
- Increase JVM heap if needed

## Advanced: JVM Flag Customization

To add custom JVM flags, you would need to modify `Ultimate.py`:

```python
def create_ultimate_base_call():
    ultimate_bin = [
        get_java(),
        "-Dosgi.configuration.area=" + os.path.join(datadir, "config"),
        "-Xmx15G",
        "-Xms4m",
        # Add deterministic flags here
        "-XX:+UseG1GC",
        "-XX:MaxGCPauseMillis=200",
        "-XX:+DisableExplicitGC",
        # ... etc
    ]
    # ... rest of function
```

## SV-COMP-Style Setup Checklist

To best approximate SV-COMP's reproducibility standards:

- [ ] **System Idle**: Run when system has minimal load (closest to "dedicated unloaded machine")
- [ ] **CPU Performance Mode**: `sudo cpupower frequency-set -g performance`
- [ ] **Disable Turbo Boost**: `echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo`
- [ ] **CPU Affinity**: Pin to specific cores (e.g., `taskset -c 0-7`)
- [ ] **High Priority**: Use `nice -n -20` for maximum priority
- [ ] **Memory Available**: Ensure 15GB+ free memory
- [ ] **Timeout**: Use 900 seconds (15 minutes) to match SV-COMP
- [ ] **Warm Cache**: Pre-load input files before timing runs
- [ ] **Minimize Background**: Stop unnecessary services/processes

## References

- [SV-COMP Official Website](https://sv-comp.sosy-lab.org/)
- [BenchExec Documentation](https://github.com/sosy-lab/benchexec)
- [SV-COMP Reproducibility Paper](https://link.springer.com/chapter/10.1007/978-3-031-90660-2_9)
- [Java G1 GC Tuning](https://docs.oracle.com/javase/9/gctuning/g1-garbage-collector.htm)
- [Linux CPU Frequency Scaling](https://www.kernel.org/doc/html/latest/admin-guide/pm/cpufreq.html)
- [Process CPU Affinity](https://man7.org/linux/man-pages/man2/sched_setaffinity.2.html)

