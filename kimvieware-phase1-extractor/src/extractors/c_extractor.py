"""
C/C++ Trajectory Extractor using Clang/LLVM
Uses libclang to parse C/C++ AST and extract execution paths
"""
import os
import logging
from pathlib import Path
from typing import List, Set
from dataclasses import dataclass

import clang.cindex
from clang.cindex import Config, Index, CursorKind

# Configure libclang - Try multiple possible paths
libclang_paths = [
    '/usr/lib/llvm-18/lib/libclang.so',
    '/usr/lib/llvm-18/lib/libclang-18.so',
    '/usr/lib/x86_64-linux-gnu/libclang-18.so',
    '/usr/lib/llvm-18/lib/libclang-18.1.3.so',
    '/usr/lib/x86_64-linux-gnu/libclang-18.so.1',
    '/usr/lib/llvm-18/lib/libclang.so.1',
]

libclang_set = False
for path in libclang_paths:
    if os.path.exists(path):
        try:
            Config.set_library_file(path)
            libclang_set = True
            logging.info(f"✅ Using libclang: {path}")
            break
        except Exception as e:
            continue

if not libclang_set:
    logging.warning("⚠️  Could not find libclang, using system default")

from kimvieware_shared.models import Trajectory

logger = logging.getLogger(__name__)


@dataclass
class CFGNode:
    """Control Flow Graph Node"""
    node_id: int
    kind: str
    location: str
    children: List[int]
    is_branch: bool = False


class CExtractor:
    """
    Extract execution paths from C/C++ code using Clang AST
    
    Symbolic Execution Strategy:
    1. Parse C/C++ file with Clang
    2. Build Control Flow Graph (CFG)
    3. Identify branch points (if, while, for, switch)
    4. Generate paths through CFG
    5. Extract constraints from conditions
    """
    
    def __init__(self, max_paths: int = 100):
        self.max_paths = max_paths
        self.index = Index.create()
        self.cfg_nodes = []
        self.next_node_id = 0
        self.paths = []
        
        # Branch kinds that create paths
        self.branch_kinds = {
            CursorKind.IF_STMT,
            CursorKind.WHILE_STMT,
            CursorKind.FOR_STMT,
            CursorKind.DO_STMT,
            CursorKind.SWITCH_STMT,
            CursorKind.CONDITIONAL_OPERATOR,
            CursorKind.CASE_STMT,
        }
    
    def extract_paths(self, source_dir: Path) -> List[Trajectory]:
        """
        Extract all execution paths from C/C++ source directory
        
        Args:
            source_dir: Directory containing .c/.cpp files
            
        Returns:
            List of Trajectory objects
        """
        logger.info(f"🔍 Extracting C/C++ paths from {source_dir}")
        
        # Find all C/C++ files
        c_files = list(source_dir.rglob("*.c"))
        cpp_files = list(source_dir.rglob("*.cpp"))
        h_files = list(source_dir.rglob("*.h"))
        
        all_files = c_files + cpp_files
        
        if not all_files:
            logger.warning("No C/C++ source files found")
            return []
        
        logger.info(f"Found {len(c_files)} .c, {len(cpp_files)} .cpp, {len(h_files)} .h files")
        
        all_trajectories = []
        
        # Process each source file
        for source_file in all_files:
            logger.info(f"Processing {source_file.name}...")
            
            try:
                trajectories = self._extract_from_file(source_file)
                all_trajectories.extend(trajectories)
                logger.info(f"  → {len(trajectories)} paths extracted")
                
            except Exception as e:
                logger.error(f"Error processing {source_file}: {e}")
                continue
        
        logger.info(f"✅ Total paths extracted: {len(all_trajectories)}")
        
        # Limit to max_paths
        if len(all_trajectories) > self.max_paths:
            logger.info(f"Limiting to {self.max_paths} paths")
            all_trajectories = all_trajectories[:self.max_paths]
        
        return all_trajectories
    
    def _extract_from_file(self, file_path: Path) -> List[Trajectory]:
        """Extract paths from a single C/C++ file"""
        
        # Parse with Clang
        tu = self.index.parse(
            str(file_path),
            args=['-std=c11', '-Wall'],
            options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
        )
        
        if not tu:
            logger.error(f"Failed to parse {file_path}")
            return []
        
        # Check for parse errors
        diagnostics = list(tu.diagnostics)
        errors = [d for d in diagnostics if d.severity >= 3]  # Error or Fatal
        
        if errors:
            logger.warning(f"Parse errors in {file_path}:")
            for err in errors[:3]:  # Show first 3
                logger.warning(f"  {err}")
        
        trajectories = []
        
        # Find all function definitions
        functions = self._find_functions(tu.cursor)
        
        logger.info(f"  Found {len(functions)} functions")
        
        # Extract paths from each function
        for func in functions:
            func_name = func.spelling
            logger.debug(f"    Analyzing function: {func_name}")
            
            # Build CFG for function
            cfg = self._build_cfg(func)
            
            # Generate paths through CFG
            func_paths = self._generate_paths_from_cfg(cfg, func_name)
            
            # Convert to Trajectory objects
            for i, path in enumerate(func_paths):
                traj = self._path_to_trajectory(path, func_name, i)
                trajectories.append(traj)
        
        return trajectories
    
    def _find_functions(self, cursor) -> List:
        """Find all function definitions in AST"""
        functions = []
        
        def visit(node):
            if node.kind == CursorKind.FUNCTION_DECL:
                # Only include definitions (not declarations)
                if node.is_definition():
                    functions.append(node)
            
            # Recurse
            for child in node.get_children():
                visit(child)
        
        visit(cursor)
        return functions
    
    def _build_cfg(self, func_cursor) -> List[CFGNode]:
        """
        Build Control Flow Graph for a function
        
        Returns list of CFG nodes
        """
        cfg = []
        node_map = {}  # cursor -> node_id
        
        self.next_node_id = 0
        
        def create_node(cursor, is_branch=False):
            """Create CFG node for cursor"""
            node_id = self.next_node_id
            self.next_node_id += 1
            
            node = CFGNode(
                node_id=node_id,
                kind=cursor.kind.name,
                location=f"{cursor.location.line}:{cursor.location.column}",
                children=[],
                is_branch=is_branch
            )
            
            cfg.append(node)
            node_map[cursor.hash] = node_id
            return node_id
        
        def visit(cursor, parent_id=None):
            """Build CFG recursively"""
            
            # Create node for this cursor
            is_branch = cursor.kind in self.branch_kinds
            current_id = create_node(cursor, is_branch)
            
            # Link to parent
            if parent_id is not None:
                cfg[parent_id].children.append(current_id)
            
            # Special handling for branch statements
            if cursor.kind == CursorKind.IF_STMT:
                children = list(cursor.get_children())
                if len(children) >= 2:
                    # Condition
                    visit(children[0], current_id)
                    # Then branch
                    visit(children[1], current_id)
                    # Else branch (if exists)
                    if len(children) >= 3:
                        visit(children[2], current_id)
            
            elif cursor.kind in {CursorKind.WHILE_STMT, CursorKind.FOR_STMT}:
                children = list(cursor.get_children())
                for child in children:
                    visit(child, current_id)
            
            elif cursor.kind == CursorKind.SWITCH_STMT:
                children = list(cursor.get_children())
                for child in children:
                    visit(child, current_id)
            
            else:
                # Regular statement - visit children
                for child in cursor.get_children():
                    visit(child, current_id)
            
            return current_id
        
        # Build CFG starting from function body
        visit(func_cursor)
        
        return cfg
    
    def _generate_paths_from_cfg(self, cfg: List[CFGNode], func_name: str) -> List[List[CFGNode]]:
        """
        Generate all paths through CFG using DFS
        
        Returns list of paths (each path is list of nodes)
        """
        if not cfg:
            return []
        
        paths = []
        max_depth = 50  # Prevent infinite loops
        
        def dfs(node_id: int, current_path: List[int], visited: Set[int], depth: int):
            """DFS to find all paths"""
            
            if depth > max_depth:
                return
            
            if len(paths) >= self.max_paths:
                return
            
            node = cfg[node_id]
            current_path.append(node_id)
            
            # If no children, this is an end node - save path
            if not node.children:
                paths.append(current_path.copy())
                current_path.pop()
                return
            
            # For branch nodes, explore all branches
            if node.is_branch:
                for child_id in node.children:
                    if child_id not in visited:
                        new_visited = visited.copy()
                        new_visited.add(child_id)
                        dfs(child_id, current_path, new_visited, depth + 1)
            else:
                # Non-branch: just continue
                for child_id in node.children:
                    if child_id not in visited:
                        new_visited = visited.copy()
                        new_visited.add(node_id)
                        dfs(child_id, current_path, new_visited, depth + 1)
            
            current_path.pop()
        
        # Start DFS from root (node 0)
        dfs(0, [], set(), 0)
        
        # Convert node IDs to node objects
        result_paths = []
        for path_ids in paths:
            path_nodes = [cfg[nid] for nid in path_ids]
            result_paths.append(path_nodes)
        
        return result_paths
    
    def _path_to_trajectory(self, path: List[CFGNode], func_name: str, path_idx: int) -> Trajectory:
        """
        Convert a CFG path to a Trajectory object
        
        Args:
            path: List of CFG nodes
            func_name: Function name
            path_idx: Path index within function
            
        Returns:
            Trajectory object
        """
        
        # Extract basic blocks (node IDs)
        basic_blocks = [node.node_id for node in path]
        
        # Extract branches covered
        branches = set()
        for i in range(len(path) - 1):
            if path[i].is_branch:
                # Branch from node i to node i+1
                branches.add((path[i].node_id, path[i+1].node_id))
        
        # Extract path condition (simplified)
        path_condition = f"{func_name}_path_{path_idx}"
        
        # Extract constraints from branch nodes
        constraints = []
        for node in path:
            if node.is_branch:
                constraints.append(f"{node.kind}@{node.location}")
        
        # Calculate cost (path length)
        cost = len(path)
        
        # Create trajectory
        return Trajectory(
            path_id=f"c_{func_name}_path_{path_idx:03d}",
            basic_blocks=basic_blocks,
            path_condition=path_condition,
            branches_covered=branches,
            constraints=constraints,
            cost=float(cost),
            is_feasible=True  # Assume feasible (would need solver to verify)
        )


def extract_c_trajectories(source_dir: Path, max_paths: int = 100) -> List[Trajectory]:
    """
    Convenience function to extract trajectories from C/C++ code
    
    Args:
        source_dir: Directory containing C/C++ source files
        max_paths: Maximum number of paths to extract
        
    Returns:
        List of Trajectory objects
    """
    extractor = CExtractor(max_paths=max_paths)
    return extractor.extract_paths(source_dir)