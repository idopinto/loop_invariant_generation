import subprocess
import sys
import os
import platform
from pathlib import Path
from typing import Dict, Optional, Any
import re


def get_verifier_version(verifier_executable_path: str) -> Dict[str, str]:
    """Get verifier version information."""
    versions = {}
    
    # Try --version
    try:
        result = subprocess.run(
            [sys.executable, verifier_executable_path, '--version'],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Check both stdout and stderr (version info might be in either)
        output = (result.stdout + result.stderr).strip()
        if output:
            # Usually just a commit hash or version string
            versions['version'] = output.split('\n')[0].strip()
        else:
            versions['version'] = "unknown"
    except Exception as e:
        versions['version'] = f"unknown ({str(e)})"
    
    # Try --ultversion
    try:
        result = subprocess.run(
            [sys.executable, verifier_executable_path, '--ultversion'],
            capture_output=True,
            text=True,
            timeout=30
        )
        output = (result.stdout + result.stderr).strip()
        # Parse the version line (e.g., "This is Ultimate 0.2.2-dev-2329fc7")
        for line in output.split('\n'):
            if 'This is Ultimate' in line:
                # Extract version string
                parts = line.split('This is Ultimate')
                if len(parts) > 1:
                    versions['ultversion'] = parts[1].strip()
                    break
        if 'ultversion' not in versions:
            versions['ultversion'] = "unknown"
    except Exception as e:
        versions['ultversion'] = f"unknown ({str(e)})"
    
    return versions

def get_system_info() -> Dict[str, str]:
    """Get system hardware information."""
    try:
        # Get CPU info - matters for timing reproducibility
        cpu_info = "unknown"
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('model name'):
                        cpu_info = line.split(':')[1].strip()
                        break
        except (FileNotFoundError, PermissionError):
            pass
        
        # Get SLURM node name if available
        slurm_node = os.environ.get('SLURM_NODELIST') or os.environ.get('SLURMD_NODENAME')
        
        system_info = {
            "architecture": platform.machine(),
            "cpu": cpu_info,
            "python_version": platform.python_version()
        }
        
        if slurm_node:
            system_info["slurm_node"] = slurm_node
        
        return system_info
    except Exception:
        return {
            "architecture": platform.machine(),
            "cpu": "unknown",
            "python_version": platform.python_version()
        }

def detect_slurm_resources() -> Dict[str, int]:
    """Detect SLURM resource allocation from environment variables."""
    resources = {}
    
    # SLURM CPUs
    if 'SLURM_CPUS_PER_TASK' in os.environ:
        try:
            resources['slurm_cpus_per_task'] = int(os.environ['SLURM_CPUS_PER_TASK'])
        except (ValueError, TypeError):
            pass
    elif 'SLURM_CPUS_ON_NODE' in os.environ:
        try:
            resources['slurm_cpus_per_task'] = int(os.environ['SLURM_CPUS_ON_NODE'])
        except (ValueError, TypeError):
            pass
    
    # SLURM Memory (can be in MB or GB, need to parse)
    if 'SLURM_MEM_PER_NODE' in os.environ:
        try:
            mem_mb = int(os.environ['SLURM_MEM_PER_NODE'])
            resources['slurm_memory_gb'] = mem_mb // 1024  # Convert MB to GB
        except (ValueError, TypeError):
            pass
    elif 'SLURM_MEM_PER_CPU' in os.environ:
        try:
            mem_mb_per_cpu = int(os.environ['SLURM_MEM_PER_CPU'])
            cpus = resources.get('slurm_cpus_per_task', 1)
            resources['slurm_memory_gb'] = (mem_mb_per_cpu * cpus) // 1024
        except (ValueError, TypeError):
            pass
    
    # SLURM Time limit (format: "HH:MM:SS" or seconds as string, or "UNLIMITED")
    if 'SLURM_TIME_LIMIT' in os.environ:
        time_str = os.environ['SLURM_TIME_LIMIT']
        try:
            # Skip if unlimited
            if time_str.upper() == 'UNLIMITED':
                pass
            # Try parsing as seconds first
            elif ':' not in time_str:
                seconds = int(time_str)
                if seconds > 0:
                    resources['slurm_timeout_hours'] = seconds // 3600
            else:
                # Parse HH:MM:SS format
                parts = time_str.split(':')
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = int(parts[2])
                    total_hours = hours + minutes / 60 + seconds / 3600
                    if total_hours > 0:
                        resources['slurm_timeout_hours'] = int(total_hours) if total_hours < 1 else round(total_hours, 1)
        except (ValueError, TypeError, IndexError):
            pass
    
    return resources

def detect_java_heap_size(uautomizer_path: str) -> Optional[int]:
    """Detect Java heap size from UAutomizer script or environment."""
    # Check _JAVA_OPTIONS environment variable first
    if '_JAVA_OPTIONS' in os.environ:
        java_opts = os.environ['_JAVA_OPTIONS']
        # Look for -Xmx pattern (e.g., -Xmx15G, -Xmx12288M)
        match = re.search(r'-Xmx(\d+)([GMK])', java_opts)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if unit == 'G':
                return value
            elif unit == 'M':
                return value // 1024  # Convert MB to GB
            elif unit == 'K':
                return value // (1024 * 1024)
    
    # Try to parse from Ultimate.py file
    try:
        uautomizer_file = Path(uautomizer_path)
        if uautomizer_file.exists():
            with open(uautomizer_file, 'r') as f:
                content = f.read()
                # Look for -Xmx pattern in the script
                match = re.search(r'-Xmx(\d+)([GMK])', content)
                if match:
                    value = int(match.group(1))
                    unit = match.group(2)
                    if unit == 'G':
                        return value
                    elif unit == 'M':
                        return value // 1024
                    elif unit == 'K':
                        return value // (1024 * 1024)
    except Exception:
        pass
    
    return None

def detect_z3_memory_limit(uautomizer_path: str) -> Optional[int]:
    """Detect Z3 memory limit from UAutomizer configuration."""
    # Z3 memory limit can be set in multiple places:
    # 1. Ultimate.py script (as -memory: parameter)
    # 2. Config XML files (in tools/uautomizer/config/)
    # 3. Environment variables
    
    # First, check Ultimate.py script
    try:
        uautomizer_file = Path(uautomizer_path)
        if uautomizer_file.exists():
            with open(uautomizer_file, 'r') as f:
                content = f.read()
                # Look for -memory: pattern (e.g., -memory:12288)
                match = re.search(r'-memory:(\d+)', content)
                if match:
                    return int(match.group(1))
    except Exception:
        pass
    
    # Check config XML files
    try:
        uautomizer_dir = Path(uautomizer_path).parent
        config_dir = uautomizer_dir / "config"
        if config_dir.exists():
            for config_file in config_dir.glob("*.xml"):
                try:
                    with open(config_file, 'r') as f:
                        content = f.read()
                        # Look for memory settings in XML (could be various formats)
                        # Common patterns: memory="12288", -memory:12288, memory:12288
                        matches = re.findall(r'(?:memory=|memory:|-memory:)"?(\d+)"?', content, re.IGNORECASE)
                        for match in matches:
                            mem_val = int(match)
                            # Z3 memory is typically in MB, values like 2024, 12288 are common
                            if mem_val >= 1000:  # Reasonable Z3 memory limit (at least 1GB)
                                return mem_val
                except Exception:
                    continue
    except Exception:
        pass
    
    return None

def get_runtime_configuration(uautomizer_path: str) -> Dict[str, Any]:
    """Get runtime configuration values dynamically."""
    config = {}
    
    # Detect SLURM resources
    slurm_resources = detect_slurm_resources()
    config.update(slurm_resources)
    
    # Detect Java heap size
    java_heap = detect_java_heap_size(uautomizer_path)
    if java_heap is not None:
        config['uautomizer_java_heap_max_gb'] = java_heap
    
    # Detect Z3 memory limit
    z3_memory = detect_z3_memory_limit(uautomizer_path)
    if z3_memory is not None:
        config['z3_memory_limit_mb'] = z3_memory
    
    return config