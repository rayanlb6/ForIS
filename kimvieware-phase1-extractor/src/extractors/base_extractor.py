"""
Base Extractor Interface
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from kimvieware_shared.models import Trajectory

class ExtractorBase(ABC):
    """Base class for all language extractors"""
    
    @abstractmethod
    def extract_paths(self, service_path: Path) -> List[Trajectory]:
        """
        Extract symbolic execution paths from service
        
        Args:
            service_path: Path to extracted service directory
            
        Returns:
            List of Trajectory objects with path info
        """
        pass
    
    @abstractmethod
    def find_entry_point(self, service_path: Path) -> Path:
        """Find main entry point of the service"""
        pass
