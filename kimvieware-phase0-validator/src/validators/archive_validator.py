"""
Archive Integrity Validator
"""
import zipfile
import tarfile
import magic
from pathlib import Path
from typing import Tuple, Optional

class ArchiveValidator:
    """Validates archive integrity"""
    
    SUPPORTED_TYPES = {
        'application/zip': 'zip',
        'application/x-tar': 'tar',
        'application/gzip': 'tar.gz',
    }
    
    @staticmethod
    def validate(archive_path: Path) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate archive
        Returns: (is_valid, archive_type, error_message)
        """
        if not archive_path.exists():
            return False, None, f"File not found: {archive_path}"
        
        # Detect MIME type
        try:
            mime_type = magic.from_file(str(archive_path), mime=True)
        except Exception as e:
            return False, None, f"Failed to detect type: {str(e)}"
        
        archive_type = ArchiveValidator.SUPPORTED_TYPES.get(mime_type)
        if not archive_type:
            return False, None, f"Unsupported type: {mime_type}"
        
        # Test integrity
        try:
            if archive_type == 'zip':
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    bad = zf.testzip()
                    if bad:
                        return False, archive_type, f"Corrupted: {bad}"
            elif 'tar' in archive_type:
                with tarfile.open(archive_path, 'r:*') as tf:
                    _ = tf.getmembers()
            
            return True, archive_type, None
        except Exception as e:
            return False, archive_type, f"Integrity check failed: {str(e)}"
    
    @staticmethod
    def extract(archive_path: Path, dest_dir: Path, archive_type: str) -> Path:
        """Extract archive"""
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        if archive_type == 'zip':
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(dest_dir)
        elif 'tar' in archive_type:
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(dest_dir)
        
        return dest_dir
