"""
Phase 2: SGATS Reduction Service

Consumes: extraction.completed
Produces: reduction.completed
"""
import sys
from pathlib import Path
import json # Import json for deepcopy or similar if needed for safety

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'kimvieware-shared' / 'src'))

from kimvieware_shared import MicroserviceBase, JobStatus, Trajectory
from algorithms.sgats import SGATS

class SGATSService(MicroserviceBase):
    """Phase 2: SGATS Path Reduction"""
    
    def __init__(self):
        super().__init__(
            service_name="Phase2_SGATS",
            input_queue="extraction.completed",
            output_queue="reduction.completed"
        )
        
        self.sgats = SGATS(
            alpha=0.4,
            beta=0.3,
            gamma=0.3,
            similarity_threshold=0.6
        )

    def _convert_sets_to_lists(self, obj):
        """Recursively converts set objects to lists in dictionaries and lists."""
        if isinstance(obj, dict):
            return {k: self._convert_sets_to_lists(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_sets_to_lists(elem) for elem in obj]
        elif isinstance(obj, set):
            return list(obj)
        else:
            return obj
    
    def process_message(self, message: dict) -> dict:
        """Reduce trajectory set using SGATS"""
        
        job_id = message['job_id']
        
        # Only process extracted jobs
        if message.get('status') != 'extracted':
            self.logger.warning(f"[{job_id}] Skipping: not extracted")
            return message
        
        trajectories_data = message.get('trajectories', [])
        
        if not trajectories_data:
            return self._error(job_id, "No trajectories to reduce")
        
        self.logger.info(f"[{job_id}] SGATS reduction on {len(trajectories_data)} trajectories")
        
        # Reconstruct Trajectory objects
        trajectories = [Trajectory.from_dict(t) for t in trajectories_data]
        
        # Apply SGATS
        reduced_set, stats = self.sgats.reduce(trajectories)
        print("SGATS OUTPUT:", len(reduced_set))
        
        self.logger.info(
            f"[{job_id}] ✅ Reduced {stats['initial_count']} → {stats['reduced_count']} "
            f"({stats['reduction_rate']*100:.1f}% reduction)"
        )
        
        # Apply the conversion to stats and original_trajectories before returning
        processed_sgats_stats = self._convert_sets_to_lists(stats)
        processed_original_trajectories = self._convert_sets_to_lists(message.get('trajectories', []))

        # Return result - KEEP ALL DATA FROM PREVIOUS PHASES
        return {
            'job_id': job_id,
            'status': JobStatus.REDUCED.value,
            'sut_info': message['sut_info'], # This should be fine (Pydantic model_dump)
            'trajectories_count': len(reduced_set),
            'trajectories': [t.to_dict() for t in reduced_set],
            # IMPORTANT: Keep original extraction data for dashboard
            'extraction_count': message.get('trajectories_count', len(trajectories_data)),
            'original_trajectories': processed_original_trajectories, # Use processed here
            'sgats_stats': processed_sgats_stats, # Use processed here
            'metadata': {
                'phase': 'sgats_reduction',
                'algorithm': 'similarity_guided_selection'
            }
        }
    
    def _error(self, job_id: str, msg: str) -> dict:
        return {
            'job_id': job_id,
            'status': JobStatus.FAILED.value,
            'error': msg,
            'phase': 'sgats'
        }

if __name__ == "__main__":
    service = SGATSService()
    service.start()