"""
Language Detector
Detects programming language of SUT
"""
from pathlib import Path
from typing import Dict, Optional
import logging
import json


class LanguageDetector:
    """
    Detect programming language and framework from source directory

    Supports:
    - Python (.py) - including Django, Flask
    - C (.c, .h)
    - C++ (.cpp, .cc, .cxx, .hpp, .h)
    - Java (.java) - including Spring Boot
    - JavaScript (.js, .mjs, .cjs, .jsx) - Express only (backend)
    - TypeScript (.ts, .tsx, .mts)
    """

    LANGUAGE_EXTENSIONS = {
        'python':     {'.py'},
        'c':          {'.c', '.h'},
        'cpp':        {'.cpp', '.cc', '.cxx', '.hpp', '.hh', '.h++'},
        'java':       {'.java'},
        'javascript': {'.js', '.mjs', '.cjs', '.jsx'},
        'typescript': {'.ts', '.tsx', '.mts'},
    }
    SUPPORTED_LANGUAGES = set(LANGUAGE_EXTENSIONS.keys())

    FRAMEWORK_INDICATORS = {
        'django':      ['manage.py', 'settings.py', 'urls.py', 'wsgi.py', 'asgi.py'],
        'flask':       ['app.py', 'application.py', 'run.py', 'requirements.txt'],
        'spring_boot': ['pom.xml', 'build.gradle', 'application.properties',
                        'application.yml', 'src/main/java'],
        'express':     ['package.json', 'app.js', 'server.js', 'index.js'],
        # ✅ Pas de nextjs, react, vue, angular — frontend exclu
    }

    @classmethod
    def detect(cls, source_dir: Path,
               logger: logging.Logger = logging.getLogger(__name__)) -> Dict[str, any]:
        """
        Detect language from source directory while ignoring heavy directories.
        """
        logger.info(f"🔍 Detecting language in {source_dir}")

        ignore_dirs = {
            'venv', '.venv', 'env', '.env', 'node_modules',
            '__pycache__', '.git', '.pytest_cache', '.idea', '.vscode',
            'site-packages', 'dist', 'build'
        }

        extension_counts = {}
        all_files = []

        for path in source_dir.rglob('*'):
            path_parts = set(path.parts)
            if any(ignore in path_parts for ignore in ignore_dirs):
                continue
            if path.is_file():
                suffix = path.suffix.lower()
                for lang, exts in cls.LANGUAGE_EXTENSIONS.items():
                    if suffix in exts:
                        all_files.append(path)
                        extension_counts[suffix] = extension_counts.get(suffix, 0) + 1

        if not all_files:
            logger.warning("No source files found in authorized directories")
            return {
                'language': 'unknown',
                'files': [],
                'entry_point': None,
                'confidence': 0.0
            }

        # --- Comptage par langage ---
        python_count = sum(
            extension_counts.get(ext, 0)
            for ext in cls.LANGUAGE_EXTENSIONS['python']
        )
        c_count = extension_counts.get('.c', 0)
        cpp_count = sum(
            extension_counts.get(ext, 0)
            for ext in cls.LANGUAGE_EXTENSIONS['cpp'] if ext != '.h'
        )
        java_count = extension_counts.get('.java', 0)
        js_count = sum(
            extension_counts.get(ext, 0)
            for ext in cls.LANGUAGE_EXTENSIONS['javascript']
        )
        ts_count = sum(
            extension_counts.get(ext, 0)
            for ext in cls.LANGUAGE_EXTENSIONS['typescript']
        )
        js_ts_count = js_count + ts_count

        total_count = python_count + c_count + cpp_count + java_count + js_ts_count

        # --- Détermination du langage principal ---
        counts = {
            'python':     python_count,
            'java':       java_count,
            'cpp':        cpp_count,
            'c':          c_count,
            'javascript': js_ts_count,
        }
        primary_language = max(counts, key=counts.get)

        if counts[primary_language] == 0:
            language     = 'unknown'
            confidence   = 0.0
            source_files = all_files

        elif primary_language == 'python':
            language     = 'python'
            confidence   = python_count / total_count
            source_files = [f for f in all_files if f.suffix == '.py']

        elif primary_language == 'java':
            language     = 'java'
            confidence   = java_count / total_count
            source_files = [f for f in all_files if f.suffix == '.java']

        elif primary_language == 'cpp':
            language     = 'cpp'
            confidence   = cpp_count / total_count
            source_files = [
                f for f in all_files
                if f.suffix in cls.LANGUAGE_EXTENSIONS['cpp']
            ]

        elif primary_language == 'c':
            language     = 'c'
            confidence   = c_count / total_count
            source_files = [f for f in all_files if f.suffix in {'.c', '.h'}]

        else:  # javascript / typescript
            language    = 'typescript' if ts_count > js_count else 'javascript'
            confidence  = js_ts_count / total_count
            source_files = [
                f for f in all_files
                if f.suffix in (
                    cls.LANGUAGE_EXTENSIONS['javascript'] |
                    cls.LANGUAGE_EXTENSIONS['typescript']
                )
            ]

        # --- Entry point & framework ---
        entry_point = cls._find_entry_point(source_dir, language, source_files)
        framework   = cls._detect_framework(source_dir, language, logger)

        logger.info(f"✅ Detected: {language} ({confidence:.0%} confidence)")
        if framework:
            logger.info(f"   Framework: {framework}")
        logger.info(f"   Files: {len(source_files)}")
        if entry_point:
            logger.info(f"   Entry: {entry_point.name}")

        return {
            'language':    language,
            'framework':   framework,
            'files':       source_files,
            'entry_point': entry_point,
            'confidence':  confidence,
            'file_count':  len(source_files),
        }

    # ------------------------------------------------------------------
    @classmethod
    def _find_entry_point(cls, source_dir: Path, language: str,
                          files: list) -> Optional[Path]:
        """Find main entry point file"""

        if language == 'python':
            candidates = ['main.py', 'app.py', '__main__.py', 'run.py']
            for candidate in candidates:
                f = source_dir / candidate
                if f.exists():
                    return f
            src_dir = source_dir / 'src'
            if src_dir.exists():
                for candidate in candidates:
                    f = src_dir / candidate
                    if f.exists():
                        return f
            return files[0] if files else None

        elif language in ['c', 'cpp']:
            candidates = ['main.c', 'main.cpp', 'app.c', 'app.cpp']
            for candidate in candidates:
                f = source_dir / candidate
                if f.exists():
                    return f
            src_dir = source_dir / 'src'
            if src_dir.exists():
                for candidate in candidates:
                    f = src_dir / candidate
                    if f.exists():
                        return f
            for file in files:
                if file.suffix in {'.c', '.cpp'}:
                    try:
                        if 'int main(' in file.read_text() or 'void main(' in file.read_text():
                            return file
                    except Exception:
                        continue
            return files[0] if files else None

        elif language == 'java':
            candidates = ['Main.java', 'App.java', 'Application.java']
            for candidate in candidates:
                for java_file in files:
                    if java_file.name == candidate:
                        return java_file
            for file in files:
                try:
                    if 'public static void main(' in file.read_text():
                        return file
                except Exception:
                    continue
            return files[0] if files else None

        elif language in ['javascript', 'typescript']:
            candidates = [
                # JS backend
                'index.js', 'main.js', 'app.js', 'server.js', 'index.mjs', 'main.mjs',
                # TS backend
                'index.ts', 'main.ts', 'app.ts', 'server.ts',
            ]
            for candidate in candidates:
                f = source_dir / candidate
                if f.exists():
                    return f
            src_dir = source_dir / 'src'
            if src_dir.exists():
                for candidate in candidates:
                    f = src_dir / candidate
                    if f.exists():
                        return f
            # Lire package.json
            pkg = source_dir / 'package.json'
            if pkg.exists():
                try:
                    data = json.loads(pkg.read_text())
                    for field in ('main', 'module', 'types', 'typings'):
                        declared = data.get(field)
                        if declared:
                            candidate = source_dir / declared
                            if candidate.exists():
                                return candidate
                except Exception:
                    pass
            return files[0] if files else None

        return None

    # ------------------------------------------------------------------
    @classmethod
    def _detect_framework(cls, source_dir: Path, language: str,
                          logger: logging.Logger) -> Optional[str]:
        """Detect backend framework only"""

        if language == 'python':
            django_score = sum(
                1 for ind in cls.FRAMEWORK_INDICATORS['django']
                if (source_dir / ind).exists()
            )
            if django_score >= 2:
                return 'django'

            flask_score = sum(
                1 for ind in cls.FRAMEWORK_INDICATORS['flask']
                if (source_dir / ind).exists()
            )
            if flask_score >= 1:
                return 'flask'

        elif language == 'java':
            spring_score = sum(
                1 for ind in cls.FRAMEWORK_INDICATORS['spring_boot']
                if (source_dir / ind).exists()
            )
            if spring_score >= 2:
                return 'spring_boot'

        elif language in ['javascript', 'typescript']:
            # ✅ Express uniquement — pas de détection frontend (next, react, vue…)
            express_score = sum(
                1 for ind in cls.FRAMEWORK_INDICATORS['express']
                if (source_dir / ind).exists()
            )
            if express_score >= 2:
                return 'express'

        return None

    # ------------------------------------------------------------------
    @classmethod
    def find_entry_point(cls, files: list, language: str) -> Optional[Path]:
        """Public helper: find entry point given a list of Path objects and language."""
        source_dir = files[0].parent if files else Path('.')
        return cls._find_entry_point(source_dir, language, files)