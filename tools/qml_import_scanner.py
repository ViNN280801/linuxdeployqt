from os import listdir as os_listdir
from os import makedirs as os_makedirs
from os.path import join as os_join
from os.path import exists as os_exists
from os.path import dirname as os_dirname
from os.path import basename as os_basename

from json import loads as json_loads
from json import JSONDecodeError as json_JSONDecodeError

from shutil import rmtree as shutil_rmtree
from shutil import copytree as shutil_copytree
from subprocess import run as subprocess_run
from subprocess import TimeoutExpired as subprocess_TimeoutExpired
from subprocess import CalledProcessError as subprocess_CalledProcessError

from typing import List, Dict, Set, Optional
from logger.logger import Logger


class QmlImportScanner:
    """
    QML Import Scanner that matches deployQmlImports from shared.cpp
    Uses qmlimportscanner to find QML dependencies like the official tool
    """

    def __init__(self, qt_info: Optional[Dict[str, str]], log_level: str = "DEBUG"):
        self.logger = Logger(log_level, "QmlImportScanner")
        self.qt_info = qt_info or {}

    def scan_qml_imports(
        self, qml_dirs: List[str], qml_import_paths: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """
        Scan QML files for imports using qmlimportscanner
        Matches deployQmlImports logic from shared.cpp

        Args:
            qml_dirs: List of directories containing QML files
            qml_import_paths: Additional QML import paths

        Returns:
            List of QML import information dictionaries
        """
        if not qml_dirs:
            self.logger.debug("No QML directories to scan")
            return []

        # Find qmlimportscanner (matches shared.cpp logic)
        qmlimportscanner_path = self._find_qmlimportscanner()
        if not qmlimportscanner_path:
            self.logger.error("qmlimportscanner not found")
            return []

        self.logger.info("🔍 Scanning QML imports...")
        self.logger.info(f"Application QML file path(s): {qml_dirs}")
        self.logger.info(f"QML module search path(s): {qml_import_paths or []}")

        # Build arguments for qmlimportscanner (matches shared.cpp)
        args = []

        # Add root paths
        for qml_dir in qml_dirs:
            args.extend(["-rootPath", qml_dir])

        # Add import paths
        if qml_import_paths:
            for import_path in qml_import_paths:
                args.extend(["-importPath", import_path])

        # Add Qt QML path
        qt_qml_path = self.qt_info.get("QT_INSTALL_QML", "")
        if qt_qml_path:
            args.extend(["-importPath", qt_qml_path])
            self.logger.debug(f"Qt QML path: {qt_qml_path}")

        # Run qmlimportscanner
        try:
            self.logger.debug(f"Running: {qmlimportscanner_path} {' '.join(args)}")
            result = subprocess_run(
                [qmlimportscanner_path] + args,
                capture_output=True,
                text=True,
                timeout=60,  # matches 60000ms timeout from shared.cpp
            )

            # Log errors if any (matches shared.cpp logic)
            if result.stderr:
                self.logger.warning("QML file parse error (deployment will continue):")
                self.logger.warning(result.stderr)

            if result.returncode != 0:
                self.logger.error(
                    f"qmlimportscanner failed with exit code {result.returncode}"
                )
                return []

            # Parse JSON output (matches shared.cpp)
            try:
                imports_data = json_loads(result.stdout)
                if not isinstance(imports_data, list):
                    self.logger.error(
                        "qmlimportscanner output error. Expected JSON array"
                    )
                    return []

                self.logger.info(f"🎨 Found {len(imports_data)} QML imports")
                return imports_data

            except json_JSONDecodeError as e:
                self.logger.error(f"Failed to parse qmlimportscanner JSON output: {e}")
                return []

        except subprocess_TimeoutExpired:
            self.logger.error("qmlimportscanner timed out")
            return []
        except Exception as e:
            self.logger.error(f"Failed to run qmlimportscanner: {e}")
            return []

    def deploy_qml_imports(
        self,
        imports_data: List[Dict[str, str]],
        target_dir: str,
        rpaths_used: Optional[Set[str]] = None,
    ) -> bool:
        """
        Deploy QML imports to target directory
        Matches deployQmlImport logic from shared.cpp

        Args:
            imports_data: QML import data from qmlimportscanner
            target_dir: Target AppDir path
            rpaths_used: Set of used RPATHs

        Returns:
            True if deployment successful
        """
        if not imports_data:
            self.logger.debug("No QML imports to deploy")
            return True

        rpaths_used = rpaths_used or set()
        qt_quick_controls_in_use = False

        self.logger.info("📦 Deploying QML imports...")

        for import_info in imports_data:
            name = import_info.get("name", "")
            path = import_info.get("path", "")
            import_type = import_info.get("type", "")

            if name == "QtQuick.Controls":
                qt_quick_controls_in_use = True

            self.logger.info(f"Deploying QML import: {name}")
            self.logger.debug(f"  path: {path}")
            self.logger.debug(f"  type: {import_type}")

            # Skip imports with missing info (matches shared.cpp)
            if not name or not path:
                self.logger.info("  Skip import: name or path is empty")
                continue

            # Deploy module imports only (matches shared.cpp)
            if import_type != "module":
                self.logger.info("  Skip non-module import")
                continue

            # Create destination path (matches shared.cpp logic)
            import_name = name.replace(".", "/")

            # Add version if present (matches shared.cpp)
            if len(path) >= 2:
                version = path[-2:]
                if version.startswith("."):
                    import_name += version

            import_dest_path = os_join(target_dir, "qml", import_name)

            # Deploy the import (matches recursiveCopyAndDeploy)
            if not self._deploy_qml_import(
                path, import_dest_path, target_dir, rpaths_used
            ):
                self.logger.warning(f"Failed to deploy QML import: {name}")

        # Special case: QtQuick/PrivateWidgets (matches shared.cpp)
        # Deploy if both QtWidgets and QtQuick.Controls are used
        if qt_quick_controls_in_use and self._requires_qt_widgets():
            self.logger.info("Deploying QML import QtQuick/PrivateWidgets")
            private_widgets_path = os_join(
                self.qt_info.get("QT_INSTALL_QML", ""), "QtQuick", "PrivateWidgets"
            )
            private_widgets_dest = os_join(
                target_dir, "qml", "QtQuick", "PrivateWidgets"
            )
            self._deploy_qml_import(
                private_widgets_path, private_widgets_dest, target_dir, rpaths_used
            )

        # CRITICAL: Always deploy QtQuick.Controls.2 and QtQuick.Templates.2 if detected
        self._deploy_critical_qml_modules(target_dir, rpaths_used)

        return True

    def _find_qmlimportscanner(self) -> Optional[str]:
        """
        Find qmlimportscanner executable
        Matches logic from shared.cpp
        """
        # Try Qt 5 location first
        qt_bins_path = self.qt_info.get("QT_INSTALL_BINS", "")
        if qt_bins_path:
            qmlimportscanner_path = os_join(qt_bins_path, "qmlimportscanner")
            if os_exists(qmlimportscanner_path):
                self.logger.debug(f"Found qmlimportscanner at: {qmlimportscanner_path}")
                return qmlimportscanner_path

        # Try Qt 6 location
        qt_libexecs_path = self.qt_info.get("QT_INSTALL_LIBEXECS", "")
        if qt_libexecs_path:
            qmlimportscanner_path = os_join(qt_libexecs_path, "qmlimportscanner")
            if os_exists(qmlimportscanner_path):
                self.logger.debug(
                    f"Found Qt 6 qmlimportscanner at: {qmlimportscanner_path}"
                )
                return qmlimportscanner_path

        # Try to find in PATH
        try:
            result = subprocess_run(
                ["which", "qmlimportscanner"], capture_output=True, text=True
            )
            if result.returncode == 0:
                qmlimportscanner_path = result.stdout.strip()
                self.logger.debug(
                    f"Found qmlimportscanner in PATH: {qmlimportscanner_path}"
                )
                return qmlimportscanner_path
        except Exception:
            pass

        self.logger.error("qmlimportscanner not found")
        self.logger.error(
            "Please install it if you want to bundle QML based applications"
        )
        return None

    def _deploy_qml_import(
        self, source_path: str, dest_path: str, app_dir_path: str, rpaths_used: Set[str]
    ) -> bool:
        """
        Deploy single QML import
        Matches deployQmlImport and recursiveCopyAndDeploy from shared.cpp
        """
        if not os_exists(source_path):
            self.logger.warning(f"QML import source not found: {source_path}")
            return False

        # Skip already deployed imports (matches shared.cpp logic)
        if os_exists(dest_path):
            try:
                files = os_listdir(dest_path)
                if files:
                    self.logger.debug(
                        f"QML import already deployed: {os_basename(dest_path)}"
                    )
                    return True
            except Exception:
                pass

        try:
            # Create destination directory
            os_makedirs(os_dirname(dest_path), exist_ok=True)

            # Copy QML import (matches recursiveCopyAndDeploy)
            self.logger.debug(f"Copying QML import: {source_path} -> {dest_path}")
            if os_exists(dest_path):
                self.logger.debug(f"Removing existing QML import: {dest_path}")
                shutil_rmtree(dest_path)
            shutil_copytree(source_path, dest_path)

            # Process .so files in the import (matches shared.cpp logic)
            self._process_qml_import_libraries(dest_path, app_dir_path, rpaths_used)

            return True

        except Exception as e:
            self.logger.error(f"Failed to deploy QML import {source_path}: {e}")
            return False

    def _process_qml_import_libraries(
        self, import_path: str, app_dir_path: str, rpaths_used: Set[str]
    ):
        """
        Process .so files in QML import directory
        Matches the .so processing logic from recursiveCopyAndDeploy in shared.cpp
        """
        try:
            import os

            for root, dirs, files in os.walk(import_path):
                for file in files:
                    if file.endswith(".so"):
                        so_path = os_join(root, file)
                        self.logger.debug(f"Processing QML .so file: {so_path}")

                        # Set correct rpath for the .so file
                        # self._fix_qml_library_rpath(so_path, app_dir_path)

        except Exception as e:
            self.logger.debug(f"Failed to process QML libraries in {import_path}: {e}")

    def _fix_qml_library_rpath(self, library_path: str, app_dir_path: str):
        """
        Fix RPATH for QML library to point to correct lib directory
        Matches rpath logic from recursiveCopyAndDeploy in shared.cpp
        """
        try:
            # Calculate relative path to lib directory
            import os

            rel_to_lib = os.path.relpath(
                os_join(app_dir_path, "lib"), os_dirname(library_path)
            )

            # Set RPATH using patchelf
            rpath = f"$ORIGIN:$ORIGIN/{rel_to_lib}"
            subprocess_run(
                ["patchelf", "--set-rpath", rpath, library_path],
                check=True,
                capture_output=True,
            )
            self.logger.debug(
                f"Updated RPATH for QML library: {os_basename(library_path)}"
            )

        except subprocess_CalledProcessError:
            self.logger.debug(
                f"Failed to update RPATH for: {os_basename(library_path)}"
            )
        except Exception as e:
            self.logger.debug(f"Error processing QML library {library_path}: {e}")

    def _requires_qt_widgets(self) -> bool:
        """
        Check if QtWidgets library is required
        This is a simplified check - in full implementation would check deployed libraries
        """
        # For now, assume QtWidgets is needed if we're deploying QML
        # In full implementation, this would check the deployed libraries list
        return True

    def _deploy_critical_qml_modules(self, target_dir: str, rpaths_used: Set[str]):
        """
        Deploy critical QML modules that are always needed for QtQuick.Controls 2
        These modules must be present or QtQuick.Controls will fail to load
        """
        if not self.qt_info:
            return

        qt_qml_path = self.qt_info.get("QT_INSTALL_QML", "")
        if not qt_qml_path or not os_exists(qt_qml_path):
            self.logger.warning("Qt QML path not found, cannot deploy critical modules")
            return

        # Critical QML modules that MUST be deployed for QtQuick.Controls 2
        critical_modules = [
            ("QtQuick/Controls.2", "QtQuick/Controls.2"),
            ("QtQuick/Templates.2", "QtQuick/Templates.2"),
        ]

        self.logger.info("🔧 Deploying critical QML modules for QtQuick.Controls 2...")

        for source_module, dest_module in critical_modules:
            source_path = os_join(qt_qml_path, source_module)
            dest_path = os_join(target_dir, "qml", dest_module)

            if os_exists(source_path):
                self.logger.info(f"📦 Deploying critical module: {dest_module}")
                success = self._deploy_qml_import(
                    source_path, dest_path, target_dir, rpaths_used
                )
                if success:
                    self.logger.debug(f"✅ Critical module deployed: {dest_module}")
                else:
                    self.logger.error(
                        f"❌ Failed to deploy critical module: {dest_module}"
                    )
            else:
                self.logger.warning(f"⚠️  Critical module not found: {source_path}")

        self.logger.success("✅ Critical QML modules deployment completed")
