"""
JavaScript/TypeScript Trajectory Extractor using Acorn
Calls Node.js + acorn via subprocess to parse JS/TS AST
"""
import json
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import List, Set
import logging
from dataclasses import dataclass, field

from kimvieware_shared.models import Trajectory

logger = logging.getLogger(__name__)


@dataclass
class CFGNode:
    """Control Flow Graph Node for JavaScript"""
    node_id: int
    kind: str
    location: str
    children: List[int] = field(default_factory=list)
    is_branch: bool = False


class JSExtractor:
    """
    Extract execution paths from JavaScript/TypeScript using Acorn.

    Strategy:
    1. Write a temporary Node.js script that uses acorn to parse the file
    2. Call it via subprocess → get AST as JSON
    3. Build CFG from AST nodes
    4. DFS to generate all paths
    5. Convert to Trajectory objects
    """

    # AST node types that create branches
    BRANCH_TYPES = {
        'IfStatement',
        'WhileStatement',
        'ForStatement',
        'ForInStatement',
        'ForOfStatement',
        'DoWhileStatement',
        'SwitchStatement',
        'ConditionalExpression',
        'TryStatement',
        'CatchClause',
        'LogicalExpression',    # && / || short-circuit
    }

    # Node.js script template — acorn parses the file and prints AST as JSON
    NODE_SCRIPT = textwrap.dedent("""
        const acorn = require('acorn');
        const fs = require('fs');

        const filePath = process.argv[2];
        const isTS = filePath.endsWith('.ts') || filePath.endsWith('.mts');

        let source;
        try {
            source = fs.readFileSync(filePath, 'utf8');
        } catch(e) {
            process.stderr.write('READ_ERROR: ' + e.message + '\\n');
            process.exit(1);
        }

        // Strip TypeScript type annotations for .ts files
        // (acorn doesn't support TS natively — we strip types before parsing)
        if (isTS) {
            source = source
                .replace(/:\\s*[\\w<>\\[\\]|&,\\s]+(?=[,)=;{])/g, '')  // param types
                .replace(/<[^>]+>/g, '')                                 // generics
                .replace(/as\\s+\\w+/g, '')                              // type assertions
                .replace(/:\\s*\\w+\\s*(?=\\{)/g, '');                  // return types
        }

        const options = {
            ecmaVersion: 2022,
            sourceType: 'module',   // handles import/export (.mjs)
            locations: true,        // include line/col info
            allowHashBang: true,
            allowImportExportEverywhere: true,
        };

        try {
            const ast = acorn.parse(source, options);
            process.stdout.write(JSON.stringify(ast));
        } catch(e) {
            process.stderr.write('PARSE_ERROR: ' + e.message + '\\n');
            process.exit(1);
        }
    """)

    def __init__(self, max_paths: int = 100):
        self.max_paths = max_paths
        self.next_node_id = 0
        self._check_node_and_acorn()

    # ------------------------------------------------------------------
    # Startup check
    # ------------------------------------------------------------------

    def _check_node_and_acorn(self):
        """Verify that node and acorn are available"""
        # Check node
        try:
            result = subprocess.run(
                ['node', '--version'],
                capture_output=True, text=True, timeout=5
            )
            logger.info(f"✅ Node.js found: {result.stdout.strip()}")
        except FileNotFoundError:
            raise RuntimeError("❌ Node.js not found. Install it: https://nodejs.org")

        # Check acorn
        try:
            result = subprocess.run(
                ['node', '-e', 'require("acorn"); console.log("ok")'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "❌ acorn not found. Install it: npm install -g acorn  "
                    "or: npm install acorn  (in your project)"
                )
            logger.info("✅ acorn available")
        except FileNotFoundError:
            raise RuntimeError("❌ Node.js not found")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def extract_paths(self, source_dir: Path) -> List[Trajectory]:
        """
        Extract all execution paths from JS/TS source directory.

        Args:
            source_dir: Directory containing .js / .mjs / .ts files

        Returns:
            List of Trajectory objects
        """
        logger.info(f"🔍 Extracting JS/TS paths from {source_dir}")

        # Collect target files
        js_files  = list(source_dir.rglob("*.js"))
        mjs_files = list(source_dir.rglob("*.mjs"))
        ts_files  = list(source_dir.rglob("*.ts"))

        # Ignore node_modules, dist, build, test files
        def _keep(f: Path) -> bool:
            bad = {'node_modules', 'dist', 'build', '.git',
                   '__pycache__', '.venv', 'coverage'}
            return (
                not any(p in f.parts for p in bad)
                and 'test' not in f.stem.lower()
                and '.min.' not in f.name
            )

        all_files = [f for f in js_files + mjs_files + ts_files if _keep(f)]

        if not all_files:
            logger.warning("No JS/TS source files found")
            return []

        logger.info(
            f"Found {len(js_files)} .js, "
            f"{len(mjs_files)} .mjs, "
            f"{len(ts_files)} .ts files "
            f"({len(all_files)} after filtering)"
        )

        all_trajectories = []

        for source_file in all_files:
            logger.info(f"Processing {source_file.name}...")
            try:
                trajectories = self._extract_from_file(source_file)
                all_trajectories.extend(trajectories)
                logger.info(f"  → {len(trajectories)} paths extracted")
            except Exception as e:
                logger.error(f"Error processing {source_file}: {e}")
                continue

        logger.info(f"✅ Total JS/TS paths extracted: {len(all_trajectories)}")

        if len(all_trajectories) > self.max_paths:
            logger.info(f"Limiting to {self.max_paths} paths")
            all_trajectories = all_trajectories[:self.max_paths]

        return all_trajectories

    # ------------------------------------------------------------------
    # AST → JSON via subprocess
    # ------------------------------------------------------------------

    def _get_ast(self, file_path: Path) -> dict | None:
        """
        Run the Node.js acorn script on file_path.
        Returns parsed AST dict, or None on failure.
        """
        # Write Node script to a temp file
        with tempfile.NamedTemporaryFile(
            suffix='.js', mode='w', delete=False, encoding='utf-8'
        ) as tmp:
            tmp.write(self.NODE_SCRIPT)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ['node', tmp_path, str(file_path)],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.warning(
                    f"acorn error on {file_path.name}: "
                    f"{result.stderr.strip()[:200]}"
                )
                return None

            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout parsing {file_path.name}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from acorn for {file_path.name}: {e}")
            return None
        finally:
            Path(tmp_path).unlink(missing_ok=True)  # clean up temp file

    # ------------------------------------------------------------------
    # File-level extraction
    # ------------------------------------------------------------------

    def _extract_from_file(self, file_path: Path) -> List[Trajectory]:
        """Extract paths from a single JS/TS file"""

        ast = self._get_ast(file_path)
        if ast is None:
            return []

        trajectories = []

        # Collect all function nodes from the AST
        functions = self._find_functions(ast)
        logger.info(f"  Found {len(functions)} functions")

        for func in functions:
            func_name = self._get_func_name(func)
            logger.debug(f"    Analyzing: {func_name}")

            cfg = self._build_cfg(func)
            paths = self._generate_paths_from_cfg(cfg, func_name)

            for i, path in enumerate(paths):
                traj = self._path_to_trajectory(path, func_name, i)
                trajectories.append(traj)

        return trajectories

    # ------------------------------------------------------------------
    # AST traversal helpers
    # ------------------------------------------------------------------

    def _find_functions(self, node: dict) -> List[dict]:
        """
        Recursively find all function nodes in the AST.
        Covers: FunctionDeclaration, FunctionExpression, ArrowFunctionExpression
        """
        results = []
        func_types = {
            'FunctionDeclaration',
            'FunctionExpression',
            'ArrowFunctionExpression',
        }

        def walk(n):
            if not isinstance(n, dict):
                return
            if n.get('type') in func_types:
                results.append(n)
            for v in n.values():
                if isinstance(v, dict):
                    walk(v)
                elif isinstance(v, list):
                    for item in v:
                        walk(item)

        walk(node)
        return results

    def _get_func_name(self, func_node: dict) -> str:
        """Extract function name (or 'anonymous' for arrow/unnamed functions)"""
        node_type = func_node.get('type', '')

        if node_type == 'FunctionDeclaration':
            id_node = func_node.get('id')
            if id_node:
                return id_node.get('name', 'anonymous')

        if node_type == 'FunctionExpression':
            id_node = func_node.get('id')
            if id_node:
                return id_node.get('name', 'anonymous')

        return 'anonymous'

    def _get_location(self, node: dict) -> str:
        """Extract line:col from acorn location info"""
        loc = node.get('loc')
        if loc and 'start' in loc:
            return f"{loc['start']['line']}:{loc['start']['column']}"
        return 'unknown'

    # ------------------------------------------------------------------
    # CFG construction
    # ------------------------------------------------------------------

    def _build_cfg(self, func_node: dict) -> List[CFGNode]:
        """Build Control Flow Graph from a function's AST node"""
        cfg: List[CFGNode] = []
        self.next_node_id = 0

        def create_node(ast_node: dict, is_branch: bool = False) -> int:
            node_id = self.next_node_id
            self.next_node_id += 1
            cfg.append(CFGNode(
                node_id=node_id,
                kind=ast_node.get('type', 'Unknown'),
                location=self._get_location(ast_node),
                children=[],
                is_branch=is_branch,
            ))
            return node_id

        def link(parent_id: int, child_id: int):
            cfg[parent_id].children.append(child_id)

        def visit(node, parent_id=None) -> int | None:
            if not isinstance(node, dict):
                return None

            node_type = node.get('type', '')
            is_branch = node_type in self.BRANCH_TYPES
            current_id = create_node(node, is_branch)

            if parent_id is not None:
                link(parent_id, current_id)

            # --- Structured traversal per node type ---

            if node_type == 'IfStatement':
                # test → consequent → [alternate]
                visit(node.get('test', {}), current_id)
                visit(node.get('consequent', {}), current_id)
                if node.get('alternate'):
                    visit(node['alternate'], current_id)

            elif node_type in ('WhileStatement', 'DoWhileStatement'):
                visit(node.get('test', {}), current_id)
                visit(node.get('body', {}), current_id)

            elif node_type == 'ForStatement':
                for key in ('init', 'test', 'update', 'body'):
                    if node.get(key):
                        visit(node[key], current_id)

            elif node_type in ('ForInStatement', 'ForOfStatement'):
                visit(node.get('left', {}), current_id)
                visit(node.get('right', {}), current_id)
                visit(node.get('body', {}), current_id)

            elif node_type == 'SwitchStatement':
                visit(node.get('discriminant', {}), current_id)
                for case in node.get('cases', []):
                    visit(case, current_id)

            elif node_type == 'TryStatement':
                visit(node.get('block', {}), current_id)
                if node.get('handler'):
                    visit(node['handler'], current_id)
                if node.get('finalizer'):
                    visit(node['finalizer'], current_id)

            elif node_type == 'BlockStatement':
                for stmt in node.get('body', []):
                    visit(stmt, current_id)

            elif node_type in (
                'FunctionDeclaration', 'FunctionExpression',
                'ArrowFunctionExpression'
            ):
                # Visit body only (params are not control-flow-relevant here)
                body = node.get('body')
                if body:
                    visit(body, current_id)

            else:
                # Generic: visit all dict/list children
                for v in node.values():
                    if isinstance(v, dict) and v.get('type'):
                        visit(v, current_id)
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict) and item.get('type'):
                                visit(item, current_id)

            return current_id

        # Start from function body
        body = func_node.get('body')
        if body:
            visit(body)

        return cfg

    # ------------------------------------------------------------------
    # DFS path generation (identical logic to C/Java extractors)
    # ------------------------------------------------------------------

    def _generate_paths_from_cfg(
        self, cfg: List[CFGNode], func_name: str
    ) -> List[List[CFGNode]]:
        """Generate all paths through CFG using DFS"""
        if not cfg:
            return []

        paths: List[List[int]] = []
        max_depth = 50

        def dfs(node_id: int, current_path: List[int],
                visited: Set[int], depth: int):
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
                        dfs(child_id, current_path,
                            visited | {child_id}, depth + 1)
            else:
                for child_id in node.children:
                    if child_id not in visited:
                        dfs(child_id, current_path,
                            visited | {node_id}, depth + 1)

            current_path.pop()

        dfs(0, [], set(), 0)

        return [[cfg[nid] for nid in path] for path in paths]

    # ------------------------------------------------------------------
    # Path → Trajectory
    # ------------------------------------------------------------------

    def _path_to_trajectory(
        self, path: List[CFGNode], func_name: str, path_idx: int
    ) -> Trajectory:
        """Convert a CFG path to a Trajectory object"""
        basic_blocks = [node.node_id for node in path]

        branches: Set[tuple] = set()
        for i in range(len(path) - 1):
            if path[i].is_branch:
                branches.add((path[i].node_id, path[i + 1].node_id))

        constraints = [
            f"{node.kind}@{node.location}"
            for node in path if node.is_branch
        ]

        return Trajectory(
            path_id=f"js_{func_name}_path_{path_idx:03d}",
            basic_blocks=basic_blocks,
            path_condition=f"{func_name}_path_{path_idx}",
            branches_covered=branches,
            constraints=constraints,
            cost=float(len(path)),
            is_feasible=True
        )


def extract_js_trajectories(
    source_dir: Path, max_paths: int = 100
) -> List[Trajectory]:
    """Convenience function to extract trajectories from JS/TS code"""
    extractor = JSExtractor(max_paths=max_paths)
    return extractor.extract_paths(source_dir)