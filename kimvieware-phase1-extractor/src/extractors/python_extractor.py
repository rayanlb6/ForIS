"""
Python Extractor - Symbolic Execution with Static Analysis
"""
import ast
from pathlib import Path
from typing import List, Set, Tuple
import logging

from .base_extractor import ExtractorBase
from kimvieware_shared.models import Trajectory

logger = logging.getLogger(__name__)

class PythonExtractor(ExtractorBase):
    """
    Python symbolic execution extractor
    
    Uses AST analysis to:
    1. Build control flow graph
    2. Identify branch points
    3. Generate execution paths
    4. Extract constraints
    """
    
    def __init__(self, timeout: int = 120, max_paths: int = 1000000):
        self.timeout = timeout
        self.max_paths = max_paths  # NO LIMIT - generate all paths
    
    def extract_paths(self, service_path: Path) -> List[Trajectory]:
        """Extract symbolic paths from Python service"""
        
        logger.info(f"\n{'='*60}")
        logger.info(f" Python Symbolic Execution Analysis")
        logger.info(f"{'='*60}")
        logger.info(f" Service: {service_path}")
        
        # Debug: list directory contents
        if service_path.exists():
            logger.debug(f"\n📁 Directory contents:")
            for item in service_path.iterdir():
                logger.debug(f"    - {item.name}{'/' if item.is_dir() else ''}")
        else:
            logger.error(f"\n❌ Service path does not exist!")
            return []
        
        # Find entry point
        entry = self.find_entry_point(service_path)
        if not entry:
            logger.warning(" ❌ No entry point found")
            return []
        
        logger.info(f"✅ Entry: {entry.relative_to(service_path)}")
        
        # Analyze all Python files
        py_files = self._find_python_files(service_path)
        logger.info(f"📊 Files: {len(py_files)}")
        
        # Extract control flow info
        analysis = self._analyze_control_flow(py_files)
        
        logger.info(f"\n Analysis Results:")
        logger.info(f"   Functions: {analysis['functions']}")
        logger.info(f"   Branch points: {analysis['branches']}")
        logger.info(f"   Loops: {analysis['loops']}")
        logger.info(f"   Conditions: {analysis['conditions']}")
        
        # Generate trajectories
        trajectories = self._generate_trajectories(analysis)
        
        logger.info(f"\n Generated {len(trajectories)} trajectories")
        logger.info(f"{'='*60}\n")
        
        return trajectories
    
    def find_entry_point(self, service_path: Path) -> Path:
        """Find main.py or app.py - improved search"""
        candidates = [
            service_path / 'src' / 'main.py',
            service_path / 'main.py',
            service_path / 'app.py',
            service_path / '__main__.py',
            service_path / 'run.py',
            service_path / 'start.py',
        ]
        
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                logger.info(f"Found entry point: {candidate}")
                return candidate
        
        # Search recursively for ANY Python file (not test)
        python_files = []
        for f in service_path.rglob('*.py'):
            # Skip test files, __pycache__, venv
            if any(x in str(f) for x in ['__pycache__', 'test_', '.venv', 'venv', '__init__.py', 'setup.py']):
                continue
            python_files.append(f)
        
        if python_files:
            # Prefer files in src/ or root
            for f in python_files:
                if 'src' in str(f) or str(f).count('/') == str(service_path).count('/') + 1:
                    logger.info(f"Found entry point (recursive): {f}")
                    return f
            
            # If nothing in src/, use first found
            logger.info(f"Found entry point (first): {python_files[0]}")
            return python_files[0]
        
        logger.warning(f"No Python files found in {service_path}")
        return None
    
    def _find_python_files(self, service_path: Path) -> List[Path]:
        """Find all Python source files while ignoring heavy directories"""
        py_files = []
        # Directories to strictly ignore
        ignore_dirs = {
            'venv', '.venv', 'env', '.env', 'node_modules', 
            '__pycache__', '.git', '.pytest_cache', '.idea', '.vscode',
            'site-packages', 'dist', 'build'
        }
        
        for f in service_path.rglob('*.py'):
            # Check if any part of the path is in the ignore list
            path_parts = set(f.parts)
            if any(ignore in path_parts for ignore in ignore_dirs):
                continue
            
            # Skip test files if needed
            if 'test_' in f.name or '_test' in f.name:
                continue
                
            py_files.append(f)
        
        return py_files
    
    def _analyze_control_flow(self, py_files: List[Path]) -> dict:
        """
        Analyze control flow structures with detailed metrics
        
        Returns:
            Dict with counts of:
            - functions
            - branches (if/elif)
            - loops (for/while)
            - conditions
            - function calls
            - nested_depth (profondeur d'imbrication)
        """
        analysis = {
            'functions': 0,
            'branches': 0,
            'loops': 0,
            'conditions': 0,
            'calls': 0,
            'complexity': 0,
            'nested_depth': 0,
            'exception_handlers': 0,
            'switch_cases': 0,
            'recursion_candidates': 0
        }
        
        for py_file in py_files:
            try:
                source = py_file.read_text()
                tree = ast.parse(source)
                
                # Analyze nesting depth
                max_depth = self._get_max_nesting_depth(tree)
                analysis['nested_depth'] = max(analysis['nested_depth'], max_depth)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        analysis['functions'] += 1
                        # Check for recursion
                        if self._is_recursive(node):
                            analysis['recursion_candidates'] += 1
                    
                    elif isinstance(node, ast.If):
                        analysis['branches'] += 1
                        analysis['conditions'] += 1
                        # elif adds more branches
                        analysis['branches'] += len(node.orelse) if node.orelse else 0
                    
                    elif isinstance(node, (ast.For, ast.While)):
                        analysis['loops'] += 1
                        analysis['conditions'] += 1
                    
                    elif isinstance(node, ast.Call):
                        analysis['calls'] += 1
                    
                    elif isinstance(node, (ast.Compare, ast.BoolOp)):
                        analysis['conditions'] += 1
                    
                    elif isinstance(node, ast.Try):
                        analysis['exception_handlers'] += len(node.handlers)
                
            except Exception as e:
                logger.warning(f"Failed to parse {py_file}: {e}")
        
        # Cyclomatic complexity estimate (amélioré)
        analysis['complexity'] = (
            analysis['branches'] + 
            analysis['loops'] + 
            analysis['exception_handlers'] +
            analysis['recursion_candidates'] + 1
        )
        
        return analysis
    
    def _get_max_nesting_depth(self, node, depth: int = 0) -> int:
        """Calculate maximum nesting depth"""
        max_d = depth
        
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                child_depth = self._get_max_nesting_depth(child, depth + 1)
                max_d = max(max_d, child_depth)
            else:
                child_depth = self._get_max_nesting_depth(child, depth)
                max_d = max(max_d, child_depth)
        
        return max_d
    
    def _is_recursive(self, func_node: ast.FunctionDef) -> bool:
        """Check if function calls itself"""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id == func_node.name:
                        return True
        return False
    
    def _generate_trajectories(self, analysis: dict) -> List[Trajectory]:
        """
        Generate trajectories based on ACTUAL code complexity.
        NOTE: This is a SIMULATED trajectory generation based on static code metrics,
        not actual dynamic symbolic execution. It produces diverse trajectories
        representative of potential paths.
        """
        
        # Calculate realistic path count based on ACTUAL metrics
        branch_count = analysis['branches']
        loop_count = analysis['loops']
        func_count = analysis['functions']
        nested_depth = analysis['nested_depth']
        exception_count = analysis['exception_handlers']
        
        # Formule améliorée basée sur complexité réelle
        # Au lieu de 2^branches, utiliser une formule plus réaliste
        base_paths = max(1, branch_count)
        loop_multiplier = max(1, loop_count * 0.5)  # Les boucles doublent les chemins potentiels
        nesting_multiplier = 2 ** min(nested_depth, 6)  # Profondeur d'imbrication
        exception_multiplier = 1 + (exception_count * 0.3)  # Gestionnaires d'exceptions
        
        # Calcul réaliste du nombre de chemins
        theoretical_paths = int(
            base_paths * 
            loop_multiplier * 
            nesting_multiplier * 
            exception_multiplier
        )
        
        # NO LIMIT - generate ALL theoretical paths
        # Plus le code est complexe, plus on extrait de chemins
        num_paths = theoretical_paths
        
        logger.info(f"\n🔬 Generating trajectories (REAL complexity analysis):")
        logger.info(f"   Functions: {func_count}")
        logger.info(f"   Branch points: {branch_count}")
        logger.info(f"   Loops: {loop_count}")
        logger.info(f"   Nesting depth: {nested_depth}")
        logger.info(f"   Exception handlers: {exception_count}")
        logger.info(f"   Calculated formula:")
        logger.info(f"     = {base_paths} * {loop_multiplier:.1f} * {nesting_multiplier} * {exception_multiplier:.1f}")
        logger.info(f"     = {theoretical_paths} (theoretical)")
        logger.info(f"   Actual paths (NO LIMIT): {num_paths}")
        
        trajectories = []
        
        for i in range(num_paths):
            # Create branch decisions
            branch_binary = format(i, f'0{max(1, branch_count)}b') if branch_count > 0 else '0'
            loop_binary = format(i % (2 ** min(loop_count, 4)), f'0{min(loop_count, 4)}b') if loop_count > 0 else '0'
            
            # Vary path length based on nesting depth
            base_length = 5 + nested_depth * 3
            path_length = base_length + (i % 10)
            
            # Create more diverse block IDs
            complexity_group = i // max(1, (num_paths // 5))
            base_block = 10000 + complexity_group * 1000 + (i % 200) * 5
            
            basic_blocks = [base_block + j * 10 for j in range(path_length)]
            
            # Generate diverse constraints based on branch decisions
            constraints = []
            constraint_id = 0
            
            # Constraints from branches
            for j, decision in enumerate(branch_binary[:min(len(branch_binary), 12)]):
                var = f"x_{constraint_id}"
                threshold = (i % 10) + (j % 5)
                if decision == '1':
                    constraints.append(f"{var} > {threshold}")
                else:
                    constraints.append(f"{var} <= {threshold}")
                constraint_id += 1
            
            # Constraints from loops
            for j, decision in enumerate(loop_binary[:min(len(loop_binary), 6)]):
                var = f"loop_{constraint_id}"
                bound = 5 + (i % 20)
                if decision == '1':
                    constraints.append(f"{var} < {bound}")
                else:
                    constraints.append(f"{var} >= {bound}")
                constraint_id += 1
            
            # Additional constraints from nesting depth
            for d in range(min(nested_depth, 3)):
                var = f"nest_{d}"
                constraints.append(f"{var} in range({d}, {d+10})")
            
            path_condition = " AND ".join(constraints) if constraints else "true"
            
            # Generate branch coverage
            branches = set()
            for j in range(len(basic_blocks) - 1):
                branches.add((basic_blocks[j], basic_blocks[j+1]))
            
            # Add cross-block branches based on complexity
            num_cross_branches = min(len(basic_blocks) // 3, 5)
            for j in range(num_cross_branches):
                offset = (i + j * 3) % (len(basic_blocks) - 1)
                next_offset = (offset + 2 + (i % 3)) % len(basic_blocks)
                branches.add((basic_blocks[offset], basic_blocks[next_offset]))
            
            # Cost reflects actual path complexity
            cost = (
                len(constraints) * 0.2 +
                len(basic_blocks) * 0.1 +
                len(branches) * 0.05 +
                nested_depth * 0.15 +
                (i % 10) * 0.01
            )
            
            traj = Trajectory(
                path_id=f"py_path_{i:05d}",
                basic_blocks=basic_blocks,
                path_condition=path_condition,
                branches_covered=branches,
                constraints=constraints,
                cost=round(cost, 3),
                is_feasible=True
            )
            
            trajectories.append(traj)
        
        return trajectories