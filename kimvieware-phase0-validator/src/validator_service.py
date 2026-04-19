"""
Phase 0: SUT Validator Service
"""

import sys
from pathlib import Path
import hashlib

from kimvieware_shared import MicroserviceBase, SUTInfo, JobStatus, JobStorage
from validators.archive_validator import ArchiveValidator
from validators.language_detector import LanguageDetector

class ValidatorService(MicroserviceBase):
    """Phase 0: Validator"""
    
    def __init__(self):
        super().__init__(
            service_name="Phase0_Validator",
            input_queue="submission.new",
            output_queue="validation.completed"
        )
        
        self.work_dir = Path("/tmp/kimvieware_validator")
        self.work_dir.mkdir(exist_ok=True, parents=True)
        self.storage = JobStorage() # Initialize JobStorage
    
    def process_message(self, message: dict) -> dict:
        """Validate SUT"""
        job_id = message['job_id']
        sut_path = Path(message['sut_path'])
        
        self.logger.info(f"[{job_id}] Validating {sut_path.name}")
        
        # Check exists
        if not sut_path.exists():
            return self._rejection(job_id, f"File not found: {sut_path}")
        
        # Validate archive
        is_valid, archive_type, error = ArchiveValidator.validate(sut_path)
        if not is_valid:
            return self._rejection(job_id, error)
        
        self.logger.info(f"[{job_id}] Archive OK ({archive_type})")
        
        # Extract
        extract_dir = self.work_dir / job_id
        try:
            ArchiveValidator.extract(sut_path, extract_dir, archive_type)
            self.logger.info(f"[{job_id}]  Extracted")
        except Exception as e:
            return self._rejection(job_id, f"Extraction failed: {str(e)}")
        
        # Detect language
        lang_info = LanguageDetector.detect(extract_dir, logger=self.logger)
        
        if lang_info['language'] not in LanguageDetector.SUPPORTED_LANGUAGES:
            return self._rejection(
                job_id,
                f"Unsupported: {lang_info['language']}"
            )
        
        self.logger.info(f"[{job_id}] 🔍 Language: {lang_info['language']}")
        if lang_info.get('framework'):
            self.logger.info(f"[{job_id}] 🏗️  Framework: {lang_info['framework']}")
        
        # Find entry
        entry = LanguageDetector.find_entry_point(
            lang_info['files'],
            lang_info['language']
        )
        
        # Checksum
        checksum = self._checksum(extract_dir)
        
        # Build SUT info
        sut_info = SUTInfo(
            language=lang_info['language'],
            framework=lang_info.get('framework'),
            size_bytes=sum(f.stat().st_size for f in lang_info['files']) if lang_info['files'] else 0, # Added check for empty files list
            files_count=lang_info['file_count'],
            entry_point=str(entry.relative_to(extract_dir)) if entry else None,
            checksum=checksum
        )
        
        self.logger.info(f"[{job_id}] Validated")

        # --- NEW: Update MongoDB directly ---
        phase0_data = {
            'language': sut_info.language,
            'framework': sut_info.framework,
            'confidence': lang_info['confidence'],
            'files_count': sut_info.files_count,
            'size_bytes': sut_info.size_bytes,
            'entry_point': sut_info.entry_point,
            'checksum': sut_info.checksum,
            'extracted_path': str(extract_dir)
        }
        self.storage.update_phase(job_id, 'phase0', phase0_data)
        
        # Update overall job status and SUT info
        self.storage.save_job({
            'job_id': job_id,
            'status': JobStatus.VALIDATED.value,
            'sut_info': sut_info.to_dict(), # SUT info should be stored at top level for dashboard
            'extracted_path': str(extract_dir), # Also store at top level for convenience
        })

        # The base class will handle publishing the returned message
        return {
            'job_id': job_id,
            'status': JobStatus.VALIDATED.value,
            'sut_info': sut_info.to_dict(),
            'extracted_path': str(extract_dir)
        }


    def _rejection(self, job_id: str, reason: str) -> dict:
        """Rejection message"""
        self.logger.warning(f"[{job_id}] {reason}")
        
        # --- NEW: Update MongoDB directly for failed jobs ---
        self.storage.save_job({
            'job_id': job_id,
            'status': JobStatus.FAILED.value,
            'error': reason,
            'phase': 'validation'
        })
        # --- END NEW ---

        return {
            'job_id': job_id,
            'status': JobStatus.FAILED.value,
            'error': reason,
            'phase': 'validation'
        }
    
    def _checksum(self, directory: Path) -> str:
        """Calculate SHA256"""
        hasher = hashlib.sha256()
        for f in sorted(directory.rglob('*')):
            if f.is_file():
                hasher.update(f.read_bytes())
        return hasher.hexdigest()

if __name__ == "__main__":
    service = ValidatorService()
    service.start()