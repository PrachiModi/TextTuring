"""
Utility functions for detecting network drives and optimizing performance.
"""
import os
import platform
import subprocess
import tempfile
import time


def is_network_drive(path: str) -> bool:
    """
    Detect if a given path is on a network drive (Google Drive, OneDrive, network share, etc.).
    
    Args:
        path: Path to check.
        
    Returns:
        bool: True if the path is on a network drive, False otherwise.
    """
    if not os.path.exists(path):
        return False
    
    try:
        abs_path = os.path.abspath(path)
        system = platform.system()
        
        # Common network drive indicators
        network_indicators = [
            'google drive',
            'googledrive',
            'onedrive',
            'dropbox',
            'icloud',
            'box sync',
            'sharepoint',
        ]
        
        path_lower = abs_path.lower()
        for indicator in network_indicators:
            if indicator in path_lower:
                return True
        
        if system == "Darwin":  # macOS
            # Check if mounted volume
            if abs_path.startswith('/Volumes/'):
                return True
            
            # Check if Google Drive File Stream
            if '/Google Drive/' in abs_path or '/GoogleDrive/' in abs_path:
                return True
            
            # Try to determine if it's a network mount using df command
            try:
                result = subprocess.run(
                    ['df', abs_path],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                output = result.stdout.lower()
                # Network filesystem types
                if any(fs in output for fs in ['nfs', 'smb', 'cifs', 'afp', 'fuse', 'osxfuse']):
                    return True
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
        
        elif system == "Windows":
            # Check if UNC path
            if abs_path.startswith('\\\\'):
                return True
            
            # Check if mapped network drive
            try:
                drive = abs_path.split(':')[0] + ':'
                result = subprocess.run(
                    ['net', 'use'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if drive in result.stdout:
                    return True
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, IndexError):
                pass
        
        elif system == "Linux":
            # Check if in /mnt or /media
            if abs_path.startswith(('/mnt/', '/media/')):
                return True
            
            # Try to determine filesystem type
            try:
                result = subprocess.run(
                    ['df', '-T', abs_path],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                output = result.stdout.lower()
                if any(fs in output for fs in ['nfs', 'cifs', 'smb', 'fuse']):
                    return True
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
        
        # Performance-based heuristic: Test write speed
        # Network drives are typically slower
        return _is_slow_filesystem(path)
    
    except Exception:
        return False


def _is_slow_filesystem(path: str, threshold_mb_per_sec: float = 50.0) -> bool:
    """
    Test if filesystem is slow by writing a small test file.
    Network drives typically have slower write speeds.
    
    Args:
        path: Path to test.
        threshold_mb_per_sec: Speed threshold in MB/s (default: 50 MB/s).
        
    Returns:
        bool: True if filesystem appears slow (likely network), False otherwise.
    """
    try:
        # Create a small test file (1MB)
        test_size = 1024 * 1024  # 1 MB
        test_data = b'0' * test_size
        
        # Use temp file in the target directory
        with tempfile.NamedTemporaryFile(dir=path, delete=False) as tmp_file:
            tmp_path = tmp_file.name
            
            # Measure write time
            start_time = time.time()
            tmp_file.write(test_data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())  # Force write to disk
            write_time = time.time() - start_time
        
        # Clean up
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        
        # Calculate speed
        if write_time > 0:
            speed_mb_per_sec = (test_size / (1024 * 1024)) / write_time
            return speed_mb_per_sec < threshold_mb_per_sec
        
        return False
    
    except Exception:
        # If we can't test, assume it's not a network drive
        return False


def get_network_drive_info(path: str) -> dict:
    """
    Get information about whether a path is on a network drive and recommendations.
    
    Args:
        path: Path to check.
        
    Returns:
        dict: Information about the path including:
            - is_network: bool
            - warning_message: str (if applicable)
            - recommendation: str (if applicable)
    """
    is_network = is_network_drive(path)
    
    info = {
        'is_network': is_network,
        'warning_message': '',
        'recommendation': ''
    }
    
    if is_network:
        info['warning_message'] = (
            "⚠️ Network Drive Detected\n\n"
            "The selected folder appears to be on a network drive "
            "(Google Drive, OneDrive, network share, etc.).\n\n"
            "Processing may be significantly slower compared to a local folder."
        )
        info['recommendation'] = (
            "For best performance:\n"
            "1. Copy the folder to your local drive (Desktop, Documents, etc.)\n"
            "2. Process the local copy\n"
            "3. Copy results back to the network drive when done\n\n"
            "Or continue with the network folder (will be slower)."
        )
    
    return info


def estimate_performance_impact(path: str, file_count: int) -> dict:
    """
    Estimate the performance impact of using a network drive.
    
    Args:
        path: Path to check.
        file_count: Number of files to process.
        
    Returns:
        dict: Performance estimates including:
            - is_network: bool
            - estimated_speedup: float (how much faster local would be)
            - local_estimate_sec: float
            - network_estimate_sec: float
    """
    is_network = is_network_drive(path)
    
    # Rough estimates based on typical performance characteristics
    # Local SSD: ~500 MB/s, Network: ~50 MB/s = 10x slower
    # But actual impact depends on file sizes and operations
    
    base_time_per_file = 0.1  # seconds (for XML parsing, etc.)
    network_overhead = 5.0 if is_network else 1.0  # 5x slower on network
    
    estimated_time = file_count * base_time_per_file * network_overhead
    local_time = file_count * base_time_per_file
    
    return {
        'is_network': is_network,
        'estimated_speedup': network_overhead if is_network else 1.0,
        'local_estimate_sec': local_time,
        'network_estimate_sec': estimated_time
    }


