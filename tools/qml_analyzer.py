from os import walk as os_walk
from os import listdir as os_listdir
from os.path import join as os_join
from os.path import exists as os_exists
from os.path import isdir as os_isdir

from typing import Set
from re import findall as re_findall

from logger import Logger, SUPPORTED_LOG_LEVELS


class QmlAnalyzer:
    """Analyzes QML files to determine required QML imports.

    This class scans QML files to find import statements and determines
    which QML modules need to be deployed, similar to the official linuxdeployqt.
    """

    def __init__(self, project_root: str, log_level: str = "DEBUG"):
        """Initialize QML analyzer.

        Args:
            project_root: Root directory of the project
            log_level: Logger verbosity level
        """
        if log_level not in SUPPORTED_LOG_LEVELS:
            log_level = "DEBUG"

        self.logger = Logger(log_level, "QmlAnalyzer")
        self.project_root = project_root
        self.custom_qml_dirs = []

        self.logger.debug("QmlAnalyzer initialized")

    def add_custom_qml_dir(self, qml_dir: str):
        """Add custom QML directory for analysis.

        Args:
            qml_dir: Path to custom QML directory
        """
        if qml_dir not in self.custom_qml_dirs:
            self.custom_qml_dirs.append(qml_dir)
            self.logger.debug(f"Added custom QML directory: {qml_dir}")

    def analyze_qml_imports(self) -> Set[str]:
        """Analyze QML files to find required imports.

        Scans all QML files in the project and custom directories to find
        import statements and returns the set of required modules.

        Returns:
            Set of QML module names that need to be deployed
        """
        self.logger.info("🎨 Analyzing QML imports...")

        imports = set()

        try:
            # Analyze project QML files
            project_qml_dirs = self._find_qml_directories()
            for qml_dir in project_qml_dirs:
                dir_imports = self._analyze_qml_directory(qml_dir)
                imports.update(dir_imports)

            # Analyze custom QML directories
            for custom_dir in self.custom_qml_dirs:
                if os_exists(custom_dir):
                    dir_imports = self._analyze_qml_directory(custom_dir)
                    imports.update(dir_imports)

            # Add standard modules that are commonly needed
            standard_modules = self._get_standard_qml_modules(imports)
            imports.update(standard_modules)

            self.logger.info(f"🎨 Found {len(imports)} QML modules to deploy")
            for module in sorted(imports):
                self.logger.debug(f"  - {module}")

            return imports

        except Exception as e:
            self.logger.error(f"❌ Failed to analyze QML imports: {e}")
            return set()

    def _find_qml_directories(self) -> list:
        """Find QML directories in the project.

        Returns:
            List of directory paths containing QML files
        """
        qml_dirs = []

        # Common QML directory names
        common_qml_dirs = ["qml", "src/qml", "resources/qml", "ui", "src/ui"]

        for dir_name in common_qml_dirs:
            qml_dir = os_join(self.project_root, dir_name)
            if os_exists(qml_dir) and os_isdir(qml_dir):
                qml_dirs.append(qml_dir)
                self.logger.debug(f"Found QML directory: {qml_dir}")

        # Also check for QML files in the project root
        if self._has_qml_files(self.project_root):
            qml_dirs.append(self.project_root)

        return qml_dirs

    def _analyze_qml_directory(self, qml_dir: str) -> Set[str]:
        """Analyze QML files in a directory for imports.

        Args:
            qml_dir: Directory containing QML files

        Returns:
            Set of imported module names
        """
        imports = set()

        try:
            for root_dir, _, files in os_walk(qml_dir):
                for file in files:
                    if file.endswith((".qml", ".js")):
                        file_path = os_join(root_dir, file)
                        file_imports = self._parse_qml_file(file_path)
                        imports.update(file_imports)

        except Exception as e:
            self.logger.warning(f"⚠️ Failed to analyze QML directory {qml_dir}: {e}")

        return imports

    def _parse_qml_file(self, file_path: str) -> Set[str]:
        """Parse a single QML file for import statements.

        Args:
            file_path: Path to the QML file

        Returns:
            Set of imported module names
        """
        imports = set()

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Find import statements
            # Matches patterns like:
            # import QtQuick 2.15
            # import QtQuick.Controls 2.15
            # import QtWebEngine 1.0
            import_pattern = (
                r"import\s+([A-Za-z][A-Za-z0-9_.]*)\s+[\d.]+(?:\s+as\s+\w+)?"
            )
            matches = re_findall(import_pattern, content)

            for match in matches:
                module_name = match.strip()
                if module_name and not module_name.startswith('"'):
                    imports.add(module_name)
                    self.logger.debug(f"Found import: {module_name} in {file_path}")

        except Exception as e:
            self.logger.debug(f"Could not parse QML file {file_path}: {e}")

        return imports

    def _has_qml_files(self, directory: str) -> bool:
        """Check if directory contains QML files.

        Args:
            directory: Directory to check

        Returns:
            True if directory contains .qml files
        """
        try:
            for item in os_listdir(directory):
                if item.endswith(".qml"):
                    return True
        except Exception:
            pass
        return False

    def _get_standard_qml_modules(self, found_imports: Set[str]) -> Set[str]:
        """Get standard QML modules that are commonly needed.

        Args:
            found_imports: Set of imports already found

        Returns:
            Set of additional standard modules
        """
        standard_modules = set()

        # If QtQuick is used, add common related modules
        if any(imp.startswith("QtQuick") for imp in found_imports):
            standard_modules.update(["QtQuick.Window", "QtQuick.Layouts"])

        # If Controls are used, add related modules
        if any("Controls" in imp for imp in found_imports):
            standard_modules.update(["QtQuick.Templates", "QtQuick.Controls.impl"])

        # Filter out modules that are already in found_imports
        return standard_modules - found_imports
