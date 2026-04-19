"""
Phase 3: EvoPath-GA Optimization Service

Consumes: reduction.completed
Produces: optimization.completed
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'kimvieware-shared' / 'src'))

from kimvieware_shared import MicroserviceBase, JobStatus, Trajectory
from algorithms.evopath_ga import EvoPathGA

class EvoPathService(MicroserviceBase):
    """Phase 3: Genetic Algorithm Optimization"""
    
    def __init__(self):
        super().__init__(
            service_name="Phase3_EvoPath",
            input_queue="reduction.completed",
            output_queue="optimization.completed"
        )
        
        self.evopath = EvoPathGA(
            w1=0.5,  # Coverage weight
            w2=0.3,  # Cost weight
            w3=0.2,  # Size weight
            population_size=50,
            generations=100,
            crossover_prob=0.7,
            mutation_prob=0.2
        )
    
    def process_message(self, message: dict) -> dict:
        """Optimize trajectory set using GA"""
        
        job_id = message['job_id']
        
        # Only process reduced jobs
        if message.get('status') != 'reduced':
            self.logger.warning(f"[{job_id}] Skipping: not reduced")
            return message
        
        trajectories_data = message.get('trajectories', [])
        
        if not trajectories_data:
            return self._error(job_id, "No trajectories to optimize")
        
        self.logger.info(f"[{job_id}] EvoPath-GA optimization on {len(trajectories_data)} trajectories")
        
        # Reconstruct Trajectory objects
        trajectories = [Trajectory.from_dict(t) for t in trajectories_data]
        
        # Apply EvoPath-GA
        optimized_set, stats = self.evopath.optimize(trajectories)
        
        self.logger.info(
            f"[{job_id}] ✅ Optimized {stats['original_count']} → {stats['optimized_count']} "
            f"({stats['size_reduction']*100:.1f}% reduction, "
            f"({stats['cost_reduction']*100:.1f}% cost saved)"
        )
        
        # Return result - KEEP ALL DATA FROM PREVIOUS PHASES
        return {
            'job_id': job_id,
            'status': JobStatus.OPTIMIZED.value,
            'sut_info': message['sut_info'],
            'trajectories_count': len(optimized_set),
            'trajectories': [t.to_dict() for t in optimized_set],
            # IMPORTANT: Keep ALL previous phase data for dashboard
            'extraction_count': message.get('extraction_count', message.get('trajectories_count')),
            'original_trajectories': message.get('original_trajectories', message.get('trajectories', [])),
            'sgats_stats': message.get('sgats_stats'),
            'evopath_stats': stats,
            'metadata': {
                'phase': 'evopath_optimization',
                'algorithm': 'genetic_algorithm'
            }
        }
    
    def _error(self, job_id: str, msg: str) -> dict:
        return {
            'job_id': job_id,
            'status': JobStatus.FAILED.value,
            'error': msg,
            'phase': 'evopath'
        }

if __name__ == "__main__":
    service = EvoPathService()
    service.start()
