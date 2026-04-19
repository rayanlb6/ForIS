"""
Java Trajectory Extractor using javalang
Parses Java AST and extracts execution paths
"""
import javalang
from pathlib import Path
from typing import List, Set, Tuple
import logging
from dataclasses import dataclass, field

from kimvieware_shared.models import Trajectory

logger = logging.getLogger(__name__)


@dataclass
class CFGNode:
    """Control Flow Graph Node for Java"""
    node_id: int
    kind: str
    location: str
    children: List[int] = field(default_factory=list)
    is_branch: bool = False


class JavaExtractor:
    """
    Extract execution paths from Java code using javalang
    
    Strategy:
    1. Parse Java files with javalang
    2. Build Control Flow Graph (CFG)
    3. Identify branch points (if, while, for, switch, try-catch)
    4. Generate paths through CFG
    5. Extract constraints from conditions
    """
    
    BRANCH_TYPES = {
        'IfStatement',
        'WhileStatement',
        'ForStatement',
        'DoStatement',
        'SwitchStatement',
        'TryStatement',
        'ConditionalExpression'
    }
    
    def __init__(self, max_paths: int = 100):
        self.max_paths = max_paths
        self.cfg_nodes = []
        self.next_node_id = 0
    
    def extract_paths(self, source_dir: Path) -> List[Trajectory]:
        """
        Extract all execution paths from Java source directory
        
        Args:
            source_dir: Directory containing .java files
            
        Returns:
            List of Trajectory objects
        """
        logger.info(f"🔍 Extracting Java paths from {source_dir}")
        
        # Find all Java files
        java_files = list(source_dir.rglob("*.java"))
        
        if not java_files:
            logger.warning("No Java source files found")
            return []
        
        logger.info(f"Found {len(java_files)} .java files")
        
        all_trajectories = []
        
        # Process each Java file
        for java_file in java_files:
            logger.info(f"Processing {java_file.name}...")
            
            try:
                trajectories = self._extract_from_file(java_file)
                all_trajectories.extend(trajectories)
                logger.info(f"  → {len(trajectories)} paths extracted")
                
            except Exception as e:
                logger.error(f"Error processing {java_file}: {e}")
                continue
        
        logger.info(f"✅ Total paths extracted: {len(all_trajectories)}")
        
        # Limit to max_paths
        if len(all_trajectories) > self.max_paths:
            logger.info(f"Limiting to {self.max_paths} paths")
            all_trajectories = all_trajectories[:self.max_paths]
        
        return all_trajectories
    
    def _extract_from_file(self, file_path: Path) -> List[Trajectory]:
        """Extract paths from a single Java file"""
        
        # Parse Java file
        try:
            code = file_path.read_text(encoding='utf-8')
            tree = javalang.parse.parse(code)
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return []
        
        trajectories = []
        
        # Find all method declarations
        methods = []
        for path, node in tree.filter(javalang.tree.MethodDeclaration):
            methods.append(node)
        
        logger.info(f"  Found {len(methods)} methods")
        
        # Extract paths from each method
        for method in methods:
            method_name = method.name
            logger.debug(f"    Analyzing method: {method_name}")
            
            # Build CFG for method
            cfg = self._build_cfg(method)
            
            # Generate paths through CFG
            method_paths = self._generate_paths_from_cfg(cfg, method_name)
            
            # Convert to Trajectory objects
            for i, path in enumerate(method_paths):
                traj = self._path_to_trajectory(path, method_name, i)
                trajectories.append(traj)
        
        return trajectories
    
    def _build_cfg(self, method_node) -> List[CFGNode]:
        """Build Control Flow Graph for a Java method"""
        
        cfg = []
        self.next_node_id = 0
        
        def create_node(node, is_branch=False):
            """Create CFG node"""
            node_id = self.next_node_id
            self.next_node_id += 1
            
            kind = type(node).__name__
            location = f"{getattr(node, 'position', 'unknown')}"
            
            cfg_node = CFGNode(
                node_id=node_id,
                kind=kind,
                location=location,
                children=[],
                is_branch=is_branch
            )
            
            cfg.append(cfg_node)
            return node_id
        
        def visit(node, parent_id=None):
            """Build CFG recursively"""
            
            if node is None:
                return None
            
            node_type = type(node).__name__
            is_branch = node_type in self.BRANCH_TYPES
            
            current_id = create_node(node, is_branch)
            
            # Link to parent
            if parent_id is not None:
                cfg[parent_id].children.append(current_id)
            
            # Special handling for branch statements
            if node_type == 'IfStatement':
                # Condition
                if hasattr(node, 'condition'):
                    visit(node.condition, current_id)
                # Then statement
                if hasattr(node, 'then_statement'):
                    visit(node.then_statement, current_id)
                # Else statement
                if hasattr(node, 'else_statement') and node.else_statement:
                    visit(node.else_statement, current_id)
            
            elif node_type in ['WhileStatement', 'ForStatement', 'DoStatement']:
                if hasattr(node, 'body'):
                    visit(node.body, current_id)
            
            elif node_type == 'SwitchStatement':
                if hasattr(node, 'cases'):
                    for case in node.cases:
                        visit(case, current_id)
            
            elif node_type == 'TryStatement':
                if hasattr(node, 'block'):
                    visit(node.block, current_id)
                if hasattr(node, 'catches'):
                    for catch in node.catches:
                        visit(catch, current_id)
            
            elif node_type == 'BlockStatement':
                if hasattr(node, 'statements'):
                    for stmt in node.statements:
                        visit(stmt, current_id)
            
            else:
                # Visit children (generic)
                if hasattr(node, 'children'):
                    for child in node.children:
                        if child:
                            visit(child, current_id)
            
            return current_id
        
        # Build CFG starting from method body
        if hasattr(method_node, 'body') and method_node.body:
            visit(method_node.body)
        
        return cfg
    
    def _generate_paths_from_cfg(self, cfg: List[CFGNode], method_name: str) -> List[List[CFGNode]]:
        """Generate all paths through CFG using DFS"""
        
        if not cfg:
            return []
        
        paths = []
        max_depth = 50
        
        def dfs(node_id: int, current_path: List[int], visited: Set[int], depth: int):
            if depth > max_depth or len(paths) >= self.max_paths:
                return
            
            node = cfg[node_id]
            current_path.append(node_id)
            
            if not node.children:
                paths.append(current_path.copy())
                current_path.pop()
                return
            
            if node.is_branch:
                for child_id in node.children:
                    if child_id not in visited:
                        new_visited = visited.copy()
                        new_visited.add(child_id)
                        dfs(child_id, current_path, new_visited, depth + 1)
            else:
                for child_id in node.children:
                    if child_id not in visited:
                        new_visited = visited.copy()
                        new_visited.add(node_id)
                        dfs(child_id, current_path, new_visited, depth + 1)
            
            current_path.pop()
        
        dfs(0, [], set(), 0)
        
        result_paths = []
        for path_ids in paths:
            path_nodes = [cfg[nid] for nid in path_ids]
            result_paths.append(path_nodes)
        
        return result_paths
    
    def _path_to_trajectory(self, path: List[CFGNode], method_name: str, path_idx: int) -> Trajectory:
        """Convert CFG path to Trajectory object"""
        
        basic_blocks = [node.node_id for node in path]
        
        branches = set()
        for i in range(len(path) - 1):
            if path[i].is_branch:
                branches.add((path[i].node_id, path[i+1].node_id))
        
        path_condition = f"{method_name}_path_{path_idx}"
        
        constraints = []
        for node in path:
            if node.is_branch:
                constraints.append(f"{node.kind}@{node.location}")
        
        cost = len(path)
        
        return Trajectory(
            path_id=f"java_{method_name}_path_{path_idx:03d}",
            basic_blocks=basic_blocks,
            path_condition=path_condition,
            branches_covered=branches,
            constraints=constraints,
            cost=float(cost),
            is_feasible=True
        )


def extract_java_trajectories(source_dir: Path, max_paths: int = 100) -> List[Trajectory]:
    """Convenience function to extract trajectories from Java code"""
    extractor = JavaExtractor(max_paths=max_paths)
    return extractor.extract_paths(source_dir)
