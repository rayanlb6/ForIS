"""
Phase 1: Path Extractor Service
Consumes: validation.completed
Produces: extraction.completed
"""
import sys
from pathlib import Path
import os
from datetime import datetime, timezone

from kimvieware_shared import MicroserviceBase, JobStatus
from extractors import PythonExtractor, CExtractor, JavaExtractor, JSExtractor  # ✅ JSExtractor importé


class ExtractorService(MicroserviceBase):
    """Phase 1: Symbolic Execution Path Extractor"""

    def __init__(self):
        super().__init__(
            service_name="Phase1_Extractor",
            input_queue="validation.completed",
            output_queue="extraction.completed"
        )

        self.max_paths = int(os.getenv('EXTRACTOR_MAX_PATHS', '1000'))

        # Initialize extractors
        self.python_extractor = PythonExtractor(max_paths=self.max_paths)
        self.c_extractor      = CExtractor(max_paths=self.max_paths)
        self.java_extractor   = JavaExtractor(max_paths=self.max_paths)
        self.js_extractor     = JSExtractor(max_paths=self.max_paths)  # ✅ Ajouté

    def process_message(self, message: dict) -> dict:
        """Extract symbolic execution paths"""

        job_id = message['job_id']

        if message.get('status') != JobStatus.VALIDATED.value:
            self.logger.warning(
                f"[{job_id}] Skipping job: status is not 'validated'. "
                f"Current status: {message.get('status')}"
            )
            return self._error_response(
                job_id,
                f"Job was not validated. Current status: {message.get('status')}"
            )

        sut_info       = message['sut_info']
        extracted_path = Path(message['extracted_path'])
        language       = sut_info['language']

        self.logger.info(f"[{job_id}] Extracting paths from {language} service")
        self.logger.info(f"[{job_id}] Path: {extracted_path}")
        self.logger.info(f"[{job_id}] Entry point: {sut_info.get('entry_point')}")

        # --- Dispatch vers le bon extracteur ---
        if language == 'python':
            trajectories = self.python_extractor.extract_paths(extracted_path)

        elif language == 'java':
            self.logger.info(f"[{job_id}] Using Java extractor")
            trajectories = self.java_extractor.extract_paths(extracted_path)

        elif language in ['c', 'cpp']:
            self.logger.info(f"[{job_id}] Using C/C++ extractor")
            trajectories = self.c_extractor.extract_paths(extracted_path)

        elif language in ['javascript', 'typescript']:          # ✅ typescript aussi
            self.logger.info(f"[{job_id}] Using JS/TS extractor (acorn)")
            trajectories = self.js_extractor.extract_paths(extracted_path)

        else:
            return self._error_response(job_id, f"Unsupported language: {language}")

        self.logger.info(f"[{job_id}] Extracted {len(trajectories)} trajectories")

        # Nom de l'extracteur utilisé pour les métadonnées
        extractor_name = {
            'python':     'python',
            'java':       'javalang',
            'c':          'clang',
            'cpp':        'clang',
            'javascript': 'acorn',
            'typescript': 'acorn',
        }.get(language, 'unknown')

        return {
            'job_id':             job_id,
            'status':             JobStatus.EXTRACTED.value,
            'sut_info':           sut_info,
            'trajectories_count': len(trajectories),
            'trajectories':       [t.to_dict() for t in trajectories],
            'metadata': {
                'language':           language,
                'extractor':          extractor_name,
                'trajectories_count': len(trajectories),
                'timestamp':          datetime.now(timezone.utc).isoformat()
            }
        }

    def _error_response(self, job_id: str, error: str) -> dict:
        """Error response"""
        return {
            'job_id': job_id,
            'status': JobStatus.FAILED.value,
            'error':  error,
            'phase':  'extraction'
        }


if __name__ == "__main__":
    service = ExtractorService()
    service.start()