"""UAutomizer verifier interface for running verification and parsing results."""
import json
import os
import subprocess
import shutil
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Union

@dataclass
class VerifierCallReport:
    """Report containing verification results and metadata."""
    decision: str = "UNKNOWN" # "TRUE", "FALSE", "UNKNOWN"
    time_taken: float = 0.0
    timeout: bool = False
    error: bool = False
    reports_dir: str = ""  
      
    def to_dict(self) -> dict:
        """Convert report to dictionary for JSON serialization."""
        return {
            'decision': self.decision,
            'time_taken': self.time_taken,
            'timeout': self.timeout,
            'error': self.error,
            # 'log_file_path': self.log_file_path,
            # 'err_file_path': self.err_file_path
            'reports_dir': self.reports_dir
        }
    
    def save_json(self, file_path: Path) -> None:
        """Save report as JSON file."""
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def from_json(cls, file_path: Path) -> 'VerifierCallReport':
        """Load report from JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls(
            decision=data['decision'],
            time_taken=data['time_taken'],
            timeout=data['timeout'],
            error=data['error'],
            # log_file_path=data['log_file_path'],
            # err_file_path=data['err_file_path']
            reports_dir=data['reports_dir']
        )


def _parse_result(output: str) -> str:
    """Parse verification result from UAutomizer output (returns "TRUE", "FALSE", or "UNKNOWN") and whether there was an error."""
    if "Result: TRUE" in output or "Result:\nTRUE" in output:
        return "TRUE", False
    if "Result: FALSE" in output or "Result:\nFALSE" in output:
        return "FALSE", False
    if "Result: UNKNOWN" in output or "Result:\nUNKNOWN" in output:
        return "UNKNOWN", False
    return "UNKNOWN", True


def _write_file(file_path: Path, content: str) -> None:
    """Helper to write content to file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        f.write(content)

def run_uautomizer(
    program_path: Path,
    property_file_path: Path,
    reports_dir: Path,
    arch: str = '32bit',
    timeout_seconds: float = 600.0,
    uautomizer_path: Path = None,
) -> VerifierCallReport:
    """
    Run UAutomizer verifier on a C file.
    
    Args:
        program_path: Path to the C program to verify.
        property_file_path: Path to the property specification file (.prp).
        reports_dir: Directory where log files will be saved.
        arch: Architecture ('32bit' or '64bit').
        timeout_seconds: Maximum execution time in seconds.
        uautomizer_path: Path to UAutomizer executable. If None, uses default.
    
    Returns:
        VerifierCallReport with verification results and metadata.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = reports_dir / f"{program_path.stem}.log"
    err_file_path = reports_dir / f"{program_path.stem}.err"
    
    # Validate required files exist
    for path in [uautomizer_path, program_path, property_file_path]:
        if not path.exists():
            _write_file(err_file_path, f"Required file not found: {path}")
            return VerifierCallReport(reports_dir=str(reports_dir))
    
    # Build command
    command = [
        'python3',
        str(uautomizer_path),
        '--spec', str(property_file_path),
        '--architecture', arch,
        '--file', str(program_path),
        '--full-output',
        '--witness-dir', str(reports_dir),
        '--witness-name', f"{program_path.stem}_witness",
    ]
    
    # Setup environment with uautomizer directory in PATH for SMT solvers
    uautomizer_dir = uautomizer_path.parent
    env = os.environ.copy()
    env['PATH'] = str(uautomizer_dir) + os.pathsep + env.get('PATH', '')
    
    report = VerifierCallReport(
        reports_dir=str(reports_dir)
    )
    # In run_uautomizer function, create a unique temp directory for each invocation
    temp_work_dir = Path(tempfile.mkdtemp(prefix="uautomizer_"))
    try:
        start_time = time.perf_counter()
        completed_process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
            cwd=temp_work_dir
        )

        report.time_taken = time.perf_counter() - start_time
        
        _write_file(log_file_path, completed_process.stdout)
        _write_file(err_file_path, completed_process.stderr)
        
        report.decision, report.error = _parse_result(completed_process.stdout)
            
    except subprocess.TimeoutExpired as e:
        report.timeout = True
        report.time_taken = timeout_seconds
        stdout_content = e.stdout.decode('utf-8', errors='ignore') if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr_content = e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else (e.stderr or "")
        _write_file(log_file_path, stdout_content)
        _write_file(err_file_path, stderr_content)
        
    except Exception as e:
        report.error = True
        _write_file(err_file_path, str(e))
    
    finally:
        # Optionally clean up temp directory after copying any needed files
        shutil.rmtree(temp_work_dir)
    return report


if __name__ == "__main__":
    import argparse
    import pprint
    
    parser = argparse.ArgumentParser(description="Run UAutomizer verifier")
    parser.add_argument("--root_dir", type=Path, 
                       default=Path('/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv'))
    parser.add_argument("--data_split", type=str, default='easy')
    parser.add_argument("--program_name", type=str, default='benchmark24_conjunctive_1')
    parser.add_argument("--property_file_path", type=str, default='unreach-call.prp')
    parser.add_argument("--arch", type=str, default='32bit', choices=['32bit', '64bit'])
    parser.add_argument("--timeout_seconds", type=int, default=600)
    parser.add_argument("--uautomizer_version", type=str, default='UAutomizer25', choices=['uautomizer23', 'uautomizer24', 'uautomizer25', 'uautomizer26'])
    args = parser.parse_args()
    uautomizer_version = args.uautomizer_version.replace('UAutomizer', '')
    program_path = args.root_dir / 'dataset' / 'evaluation'/'full'/ uautomizer_version / args.data_split / 'c' / f"{args.program_name}.c"
    property_file_path = args.root_dir / 'dataset' / 'properties' / args.property_file_path
    reports_dir = args.root_dir / "example_reports"
    uautomizer_path = args.root_dir / "tools" / args.uautomizer_version / "Ultimate.py"
    
    print(f"Running UAutomizer on {program_path}")
    print(f"  Property: {property_file_path}")
    print(f"  Architecture: {args.arch}")
    print(f"  Timeout: {args.timeout_seconds}s")
    print(f"  UAutomizer version: {args.uautomizer_version}")
    
    result = run_uautomizer(
        program_path=program_path,
        property_file_path=property_file_path,
        reports_dir=reports_dir,
        arch=args.arch,
        timeout_seconds=args.timeout_seconds,
        uautomizer_path=uautomizer_path
    )
    
    print("\n--- Verification Complete ---")
    pprint.pprint(result.to_dict())
