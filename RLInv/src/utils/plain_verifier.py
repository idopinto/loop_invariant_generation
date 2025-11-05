"""UAutomizer verifier interface for running verification and parsing results."""
import json
import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Union


class Decision(Enum):
    """Verification result decision."""
    Verified = 1
    Falsified = 2
    Unknown = 3


@dataclass
class VerifierCallReport:
    """Report containing verification results and metadata."""
    decision: Decision = Decision.Unknown
    time_taken: float = 0.0
    timeout: bool = False
    error: bool = False
    log_file_path: str = ""
    err_file_path: str = ""
    
    def to_dict(self) -> dict:
        """Convert report to dictionary for JSON serialization."""
        return {
            'decision': self.decision.name,
            'time_taken': self.time_taken,
            'timeout': self.timeout,
            'error': self.error,
            'log_file_path': self.log_file_path,
            'err_file_path': self.err_file_path
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
            decision=Decision[data['decision']],
            time_taken=data['time_taken'],
            timeout=data['timeout'],
            error=data['error'],
            log_file_path=data['log_file_path'],
            err_file_path=data['err_file_path']
        )


def _parse_result(output: str) -> Decision:
    """Parse verification result from UAutomizer output."""
    if "Result:" not in output:
        return Decision.Unknown
    
    if "Result:\nTRUE" in output or "Result: TRUE" in output:
        return Decision.Verified
    elif "Result:\nFALSE" in output or "Result: FALSE" in output:
        return Decision.Falsified
    elif "Result:\nUNKNOWN" in output or "Result: UNKNOWN" in output:
        return Decision.Unknown
    return Decision.Unknown


def _write_file(file_path: Path, content: str) -> None:
    """Helper to write content to file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        f.write(content)


def _get_uautomizer_path(root_dir: Optional[Path] = None) -> Path:
    """Get default UAutomizer executable path."""
    if root_dir:
        return root_dir / "tools" / "uautomizer" / "Ultimate.py"
    return Path('/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/tools/uautomizer/Ultimate.py')


def run_uautomizer(
    c_file_path: Union[Path, str],
    property_file_path: Union[Path, str],
    reports_dir: Union[Path, str],
    arch: str = '32bit',
    timeout_seconds: float = 600.0,
    uautomizer_path: Optional[Union[Path, str]] = None,
) -> VerifierCallReport:
    """
    Run UAutomizer verifier on a C file.
    
    Args:
        c_file_path: Path to the C file to verify.
        property_file_path: Path to the property specification file (.prp).
        reports_dir: Directory where log files will be saved.
        arch: Architecture ('32bit' or '64bit').
        timeout_seconds: Maximum execution time in seconds.
        uautomizer_path: Path to UAutomizer executable. If None, uses default.
    
    Returns:
        VerifierCallReport with verification results and metadata.
    """
    # Convert all paths to Path objects
    uautomizer_path = Path(uautomizer_path) if uautomizer_path else _get_uautomizer_path()
    c_file_path = Path(c_file_path)
    property_file_path = Path(property_file_path)
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    log_file_path = reports_dir / f"{c_file_path.stem}.log"
    err_file_path = reports_dir / f"{c_file_path.stem}.err"
    
    # Validate required files exist
    for path in [uautomizer_path, c_file_path, property_file_path]:
        if not path.exists():
            _write_file(err_file_path, f"Required file not found: {path}")
            return VerifierCallReport(
                decision=Decision.Unknown,
                time_taken=0.0,
                error=True,
                log_file_path=str(log_file_path),
                err_file_path=str(err_file_path)
            )
    
    # Build command
    command = [
        'python3',
        str(uautomizer_path),
        '--spec', str(property_file_path),
        '--architecture', arch,
        '--file', str(c_file_path),
        '--full-output'
    ]
    
    # Setup environment with uautomizer directory in PATH for SMT solvers
    uautomizer_dir = uautomizer_path.parent
    env = os.environ.copy()
    env['PATH'] = str(uautomizer_dir) + os.pathsep + env.get('PATH', '')
    
    report = VerifierCallReport(
        log_file_path=str(log_file_path),
        err_file_path=str(err_file_path)
    )
    
    try:
        start_time = time.perf_counter()
        completed_process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env
        )
        report.time_taken = time.perf_counter() - start_time
        
        _write_file(log_file_path, completed_process.stdout)
        _write_file(err_file_path, completed_process.stderr)
        
        report.decision = _parse_result(completed_process.stdout)
        if report.decision == Decision.Unknown and "Result:" not in completed_process.stdout:
            report.error = True
            
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
    
    return report


if __name__ == "__main__":
    import argparse
    import pprint
    
    parser = argparse.ArgumentParser(description="Run UAutomizer verifier")
    parser.add_argument("--root_dir", type=Path, 
                       default=Path('/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv'))
    parser.add_argument("--data_split", type=str, default='easy')
    parser.add_argument("--c_file_path", type=str, default='benchmark24_conjunctive_1.c')
    parser.add_argument("--spec_file_path", type=str, default='unreach-call.prp')
    parser.add_argument("--arch", type=str, default='32bit', choices=['32bit', '64bit'])
    parser.add_argument("--timeout_seconds", type=int, default=600)
    
    args = parser.parse_args()
    
    c_file = args.root_dir / 'dataset' / 'evaluation' / args.data_split / 'c' / args.c_file_path
    spec_file = args.root_dir / 'dataset' / 'properties' / args.spec_file_path
    reports_dir = args.root_dir / "example_reports"
    uautomizer_path = args.root_dir / "tools" / "uautomizer" / "Ultimate.py"
    
    print(f"Running UAutomizer on {c_file}")
    print(f"  Property: {spec_file}")
    print(f"  Architecture: {args.arch}")
    print(f"  Timeout: {args.timeout_seconds}s")
    
    result = run_uautomizer(
        c_file_path=c_file,
        property_file_path=spec_file,
        reports_dir=reports_dir,
        arch=args.arch,
        timeout_seconds=args.timeout_seconds,
        uautomizer_path=uautomizer_path
    )
    
    print("\n--- Verification Complete ---")
    pprint.pprint(result.to_dict())
