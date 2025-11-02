import subprocess
import time
import os
import pprint
import json
from enum import Enum
from dataclasses import dataclass, asdict
from pathlib import Path
class Decision(Enum):
    Verified = 1
    Falsified = 2
    Unknown = 3
    # Timeout = 4
    # Error = 5
    # TRUE = "TRUE"
    # FALSE = "FALSE"
    # UNKNOWN = "UNKNOWN"
    # TIMEOUT = "TIMEOUT"
    # ERROR = "ERROR"

@dataclass
class VerifierCallReport:
    decision: Decision = Decision.Unknown
    time_taken: float = 0.0
    timeout: bool = False
    error: bool = False
    log_file_path: str = ""
    err_file_path: str = ""
    
    def to_dict(self) -> dict:
        """Convert the report to a dictionary for JSON serialization."""
        return {
            'decision': self.decision.name,  # Convert enum to string
            'time_taken': self.time_taken,
            'timeout': self.timeout,
            'error': self.error,
            'log_file_path': self.log_file_path,
            'err_file_path': self.err_file_path
        }
    
    def save_json(self, file_path: Path) -> None:
        """Save the report as a JSON file."""
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def from_json(cls, file_path: Path) -> 'VerifierCallReport':
        """Load a report from a JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls(
            decision=Decision[data['decision']],  # Convert string back to enum
            time_taken=data['time_taken'],
            timeout=data['timeout'],
            error=data['error'],
            log_file_path=data['log_file_path'],
            err_file_path=data['err_file_path']
        )
    
    
def run_uautomizer(
    uautomizer_path: str,
    c_file_path: str,
    property_file_path: str,
    reports_dir: Path,
    arch: str = '64bit',
    timeout_seconds: float = 300.0,    
) -> VerifierCallReport:
    """
    Runs the UAutomizer verifier on a given C file and measures performance.

    Args:
        uautomizer_path: Path to the UAutomizer executable (e.g., './Ultimate.py').
        c_file_path: Path to the C file to be verified.
        property_file_path: Path to the property specification file.
        reports_dir: Directory where log files will be saved.
        arch: Architecture of the target system (default: '64bit').
        timeout_seconds: Maximum time in seconds before timeout.

    Returns:
        VerifierCallReport containing the verification results and log file paths.
    """
    # --- Create reports directory ---
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate simple filenames without timestamps
    c_file_name = Path(c_file_path).stem
    log_file_path = reports_dir / f"{c_file_name}.log"
    err_file_path = reports_dir / f"{c_file_name}.err"
    
    # --- Input Validation ---
    for path in [uautomizer_path, c_file_path, property_file_path]:
        if not os.path.exists(path):
            # Save error to err file
            with open(err_file_path, 'w') as f:
                f.write(f"Required file not found at: {path}")
            report = VerifierCallReport(
                decision=Decision.Unknown,
                time_taken=0.0,
                timeout=False,
                error=True,
                log_file_path=str(log_file_path),
                err_file_path=str(err_file_path)
            )
            return report

    # --- Command Construction ---
    # Final command structure based on the --help output.
    command = [
        uautomizer_path,
        '--spec',
        str(property_file_path),
        '--architecture',
        arch,
        '--file',
        str(c_file_path),
        '--full-output'
    ]
    report = VerifierCallReport(
        log_file_path=str(log_file_path),
        err_file_path=str(err_file_path)
    )

    try:
        # --- Execution and Timing ---
        start_time = time.perf_counter()
        completed_process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False
        )
        end_time = time.perf_counter()

        report.time_taken = end_time - start_time
        
        # Save stdout and stderr to files
        with open(log_file_path, 'w') as f:
            f.write(completed_process.stdout)
        with open(err_file_path, 'w') as f:
            f.write(completed_process.stderr)

        # --- Result Parsing ---
        if "Result:" in completed_process.stdout:
            if "Result:\nTRUE" in completed_process.stdout or "Result: TRUE" in completed_process.stdout:
                report.decision = Decision.Verified
            elif "Result:\nFALSE" in completed_process.stdout or "Result: FALSE" in completed_process.stdout:
                report.decision = Decision.Falsified
            elif "Result:\nUNKNOWN" in completed_process.stdout or "Result: UNKNOWN" in completed_process.stdout:
                report.decision = Decision.Unknown
            else:
                report.decision = Decision.Unknown
        else:
             report.error = True

    except subprocess.TimeoutExpired as e:
        report.timeout = True
        report.time_taken = timeout_seconds
        # Save timeout output to files (handle bytes/str)
        with open(log_file_path, 'w') as f:
            f.write(e.stdout.decode('utf-8', errors='ignore') if isinstance(e.stdout, bytes) else (e.stdout or ""))
        with open(err_file_path, 'w') as f:
            f.write(e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else (e.stderr or ""))
    except Exception as e:
        report.error = True
        # Save exception to err file
        with open(err_file_path, 'w') as f:
            f.write(str(e))

    return report

# --- Example Usage ---
if __name__ == "__main__":
    # --- IMPORTANT: UPDATE THESE PATHS ---
    # This should be the path to the script in your UAutomizer directory.
    UAUTOMIZER_EXECUTABLE_PATH = '/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/tools/uautomizer/Ultimate.py'
    C_FILE_PATH = 'dataset/evaluation/problem.c'
    # This is the property file, likely located in the 'config' subdirectory.
    SPEC_FILE_PATH = 'dataset/properties/unreach-call.prp' # <-- UPDATE IF NEEDED

    print(f"--- Running UAutomizer on {C_FILE_PATH} ---")
    with open(C_FILE_PATH, 'r') as file:
        program = file.read()
    print(f"Program: {program}")
    # Create a reports directory for this example
    reports_dir = Path("example_reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    verification_result = run_uautomizer(
        uautomizer_path=UAUTOMIZER_EXECUTABLE_PATH,
        c_file_path=C_FILE_PATH,
        property_file_path=SPEC_FILE_PATH,
        reports_dir=reports_dir,
        arch="32bit", # Explicitly set architecture
        timeout_seconds=60
    )

    print("\n--- Verification Complete ---")
    pprint.pprint(verification_result)