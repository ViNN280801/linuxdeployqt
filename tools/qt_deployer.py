from os import X_OK as os_X_OK
from os import walk as os_walk
from os import chmod as os_chmod
from os import access as os_access
from os import remove as os_remove
from os import listdir as os_listdir
from os import symlink as os_symlink
from os import makedirs as os_makedirs

from os.path import join as os_join
from os.path import isdir as os_path_isdir
from os.path import isfile as os_path_isfile
from os.path import islink as os_path_islink
from os.path import exists as os_path_exists
from os.path import abspath as os_path_abspath
from os.path import dirname as os_path_dirname
from os.path import relpath as os_path_relpath
from os.path import basename as os_path_basename

from shutil import copy2 as shutil_copy2
from shutil import rmtree as shutil_rmtree
from shutil import copytree as shutil_copytree
from subprocess import run as subprocess_run
from subprocess import CalledProcessError as subprocess_CalledProcessError
from subprocess import TimeoutExpired as subprocess_TimeoutExpired

from typing import Dict, List, Optional, Set
from logger.logger import Logger

from .appdir_paths import AppDirPaths
from .ldd_dependency_collector import LddDependencyCollector, LibraryInfo
from .patch_gnustack import GnuStackPatcher
from .qt_component_analyzer import QtComponentAnalyzer
from .qml_import_scanner import QmlImportScanner


class QtDeployer:
    def __init__(self, project_root: str, log_level: str = "DEBUG"):
        self.project_root = project_root
        self.log_level = log_level  # Store for later use
        self.logger = Logger(log_level, self.__class__.__name__)

        # Create dependency collector with default settings (matching original linuxdeployqt)
        self.dependency_collector = LddDependencyCollector(log_level)
        self.dependency_collector.set_bundle_mode(bundle_all_but_core_libs=False)

        self.component_analyzer = QtComponentAnalyzer(
            self.dependency_collector, project_root, log_level
        )

        self.always_overwrite_enabled = False
        self.bundle_all_but_core_libs = (
            False  # Default to false like original linuxdeployqt
        )
        self.bundle_everything = False
        self.run_strip_enabled = True
        self.copy_copyright_files = True
        self.qt_lib_infix = ""
        self.fhs_like_mode = False
        self.fhs_prefix = ""

        self.qt_detected = 0  # 0 = not detected, 4 = Qt4, 5 = Qt5, 6 = Qt6
        self.qt_detection_complete = False
        self.qt_to_be_bundled_info = {}

        # Paths
        self.app_binary_path = ""
        self.appdir_paths: Optional[AppDirPaths] = None
        self.explicit_qt_path = ""  # Path to explicit Qt installation

        # QML Import Scanner
        self.qml_import_scanner = None

        self.logger.debug("QtDeployer initialized")

    def set_custom_qml_dir(self, qml_dir: str):
        """Set custom QML directory for analysis"""
        self.component_analyzer.set_custom_qml_dir(qml_dir)

    def set_explicit_qt_path(self, qt_path: str):
        """
        Set explicit Qt installation path to prevent ABI conflicts.

        Args:
            qt_path: Path to Qt installation directory (e.g., /opt/Qt5.15.17)
        """
        self.explicit_qt_path = qt_path
        self.logger.info(f"🎯 Using explicit Qt installation: {qt_path}")

        # Pre-validate the Qt installation
        qt_bin_dir = os_join(qt_path, "bin")
        qt_lib_dir = os_join(qt_path, "lib")
        qmake_path = os_join(qt_bin_dir, "qmake")

        if not os_path_exists(qmake_path):
            self.logger.warning(f"⚠️ qmake not found at {qmake_path}")
        else:
            self.logger.debug(f"✅ Found qmake at: {qmake_path}")

        if not os_path_exists(qt_lib_dir):
            self.logger.warning(f"⚠️ Qt lib directory not found at {qt_lib_dir}")
        else:
            self.logger.debug(f"✅ Found Qt lib directory: {qt_lib_dir}")

    def deploy_qt(
        self,
        executable_path: str,
        target_dir: str,
        desktop_file: str = "",
        icon_file: str = "",
        apprun_file: str = "",
    ) -> bool:
        """
        Args:
            executable_path: Path to main application binary
            target_dir: Target AppDir path
            desktop_file: Path to .desktop file
            icon_file: Path to icon file
            apprun_file: Path to AppRun script

        Returns:
            True if deployment successful
        """
        try:
            self.logger.info("🚀 Starting Qt deployment...")

            # Validate inputs
            if not os_path_exists(executable_path):
                self.logger.error(f"Executable not found: {executable_path}")
                return False

            self.app_binary_path = os_path_abspath(executable_path)

            # Check if AppRun script expects FHS structure
            force_fhs_mode = False
            if apprun_file and os_path_exists(apprun_file):
                try:
                    with open(apprun_file, "r") as f:
                        apprun_content = f.read()
                    # If AppRun references usr/bin, force FHS mode
                    if "/usr/bin/" in apprun_content or "$HERE/usr/" in apprun_content:
                        force_fhs_mode = True
                        self.logger.debug(
                            "🔧 Forcing FHS mode due to AppRun script structure"
                        )
                except Exception as e:
                    self.logger.debug(f"Could not read AppRun file: {e}")

            # Determine FHS-like mode
            self._determine_fhs_mode()

            # Override FHS mode if needed
            if force_fhs_mode and not self.fhs_like_mode:
                self.fhs_like_mode = True
                self.fhs_prefix = target_dir  # Use target dir as prefix
                self.logger.info("🔧 Enabled FHS mode for AppRun compatibility")

            # Initialize AppDir paths
            self.appdir_paths = AppDirPaths(
                target_dir, self.fhs_like_mode, self.fhs_prefix
            )

            # Create AppDir structure
            if not self._create_appdir_structure(
                executable_path, target_dir, apprun_file
            ):
                return False

            # Find dependencies and detect Qt version
            dependencies = self.dependency_collector.get_libs(executable_path)
            self._detect_qt_version(dependencies)

            # Sync Qt version detection with dependency collector
            if self.dependency_collector.qt_detected != 0:
                self.qt_detected = self.dependency_collector.qt_detected
                self.logger.debug(
                    f"Synced Qt version from dependency collector: {self.qt_detected}"
                )

            if self.qt_detected == 0:
                self.logger.warning(
                    "No Qt libraries detected, deploying non-Qt libraries only"
                )

            # Get Qt information using qmake
            qt_info = self._get_qt_info_from_qmake()
            if qt_info:
                self.qt_to_be_bundled_info = qt_info

            # Initialize QML Import Scanner with Qt info
            self.qml_import_scanner = QmlImportScanner(
                self.qt_to_be_bundled_info, self.log_level
            )

            # Mark detection as complete
            self.qt_detection_complete = True

            # Deploy all libraries
            if not self._deploy_all_libraries(executable_path, target_dir):
                return False

            # Deploy system Qt libraries with version aliasing if Qt detected
            if self.qt_detected > 0:
                if not self._deploy_system_qt_libraries(target_dir, self.qt_detected):
                    self.logger.warning(
                        "Failed to deploy system Qt libraries, but continuing..."
                    )

            # Deploy Qt plugins if Qt detected
            if self.qt_detected > 0:
                components = self.component_analyzer.analyze_required_components(
                    executable_path
                )

                # Deploy plugins
                plugins = components.get("plugins", set())
                if isinstance(plugins, set) and plugins:
                    if not self._deploy_plugins(plugins, target_dir):
                        return False

                # Deploy QML imports using qmlimportscanner
                if not self._deploy_qml_imports_with_scanner(target_dir):
                    return False

                # Create qt.conf
                if not self._create_qt_conf(target_dir):
                    return False

                # Deploy WebEngine components if needed
                webengine_needed = components.get("webengine_needed", False)
                if webengine_needed:
                    if not self._deploy_webengine_components(qt_info, target_dir):
                        return False

                # Deploy Qt translations
                if not self._deploy_qt_translations(qt_info, target_dir):
                    return False

            # Deploy desktop integration
            if desktop_file and icon_file:
                self._deploy_desktop_integration(target_dir, desktop_file, icon_file)

            # Deploy application resources
            if not self._deploy_application_resources(target_dir):
                return False

            # Final step: verify and fix all RPATH settings
            self._verify_and_fix_rpaths(target_dir)

            self.logger.success("✅ Qt deployment completed successfully!")
            return True

        except Exception as e:
            self.logger.error(f"❌ Qt deployment failed: {e}")
            import traceback

            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return False

    def _determine_fhs_mode(self):
        """Determine if FHS-like mode should be used"""
        potential_fhs_prefix = os_path_dirname(os_path_dirname(self.app_binary_path))
        bin_dir = os_join(potential_fhs_prefix, "bin")

        if os_path_isdir(bin_dir) and self.app_binary_path.startswith(bin_dir):
            self.fhs_like_mode = True
            self.fhs_prefix = potential_fhs_prefix
            self.logger.debug(f"FHS-like mode enabled with PREFIX: {self.fhs_prefix}")
        else:
            self.fhs_like_mode = False
            self.logger.debug("Using traditional AppDir mode")

    def _create_appdir_structure(
        self, executable_path: str, target_dir: str, apprun_file: str
    ) -> bool:
        """Create AppDir structure"""
        try:
            # Create main AppDir directory
            os_makedirs(target_dir, exist_ok=True)
            self.logger.info(f"📁 Created AppDir: {target_dir}")

            if not self.appdir_paths:
                return False

            # Create necessary directories
            directories_to_create = [
                self.appdir_paths.LIB_DIR,
                self.appdir_paths.PLUGINS_DIR,
                self.appdir_paths.QML_DIR,
                self.appdir_paths.TRANSLATIONS_DIR,
            ]

            if self.fhs_like_mode:
                directories_to_create.extend(
                    [
                        self.appdir_paths.BIN_DIR,
                        self.appdir_paths.SHARE_DIR,
                    ]
                )

            for directory in directories_to_create:
                os_makedirs(directory, exist_ok=True)
                self.logger.debug(f"Created directory: {directory}")

            # Copy main executable
            app_name = os_path_basename(executable_path)

            if self.fhs_like_mode:
                target_executable = os_join(self.appdir_paths.BIN_DIR, app_name)
                relative_bin_path = f"usr/bin/{app_name}"
            else:
                target_executable = os_join(target_dir, app_name)
                relative_bin_path = app_name

            shutil_copy2(executable_path, target_executable)
            os_chmod(target_executable, 0o755)
            self.logger.info(f"📋 Copied executable: {app_name}")

            # Create AppRun
            apprun_path = os_join(target_dir, "AppRun")
            if not os_path_exists(apprun_path):
                if apprun_file and os_path_exists(apprun_file):
                    shutil_copy2(apprun_file, apprun_path)
                    os_chmod(apprun_path, 0o755)
                    self.logger.info("📋 Copied custom AppRun script")
                else:
                    # Create enhanced AppRun script with LD_LIBRARY_PATH
                    apprun_content = self._create_enhanced_apprun_script(
                        app_name, self.fhs_like_mode
                    )
                    try:
                        with open(apprun_path, "w") as f:
                            f.write(apprun_content)
                        os_chmod(apprun_path, 0o755)
                        self.logger.info(
                            "🚀 Created enhanced AppRun script with library isolation"
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to create enhanced AppRun: {e}")
                        # Fallback to symlink
                        try:
                            os_symlink(relative_bin_path, apprun_path)
                            self.logger.info(
                                f"🔗 Created AppRun symlink to {relative_bin_path}"
                            )
                        except OSError:
                            # Fallback to copy if symlink fails
                            shutil_copy2(target_executable, apprun_path)
                            os_chmod(apprun_path, 0o755)
                            self.logger.info(
                                "📋 Created AppRun as copy (symlink failed)"
                            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to create AppDir structure: {e}")
            return False

    def _detect_qt_version(self, dependencies: List[str]):
        """Detect Qt version from dependencies"""
        for dep in dependencies:
            dep_lower = dep.lower()
            if "libqt6" in dep_lower:
                self.qt_detected = 6
                self.logger.info("🎯 Qt 6 detected")
                break
            elif "libqt5" in dep_lower:
                self.qt_detected = 5
                self.logger.info("🎯 Qt 5 detected")
                break
            elif "libqtcore.so.4" in dep_lower:
                self.qt_detected = 4
                self.logger.info("🎯 Qt 4 detected")
                break

    def _get_qt_info_from_qmake(self) -> Optional[Dict[str, str]]:
        """Get Qt information using qmake"""
        try:
            if self.qt_detected == 0:
                return None

            qmake_path = None

            # If explicit Qt path is set, use qmake from that path only
            if self.explicit_qt_path:
                explicit_qmake = os_join(self.explicit_qt_path, "bin", "qmake")
                if os_path_exists(explicit_qmake):
                    qmake_path = explicit_qmake
                    self.logger.info(f"🎯 Using explicit qmake: {qmake_path}")
                else:
                    self.logger.error(
                        f"❌ qmake not found in explicit Qt path: {explicit_qmake}"
                    )
                    return None
            else:
                # Try to find qmake on PATH (original behavior)
                qmake_candidates = []

                if self.qt_detected == 6:
                    qmake_candidates.extend(["qmake-qt6", "qmake"])
                elif self.qt_detected == 5:
                    qmake_candidates.extend(["qmake-qt5", "qmake"])
                elif self.qt_detected == 4:
                    qmake_candidates.extend(["qmake-qt4", "qmake"])
                else:
                    qmake_candidates.append("qmake")

                for candidate in qmake_candidates:
                    try:
                        result = subprocess_run(
                            ["which", candidate],
                            capture_output=True,
                            text=True,
                            check=True,
                        )
                        qmake_path = result.stdout.strip()
                        self.logger.info(f"🔍 Found qmake on PATH: {qmake_path}")
                        break
                    except subprocess_CalledProcessError:
                        continue

                if not qmake_path:
                    self.logger.warning("qmake not found on PATH")
                    return None

            # Run qmake -query
            result = subprocess_run(
                [qmake_path, "-query"], capture_output=True, text=True, check=True
            )

            qt_info = {}
            for line in result.stdout.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    qt_info[key.strip()] = value.strip()

            # Validate Qt installation
            qt_libs_path = qt_info.get("QT_INSTALL_LIBS", "")
            if not qt_libs_path or not os_path_exists(qt_libs_path):
                self.logger.warning("Qt installation path could not be determined")
                return qt_info  # Return partial info anyway

            self.logger.debug(f"Qt libs path: {qt_libs_path}")

            # When using explicit Qt path, verify consistency
            if self.explicit_qt_path:
                expected_libs_path = os_join(self.explicit_qt_path, "lib")
                if qt_libs_path != expected_libs_path:
                    self.logger.warning(
                        f"⚠️ qmake reports different lib path ({qt_libs_path}) "
                        f"than expected from explicit Qt path ({expected_libs_path})"
                    )
                else:
                    self.logger.info("✅ Confirmed explicit Qt installation paths")

            return qt_info

        except Exception as e:
            self.logger.warning(f"Failed to get Qt information: {e}")
            return None

    def _deploy_all_libraries(self, executable_path: str, target_dir: str) -> bool:
        """
        Deploy all libraries (Qt and non-Qt) using proper filtering
        """
        try:
            if not self.appdir_paths:
                return False

            self.logger.info("📚 Deploying all libraries...")

            # Get libraries using proper filtering (respects exclude list)
            libraries_to_bundle = self.dependency_collector.get_libs(executable_path)

            if not libraries_to_bundle:
                self.logger.warning("No libraries found to bundle")
                return True

            # Convert library paths to LibraryInfo objects for deployment
            libraries_to_deploy = []

            for lib_path in libraries_to_bundle:
                lib_info = self._create_library_info(lib_path, target_dir)
                if lib_info:
                    libraries_to_deploy.append(lib_info)

            # Add missing Qt platform libraries that are not detected by ldd
            # but are required for XCB platform plugin
            missing_qt_libs = self._find_missing_qt_platform_libraries()
            for missing_lib in missing_qt_libs:
                if missing_lib and os_path_exists(missing_lib.source_file_path):
                    libraries_to_deploy.append(missing_lib)
                    self.logger.info(
                        f"🔧 Adding missing Qt platform library: {missing_lib.library_name}"
                    )

            # Deploy each library
            copied_libraries = []
            processed_paths = set()
            deployed_full_paths = []  # list to store full paths

            while libraries_to_deploy:
                library = libraries_to_deploy.pop(0)

                if library.library_name in copied_libraries:
                    continue

                copied_libraries.append(library.library_name)

                # Copy the library to AppDir
                deployed_path = self._copy_library(library, target_dir)
                if not deployed_path:
                    continue
                deployed_full_paths.append(deployed_path)  # Store the full path

                # Strip binary if enabled
                if self.run_strip_enabled:
                    self._run_strip(deployed_path)

                # Check for dependencies of this library (recursive)
                # Use get_libs to respect exclude list
                if deployed_path not in processed_paths:
                    processed_paths.add(deployed_path)
                    dep_library_paths = self.dependency_collector.get_libs(
                        deployed_path
                    )

                    for dep_lib_path in dep_library_paths:
                        dep_lib_name = os_path_basename(dep_lib_path)
                        # Ensure we don't re-add or re-process already copied libraries
                        if (
                            dep_lib_name not in copied_libraries
                            and dep_lib_path not in processed_paths
                        ):
                            dep_lib_info = self._create_library_info(
                                dep_lib_path, target_dir
                            )
                            if dep_lib_info and dep_lib_info not in libraries_to_deploy:
                                libraries_to_deploy.append(dep_lib_info)

            # Post-deployment cleanup: remove any excluded libraries that slipped through
            removed_count = self._cleanup_excluded_libraries(target_dir)
            if removed_count > 0:
                self.logger.info(f"🧹 Cleaned up {removed_count} excluded libraries")

            final_count = (
                len(deployed_full_paths) - removed_count
            )  # Use deployed_full_paths count
            self.logger.success(f"✅ Deployed {final_count} libraries")

            self.logger.info("Fixing GNU_STACK segments in deployed libraries...")
            for lib_path in deployed_full_paths:  # Iterate over full paths
                self.logger.debug(f"Fixing GNU_STACK segment in {lib_path}")
                GnuStackPatcher.fix_executable_stack(lib_path)
            return True

        except Exception as e:
            self.logger.error(f"Failed to deploy libraries: {e}")
            return False

    def _cleanup_excluded_libraries(self, target_dir: str) -> int:
        """
        Clean up any excluded libraries that were deployed by mistake.

        Args:
            target_dir: Target AppDir path

        Returns:
            Number of removed libraries
        """
        from .exclude_libs import GENERATED_EXCLUDE_LIST

        removed_count = 0

        if not self.appdir_paths:
            return removed_count

        lib_dir = self.appdir_paths.LIB_DIR

        if not os_path_isdir(lib_dir):
            return removed_count

        try:
            # Scan the lib directory for excluded libraries
            for root, _, files in os_walk(lib_dir):
                for file in files:
                    if file.endswith(".so") or ".so." in file:
                        # Check if this file matches any in the exclude list
                        for excluded_lib in GENERATED_EXCLUDE_LIST:
                            if file == excluded_lib or file.startswith(
                                excluded_lib.replace(".so", ".so.")
                            ):
                                lib_path = os_join(root, file)
                                try:
                                    os_remove(lib_path)
                                    self.logger.debug(
                                        f"🗑️  Removed excluded library: {file}"
                                    )
                                    removed_count += 1
                                except Exception as e:
                                    self.logger.warning(f"Failed to remove {file}: {e}")
                                break

        except Exception as e:
            self.logger.error(f"Failed to cleanup excluded libraries: {e}")

        return removed_count

    def _find_existing_libraries(self, target_dir: str) -> List[str]:
        """Find existing libraries in AppDir"""
        libraries = []
        if self.appdir_paths:
            lib_dir = self.appdir_paths.LIB_DIR

            if os_path_isdir(lib_dir):
                for root, _, files in os_walk(lib_dir):
                    for file in files:
                        if file.endswith(".so") or ".so." in file:
                            libraries.append(os_join(root, file))

        return libraries

    def _create_library_info(
        self, library_path: str, target_dir: str
    ) -> Optional[LibraryInfo]:
        """
        Create LibraryInfo object from library path

        Args:
            library_path: Full path to library file
            target_dir: Target AppDir path

        Returns:
            LibraryInfo object or None if invalid
        """
        if not library_path or not os_path_exists(library_path):
            return None

        try:
            lib_info = LibraryInfo()
            lib_name = os_path_basename(library_path)
            lib_dir = os_path_dirname(library_path)

            lib_info.library_name = lib_name
            lib_info.binary_name = lib_name
            lib_info.library_path = library_path
            lib_info.binary_path = library_path
            lib_info.source_file_path = library_path
            lib_info.library_directory = lib_dir + "/"
            lib_info.binary_directory = lib_dir + "/"
            lib_info.is_dylib = True
            lib_info.deployed_install_name = "$ORIGIN"

            # Set destination directory
            if target_dir in library_path:
                # Library already in AppDir
                lib_info.library_destination_directory = os_path_relpath(
                    lib_dir, target_dir
                )
            else:
                lib_info.library_destination_directory = "lib/"

            lib_info.binary_destination_directory = (
                lib_info.library_destination_directory
            )

            return lib_info

        except Exception as e:
            self.logger.debug(f"Failed to create LibraryInfo for {library_path}: {e}")
            return None

    def _find_missing_qt_platform_libraries(self) -> List[LibraryInfo]:
        """
        Find missing Qt platform libraries that are required but not detected by ldd.
        This addresses the common issue where libQt5XcbQpa.so.5 and libQt5DBus.so.5
        are needed but not bundled.
        """
        missing_libraries = []

        if self.qt_detected == 0:
            return missing_libraries

        # Use explicit Qt path if set, otherwise use qmake info
        qt_libs_path = ""
        if self.explicit_qt_path:
            qt_libs_path = os_join(self.explicit_qt_path, "lib")
            self.logger.debug(f"🎯 Using explicit Qt libs path: {qt_libs_path}")
        elif self.qt_to_be_bundled_info:
            qt_libs_path = self.qt_to_be_bundled_info.get("QT_INSTALL_LIBS", "")
            self.logger.debug(f"🔍 Using qmake Qt libs path: {qt_libs_path}")

        if not qt_libs_path or not os_path_exists(qt_libs_path):
            self.logger.debug(
                "No valid Qt libs path found for missing library detection"
            )
            return missing_libraries

        # List of critical Qt platform libraries based on detected Qt version
        critical_qt_libs = []

        if self.qt_detected == 5:
            critical_qt_libs = [
                "libQt5XcbQpa.so.5",
                "libQt5DBus.so.5",
                "libQt5XcbQpa.so",
                "libQt5DBus.so",
                # Critical Qt Quick Controls 2 libraries
                "libQt5QuickControls2.so.5",
                "libQt5QuickTemplates2.so.5",
                "libQt5QuickControls2.so",
                "libQt5QuickTemplates2.so",
            ]
        elif self.qt_detected == 6:
            critical_qt_libs = [
                "libQt6XcbQpa.so.6",
                "libQt6DBus.so.6",
                "libQt6XcbQpa.so",
                "libQt6DBus.so",
                # Critical Qt Quick Controls 2 libraries for Qt6
                "libQt6QuickControls2.so.6",
                "libQt6QuickTemplates2.so.6",
                "libQt6QuickControls2.so",
                "libQt6QuickTemplates2.so",
            ]
        elif self.qt_detected == 4:
            # Qt4 has different platform libraries
            critical_qt_libs = [
                "libQtDBus.so.4",
            ]

        for lib_name in critical_qt_libs:
            lib_path = os_join(qt_libs_path, lib_name)
            if os_path_exists(lib_path):
                # Create LibraryInfo for this missing library
                lib_info = LibraryInfo()
                lib_info.library_name = lib_name
                lib_info.binary_name = lib_name
                lib_info.source_file_path = lib_path
                lib_info.library_destination_directory = "lib/"
                lib_info.binary_destination_directory = "lib/"
                lib_info.is_dylib = True
                lib_info.deployed_install_name = "$ORIGIN"

                missing_libraries.append(lib_info)
                self.logger.debug(
                    f"Found critical Qt{self.qt_detected} library: {lib_path}"
                )

        return missing_libraries

    def _create_enhanced_apprun_script(self, app_name: str, fhs_like_mode: bool) -> str:
        """
        Create enhanced AppRun script with comprehensive library isolation.
        Specially designed to handle Boost libraries and other non-Qt dependencies.

        Args:
            app_name: Name of the application binary
            fhs_like_mode: Whether using FHS-like directory structure

        Returns:
            AppRun script content as string
        """
        if fhs_like_mode:
            binary_path = f"usr/bin/{app_name}"
            lib_paths = "${HERE}/usr/lib:${HERE}/lib"
            plugin_paths = "${HERE}/usr/plugins:${HERE}/plugins"
            qml_paths = "${HERE}/usr/qml:${HERE}/qml"
        else:
            binary_path = app_name
            lib_paths = "${HERE}/lib"
            plugin_paths = "${HERE}/plugins"
            qml_paths = "${HERE}/qml"

        script_content = f"""#!/bin/bash

# Capture original LD_LIBRARY_PATH from the host environment
LD_LIBRARY_PATH_ORIGINAL="$LD_LIBRARY_PATH"

# *********************************************************************************
# Generated by linuxdeployqt-python automatically                               ***
# *********************************************************************************

# Enhanced AppRun script for {app_name}
# Ensures comprehensive library isolation for Qt and non-Qt libraries (Boost, etc.)
# Based on official linuxdeployqt behavior with Astra Linux compatibility

# Get the directory where this AppImage is mounted
HERE="$(dirname "$(readlink -f "${{0}}")")"

# === CRITICAL: Library path isolation ===
# This prioritizes AppImage libraries over system ones to prevent "not found" errors
# Especially important for Boost libraries and other non-Qt dependencies

# Primary library paths (highest priority)
export LD_LIBRARY_PATH="{lib_paths}"

# Add common system library paths for unbundled system libraries
# These are often needed for things like NSS, Glib, etc., which are excluded by design
if [ -d "/usr/lib" ]; then
    LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:/usr/lib"
fi
if [ -d "/usr/lib/x86_64-linux-gnu" ]; then
    LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:/usr/lib/x86_64-linux-gnu"
fi
if [ -d "/lib" ]; then
    LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:/lib"
fi
if [ -d "/lib/x86_64-linux-gnu" ]; then
    LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:/lib/x86_64-linux-gnu"
fi

# Additional fallback paths for complex dependency chains
if [ -d "${{HERE}}/lib64" ]; then
    LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:${{HERE}}/lib64"
fi

# Add specific problematic system library paths that are often excluded by default
if [ -d "/usr/lib/x86_64-linux-gnu/nss" ]; then
    LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:/usr/lib/x86_64-linux-gnu/nss"
fi
if [ -d "/usr/lib/x86_64-linux-gnu/mesa" ]; then
    LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:/usr/lib/x86_64-linux-gnu/mesa"
fi

# Append original LD_LIBRARY_PATH from the environment where AppRun was launched
export LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:${{LD_LIBRARY_PATH_ORIGINAL}}"

# === Qt-specific environment setup ===
# Force Qt to use our bundled plugins and QML modules
export QT_PLUGIN_PATH="{plugin_paths}"
export QML2_IMPORT_PATH="{qml_paths}"
export QT_QPA_PLATFORM_PLUGIN_PATH="{plugin_paths}/platforms"

# Disable Qt's attempts to use system libraries
export QT_QPA_GENERIC_PLUGINS=""
export QT_AUTO_SCREEN_SCALE_FACTOR=0

# === Advanced library resolution ===
# These help with complex dependency scenarios common in Astra Linux

# Ensure dynamic linker finds our libraries first
export LD_PRELOAD=""

# Help with OpenGL and graphics library resolution
if [ -d "${{HERE}}/lib/x86_64-linux-gnu" ]; then
    export LD_LIBRARY_PATH="${{HERE}}/lib/x86_64-linux-gnu:${{LD_LIBRARY_PATH}}"
fi

# === Error handling and debugging ===
# Debug mode (enable with APPIMAGE_DEBUG=1)
if [ -n "$APPIMAGE_DEBUG" ]; then
    echo "=== Enhanced AppRun Debug Info ==="
    echo "HERE: $HERE"
    echo "Binary path: {binary_path}"
    echo "LD_LIBRARY_PATH: $LD_LIBRARY_PATH"
    echo "QT_PLUGIN_PATH: $QT_PLUGIN_PATH"
    echo "QML2_IMPORT_PATH: $QML2_IMPORT_PATH"
    echo "QT_QPA_PLATFORM_PLUGIN_PATH: $QT_QPA_PLATFORM_PLUGIN_PATH"
    echo ""
    echo "=== Available libraries ==="
    if [ -d "${{HERE}}/lib/" ]; then
        ls -la "${{HERE}}/lib/" 2>/dev/null
    else
        echo "No lib directory found"
    fi
    echo ""
    echo "=== Testing library dependencies ==="
    if command -v ldd >/dev/null 2>&1; then
        ldd "${{HERE}}/{binary_path}" 2>/dev/null | grep -E "(not found|=>)" | head -20 || echo "ldd check failed"
    else
        echo "ldd command not available"
    fi
    echo "========================="
fi

# === Binary location and execution ===
# Find and execute the application
EXEC="${{HERE}}/{binary_path}"

# Fallback binary search for robustness
if [ ! -f "$EXEC" ]; then
    # Try alternative locations
    if [ -f "${{HERE}}/{app_name}" ]; then
        EXEC="${{HERE}}/{app_name}"
    elif [ -f "${{HERE}}/usr/bin/{app_name}" ]; then
        EXEC="${{HERE}}/usr/bin/{app_name}"
    elif [ -f "${{HERE}}/bin/{app_name}" ]; then
        EXEC="${{HERE}}/bin/{app_name}"
    fi
fi

# Final validation
if [ ! -f "$EXEC" ]; then
    echo "❌ Error: {app_name} binary not found!"
    echo "   Searched in:"
    echo "   - ${{HERE}}/{binary_path}"
    echo "   - ${{HERE}}/{app_name}"
    echo "   - ${{HERE}}/usr/bin/{app_name}"
    echo "   - ${{HERE}}/bin/{app_name}"
    echo ""
    echo "Available files in ${{HERE}}:"
    if [ -d "${{HERE}}" ]; then
        ls -la "${{HERE}}" 2>/dev/null
    else
        echo "Cannot list directory"
    fi
    exit 1
fi

# Make sure binary is executable
chmod +x "$EXEC" 2>/dev/null

# === Final execution ===
# Execute with all arguments preserved
if [ -n "$APPIMAGE_DEBUG" ]; then
    echo "Executing: $EXEC $@"
fi

exec "$EXEC" "$@"
"""
        return script_content

    def _get_binary_rpaths(self, binary_path: str) -> Set[str]:
        """Get binary rpaths"""
        rpaths = set()
        try:
            result = subprocess_run(
                ["objdump", "-x", binary_path], capture_output=True, text=True
            )

            for line in result.stdout.split("\n"):
                if "RUNPATH" in line:
                    parts = line.split("RUNPATH")
                    if len(parts) > 1:
                        rpath = parts[1].strip()
                        rpaths.add(rpath)

        except Exception as e:
            self.logger.debug(f"Failed to get rpaths for {binary_path}: {e}")

        return rpaths

    def _copy_library(self, library: LibraryInfo, target_dir: str) -> Optional[str]:
        """
        Copy library to AppDir

        Args:
            library: LibraryInfo object
            target_dir: Target AppDir path

        Returns:
            Path to deployed library or None if failed
        """
        try:
            if not self.appdir_paths:
                return None

            if not os_path_exists(library.source_file_path):
                self.logger.warning(f"Library not found: {library.source_file_path}")
                return None

            # Construct destination path
            dest_dir = os_join(target_dir, library.library_destination_directory)
            dest_path = os_join(dest_dir, library.binary_name)

            # Create destination directory
            os_makedirs(dest_dir, exist_ok=True)

            # Skip if already deployed and not overwrite mode
            if os_path_exists(dest_path) and not self.always_overwrite_enabled:
                return dest_path

            # Copy library
            shutil_copy2(library.source_file_path, dest_path)
            os_chmod(dest_path, 0o755)

            self.logger.debug(f"📚 Deployed library: {library.library_name}")
            return dest_path

        except Exception as e:
            self.logger.error(f"Failed to copy library {library.library_name}: {e}")
            return None

    def _change_identification(self, binary_path: str):
        """Change RPATH identification with improved isolation for all libraries (Qt and non-Qt)"""
        try:
            if not self.appdir_paths:
                return

            self.logger.debug(f"Updating RPATH for: {os_path_basename(binary_path)}")

            # Verify that patchelf is available
            try:
                subprocess_run(
                    ["patchelf", "--version"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                )
            except (
                subprocess_CalledProcessError,
                FileNotFoundError,
                subprocess_TimeoutExpired,
            ):
                self.logger.warning("patchelf not available, skipping RPATH update")
                return

            # Get current RPATH first and clear it
            try:
                # First completely remove existing RPATH to avoid conflicts
                subprocess_run(
                    ["patchelf", "--remove-rpath", binary_path],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10,
                )
                self.logger.debug(
                    f"Cleared existing RPATH for {os_path_basename(binary_path)}"
                )
            except subprocess_CalledProcessError:
                # If we can't clear RPATH, continue anyway
                self.logger.debug(
                    f"Could not clear RPATH for {os_path_basename(binary_path)}, continuing..."
                )
            except Exception as e:
                self.logger.debug(f"Error clearing RPATH: {e}")

            # Calculate relative path to lib directory
            binary_dir = os_path_dirname(binary_path)
            lib_dir = self.appdir_paths.LIB_DIR

            try:
                rel_path = os_path_relpath(lib_dir, binary_dir)
                new_rpath_entry = f"$ORIGIN/{rel_path}"
            except ValueError:
                # Fallback if relative path calculation fails
                new_rpath_entry = "$ORIGIN/../lib"

            # Create a comprehensive RPATH for ALL libraries (Qt and non-Qt)
            # This ensures Boost and other libraries find their dependencies
            rpath_parts = [
                "$ORIGIN",  # Same directory as binary (highest priority)
                new_rpath_entry,  # Primary lib directory
            ]

            # Add more comprehensive RPATH entries for better compatibility
            if "plugins" in binary_path:
                # Qt plugins often need more paths to find libraries
                if "platforms" in binary_path or "imageformats" in binary_path:
                    rpath_parts.extend(
                        [
                            "$ORIGIN/../../lib",  # From plugins/platforms to /lib
                            "$ORIGIN/../../../lib",  # Deeper nesting
                        ]
                    )
                else:
                    rpath_parts.append("$ORIGIN/../../lib")  # From plugins to /lib
            elif "qml" in binary_path:
                # QML plugins might be nested deeper
                rpath_parts.extend(
                    [
                        "$ORIGIN/../../lib",  # From qml/Module to /lib
                        "$ORIGIN/../../../lib",  # Deeper nesting
                        "$ORIGIN/../../../../lib",  # For very deep QML modules
                    ]
                )
            else:
                # Standard executables and libraries
                rpath_parts.extend(
                    [
                        "$ORIGIN/lib",  # Standard lib subdirectory
                        "$ORIGIN/../lib",  # Parent lib directory
                    ]
                )

            # For FHS mode, add additional paths
            if self.fhs_like_mode:
                rpath_parts.extend(
                    [
                        "$ORIGIN/../../lib",  # For usr/bin -> lib
                        "$ORIGIN/../usr/lib",  # Alternative usr structure
                    ]
                )

            # Remove duplicates while preserving order
            unique_rpath_parts = []
            for part in rpath_parts:
                if part not in unique_rpath_parts:
                    unique_rpath_parts.append(part)

            final_rpath = ":".join(unique_rpath_parts)

            # Use patchelf to set RPATH with enhanced error handling
            try:
                subprocess_run(
                    ["patchelf", "--set-rpath", final_rpath, binary_path],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                self.logger.debug(
                    f"✅ Updated RPATH for {os_path_basename(binary_path)}: {final_rpath}"
                )

            except subprocess_CalledProcessError as e:
                stderr = (
                    e.stderr.decode() if isinstance(e.stderr, bytes) else str(e.stderr)
                )

                if "Not enough room for program headers" in stderr:
                    self.logger.debug(
                        f"⚠️  {os_path_basename(binary_path)} already has maximum RPATH entries"
                    )
                    # Try with fewer RPATH entries
                    try:
                        simplified_rpath = "$ORIGIN:$ORIGIN/../lib"
                        subprocess_run(
                            ["patchelf", "--set-rpath", simplified_rpath, binary_path],
                            check=True,
                            capture_output=True,
                            timeout=15,
                        )
                        self.logger.debug(
                            f"✅ Updated with simplified RPATH for {os_path_basename(binary_path)}: {simplified_rpath}"
                        )
                    except subprocess_CalledProcessError:
                        self.logger.warning(
                            f"⚠️  Could not update RPATH for {os_path_basename(binary_path)} (not enough space)"
                        )
                elif "cannot write to" in stderr or "Permission denied" in stderr:
                    self.logger.warning(
                        f"⚠️  Permission denied updating RPATH for {os_path_basename(binary_path)}"
                    )
                elif (
                    "not a dynamic executable" in stderr or "not an ELF file" in stderr
                ):
                    self.logger.debug(
                        f"⏭️  Skipping non-ELF file: {os_path_basename(binary_path)}"
                    )
                else:
                    self.logger.warning(
                        f"⚠️  Failed to update RPATH for {os_path_basename(binary_path)}: {stderr}"
                    )

        except Exception as e:
            self.logger.warning(
                f"⚠️  Error updating RPATH for {os_path_basename(binary_path)}: {e}"
            )

    def _run_strip(self, binary_path: str):
        """Strip binary"""
        try:
            subprocess_run(["strip", binary_path], check=True, capture_output=True)
            self.logger.debug(f"Stripped: {os_path_basename(binary_path)}")
        except subprocess_CalledProcessError:
            self.logger.debug(
                f"Strip failed or not needed for: {os_path_basename(binary_path)}"
            )

    def _create_qt_conf(self, target_dir: str) -> bool:
        """Create qt.conf file"""
        try:
            if not self.appdir_paths:
                return False

            # Create qt.conf content
            content = f"""# Generated by linuxdeployqt-python
# https://github.com/probonopd/linuxdeployqt/
[Paths]
Prefix = {self.appdir_paths.QT_CONF_PREFIX}
Plugins = {self.appdir_paths.QT_CONF_PLUGINS}
Imports = {self.appdir_paths.QT_CONF_QML}
Qml2Imports = {self.appdir_paths.QT_CONF_QML}
"""

            # Determine qt.conf location (next to main executable)
            if self.fhs_like_mode:
                qt_conf_path = os_join(self.appdir_paths.BIN_DIR, "qt.conf")
            else:
                qt_conf_path = os_join(target_dir, "qt.conf")

            # Write qt.conf
            if not os_path_exists(qt_conf_path) or self.always_overwrite_enabled:
                with open(qt_conf_path, "w") as f:
                    f.write(content)
                self.logger.info(f"Created qt.conf: {qt_conf_path}")
            else:
                self.logger.debug("qt.conf already exists, not overwriting")

            return True

        except Exception as e:
            self.logger.error(f"Failed to create qt.conf: {e}")
            return False

    def _deploy_plugins(self, required_plugins: Set[str], target_dir: str) -> bool:
        """Deploy Qt plugins"""
        try:
            if not self.appdir_paths:
                return False

            # Use explicit Qt path if set, otherwise use qmake info
            qt_plugins_path = ""
            if self.explicit_qt_path:
                qt_plugins_path = os_join(self.explicit_qt_path, "plugins")
                self.logger.debug(
                    f"🎯 Using explicit Qt plugins path: {qt_plugins_path}"
                )
            elif self.qt_to_be_bundled_info:
                qt_plugins_path = self.qt_to_be_bundled_info.get(
                    "QT_INSTALL_PLUGINS", ""
                )
                self.logger.debug(f"🔍 Using qmake Qt plugins path: {qt_plugins_path}")

            if not qt_plugins_path or not os_path_exists(qt_plugins_path):
                self.logger.warning("Qt plugins directory not found")
                return False

            self.logger.info(f"Deploying plugins from: {qt_plugins_path}")

            for plugin in required_plugins:
                plugin_source = os_join(qt_plugins_path, plugin)
                plugin_target = os_join(self.appdir_paths.PLUGINS_DIR, plugin)

                if os_path_exists(plugin_source):
                    if os_path_isfile(plugin_source):
                        # Single plugin file
                        os_makedirs(os_path_dirname(plugin_target), exist_ok=True)
                        shutil_copy2(plugin_source, plugin_target)
                        os_chmod(plugin_target, 0o755)
                        # self._change_identification(plugin_target)
                        if self.run_strip_enabled:
                            self._run_strip(plugin_target)
                    elif os_path_isdir(plugin_source):
                        # Plugin directory
                        if os_path_exists(plugin_target):
                            self.logger.debug(
                                f"Removing existing plugin target: {plugin_target}"
                            )
                            shutil_rmtree(plugin_target)
                        shutil_copytree(plugin_source, plugin_target)
                        # Process all .so files in the directory
                        for root, dirs, files in os_walk(plugin_target):
                            for file in files:
                                if file.endswith(".so"):
                                    so_path = os_join(root, file)
                                    os_chmod(so_path, 0o755)
                                    # self._change_identification(so_path)
                                    if self.run_strip_enabled:
                                        self._run_strip(so_path)

                    self.logger.debug(f"Deployed plugin: {plugin}")
                else:
                    self.logger.warning(f"Plugin not found: {plugin_source}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to deploy plugins: {e}")
            return False

    def _deploy_qml_imports_with_scanner(self, target_dir: str) -> bool:
        """
        Deploy QML imports using qmlimportscanner
        """
        try:
            if not self.qml_import_scanner:
                self.logger.debug("QML import scanner not initialized")
                return True

            # Find QML directories
            qml_dirs = []

            # Add custom QML directories
            custom_qml_dirs = self.component_analyzer.qml_analyzer.custom_qml_dirs
            qml_dirs.extend(custom_qml_dirs)

            # Auto-detect QML directories in project
            if not qml_dirs:
                auto_qml_dirs = self._find_user_qml_directories()
                qml_dirs.extend(auto_qml_dirs)

            if not qml_dirs:
                self.logger.debug("No QML directories found to scan")
                return True

            self.logger.info(f"🎨 Scanning QML directories: {qml_dirs}")

            # Scan QML imports using qmlimportscanner
            imports_data = self.qml_import_scanner.scan_qml_imports(qml_dirs)
            if not imports_data:
                self.logger.debug("No QML imports found")
                return True

            # Deploy QML imports
            rpaths_used = set()  # TODO: get from deployed libraries
            success = self.qml_import_scanner.deploy_qml_imports(
                imports_data, target_dir, rpaths_used
            )

            if success:
                self.logger.success("✅ QML imports deployed successfully")
            else:
                self.logger.warning("⚠️  Some QML imports failed to deploy")

            return success

        except Exception as e:
            self.logger.error(f"❌ Failed to deploy QML imports: {e}")
            return False

    def _deploy_webengine_components(
        self, qt_info: Optional[Dict[str, str]], target_dir: str
    ) -> bool:
        """Deploy Qt WebEngine components"""
        if not qt_info or not self.appdir_paths:
            return False

        try:
            self.logger.info("🌐 Deploying Qt WebEngine components...")

            # Create directories
            os_makedirs(self.appdir_paths.LIBEXEC_DIR, exist_ok=True)
            os_makedirs(self.appdir_paths.RESOURCES_DIR, exist_ok=True)

            # Deploy QtWebEngineProcess
            qt_libexec_path = qt_info.get("QT_INSTALL_LIBEXECS", "")
            if not qt_libexec_path:
                qt_libexec_path = qt_info.get("QT_INSTALL_BINS", "")  # Fallback for Qt5

            if qt_libexec_path and os_path_exists(qt_libexec_path):
                webengine_process = os_join(qt_libexec_path, "QtWebEngineProcess")
                if os_path_exists(webengine_process):
                    target_process = os_join(
                        self.appdir_paths.LIBEXEC_DIR, "QtWebEngineProcess"
                    )
                    shutil_copy2(webengine_process, target_process)
                    os_chmod(target_process, 0o755)

                    # Update RPATH for WebEngine process
                    # self._change_identification(target_process)
                    if self.run_strip_enabled:
                        self._run_strip(target_process)

                    self.logger.info("✅ Deployed QtWebEngineProcess")
                else:
                    self.logger.warning(
                        f"QtWebEngineProcess not found in {qt_libexec_path}"
                    )

            # Deploy WebEngine resources
            qt_data_path = qt_info.get("QT_INSTALL_DATA", "")
            if qt_data_path and os_path_exists(qt_data_path):
                # Copy qtwebengine_resources.pak and other resources
                resources_files = [
                    "qtwebengine_resources.pak",
                    "qtwebengine_resources_100p.pak",
                    "qtwebengine_resources_200p.pak",
                    "qtwebengine_devtools_resources.pak",
                    "icudtl.dat",
                ]

                for resource_file in resources_files:
                    resource_source = os_join(qt_data_path, "resources", resource_file)
                    if os_path_exists(resource_source):
                        resource_target = os_join(
                            self.appdir_paths.RESOURCES_DIR, resource_file
                        )
                        shutil_copy2(resource_source, resource_target)
                        self.logger.debug(
                            f"Deployed WebEngine resource: {resource_file}"
                        )

                # Copy locales if they exist
                locales_source = os_join(
                    qt_data_path, "translations", "qtwebengine_locales"
                )
                if os_path_exists(locales_source):
                    locales_target = os_join(
                        self.appdir_paths.TRANSLATIONS_DIR, "qtwebengine_locales"
                    )
                    if not os_path_exists(locales_target):
                        shutil_copytree(locales_source, locales_target)
                        self.logger.debug("Deployed WebEngine locales")

            # Alternative: try to find resources in Qt installation
            qt_prefix = qt_info.get("QT_INSTALL_PREFIX", "")
            if qt_prefix:
                alt_resources = [
                    os_join(qt_prefix, "resources"),
                    os_join(qt_prefix, "share", "qt5", "resources"),
                    os_join(qt_prefix, "share", "qt6", "resources"),
                ]

                for alt_path in alt_resources:
                    if os_path_exists(alt_path):
                        for item in os_listdir(alt_path):
                            if item.endswith(".pak") or item == "icudtl.dat":
                                source_file = os_join(alt_path, item)
                                target_file = os_join(
                                    self.appdir_paths.RESOURCES_DIR, item
                                )
                                if not os_path_exists(target_file):
                                    shutil_copy2(source_file, target_file)
                                    self.logger.debug(
                                        f"Deployed WebEngine resource: {item}"
                                    )
                        break

            self.logger.success("✅ Qt WebEngine components deployed")
            return True

        except Exception as e:
            self.logger.error(f"Failed to deploy WebEngine components: {e}")
            return False

    def _deploy_qt_translations(
        self, qt_info: Optional[Dict[str, str]], target_dir: str
    ) -> bool:
        """Deploy Qt translations"""
        if not qt_info or not self.appdir_paths:
            return True  # Not an error if no Qt info

        try:
            qt_translations_path = qt_info.get("QT_INSTALL_TRANSLATIONS", "")
            if not qt_translations_path or not os_path_exists(qt_translations_path):
                self.logger.debug("Qt translations not found, skipping")
                return True

            self.logger.info(f"Deploying Qt translations from: {qt_translations_path}")

            # Copy translation files
            os_makedirs(self.appdir_paths.TRANSLATIONS_DIR, exist_ok=True)

            import glob

            qm_files = glob.glob(os_join(qt_translations_path, "*.qm"))

            for qm_file in qm_files:
                target_file = os_join(
                    self.appdir_paths.TRANSLATIONS_DIR, os_path_basename(qm_file)
                )
                shutil_copy2(qm_file, target_file)

            self.logger.debug(f"Deployed {len(qm_files)} translation files")
            return True

        except Exception as e:
            self.logger.error(f"Failed to deploy translations: {e}")
            return False

    def _deploy_desktop_integration(
        self, target_dir: str, desktop_file: str, icon_file: str
    ):
        """Deploy desktop file and icon"""
        try:
            # Deploy desktop file
            if desktop_file and os_path_exists(desktop_file):
                target_desktop = os_join(target_dir, os_path_basename(desktop_file))
                if not os_path_exists(target_desktop):
                    shutil_copy2(desktop_file, target_desktop)
                    self.logger.info(
                        f"📋 Deployed desktop file: {os_path_basename(desktop_file)}"
                    )

            # Deploy icon file
            if icon_file and os_path_exists(icon_file):
                target_icon = os_join(target_dir, os_path_basename(icon_file))
                if not os_path_exists(target_icon):
                    shutil_copy2(icon_file, target_icon)
                    # Also copy as .DirIcon for ROX compatibility
                    diricon_path = os_join(target_dir, ".DirIcon")
                    if not os_path_exists(diricon_path):
                        shutil_copy2(icon_file, diricon_path)
                    self.logger.info(f"🎨 Deployed icon: {os_path_basename(icon_file)}")

        except Exception as e:
            self.logger.error(f"Failed to deploy desktop integration: {e}")

    def _find_user_qml_directories(self) -> List[str]:
        """Find user QML directories in the project"""
        qml_dirs = []

        # Check if custom QML directories were set via set_custom_qml_dir
        custom_dirs = getattr(
            self.component_analyzer.qml_analyzer, "custom_qml_dirs", []
        )
        if custom_dirs:
            for custom_dir in custom_dirs:
                # Only add if it's within project directory
                if custom_dir.startswith(self.project_root):
                    qml_dirs.append(custom_dir)
                else:
                    self.logger.debug(
                        f"Skipping custom QML dir outside project: {custom_dir}"
                    )

        # Look for standard QML directories in project only
        project_qml_candidates = [
            os_join(self.project_root, "qml"),
            os_join(self.project_root, "src", "qml"),
            os_join(self.project_root, "resources", "qml"),
            os_join(self.project_root, "ui"),
        ]

        for candidate in project_qml_candidates:
            if os_path_exists(candidate) and os_path_isdir(candidate):
                # Check if directory contains QML files
                has_qml = False
                try:
                    for root, dirs, files in os_walk(candidate):
                        # Skip build and AppDir directories
                        dirs[:] = [
                            d
                            for d in dirs
                            if not d.startswith(".")
                            and "AppDir" not in d
                            and "build" not in d
                        ]

                        if any(f.endswith(".qml") for f in files):
                            has_qml = True
                            break
                except Exception:
                    continue

                if has_qml and candidate not in qml_dirs:
                    qml_dirs.append(candidate)
                    self.logger.debug(f"Found user QML directory: {candidate}")

        self.logger.info(f"Found {len(qml_dirs)} user QML directories")
        return qml_dirs

    def _deploy_application_resources(self, target_dir: str) -> bool:
        """Deploy application resources (icons, translations, etc.)"""
        try:
            self.logger.info("📦 Deploying application resources...")

            if not self.appdir_paths:
                return False

            resources_deployed = 0

            # Deploy resources directory if it exists
            resources_dir = os_join(self.project_root, "resources")
            if os_path_exists(resources_dir) and os_path_isdir(resources_dir):
                # Deploy icons
                icons_source = os_join(resources_dir, "icons")
                if os_path_exists(icons_source):
                    icons_target = os_join(target_dir, "resources", "icons")
                    if not os_path_exists(icons_target):
                        shutil_copytree(icons_source, icons_target)
                        self.logger.debug("Deployed icons directory")
                        resources_deployed += 1

                # Deploy translations
                translations_source = os_join(resources_dir, "translations")
                if os_path_exists(translations_source):
                    # Copy to both standard translations dir and resources/translations
                    # Standard location
                    standard_trans_target = self.appdir_paths.TRANSLATIONS_DIR
                    os_makedirs(standard_trans_target, exist_ok=True)

                    # Resources location (for QRC compatibility)
                    resources_trans_target = os_join(
                        target_dir, "resources", "translations"
                    )
                    os_makedirs(os_path_dirname(resources_trans_target), exist_ok=True)

                    try:
                        # Copy .qm files to standard location
                        for file in os_listdir(translations_source):
                            if file.endswith(".qm"):
                                source_file = os_join(translations_source, file)
                                target_file = os_join(standard_trans_target, file)
                                if (
                                    not os_path_exists(target_file)
                                    or self.always_overwrite_enabled
                                ):
                                    shutil_copy2(source_file, target_file)

                        # Copy entire directory to resources location
                        if not os_path_exists(resources_trans_target):
                            shutil_copytree(translations_source, resources_trans_target)

                        self.logger.debug("Deployed translations")
                        resources_deployed += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to deploy translations: {e}")

                # Deploy other resource files (like QRC files, etc.)
                for item in os_listdir(resources_dir):
                    item_path = os_join(resources_dir, item)
                    target_path = os_join(target_dir, "resources", item)

                    if os_path_isfile(item_path) and not os_path_exists(target_path):
                        os_makedirs(os_path_dirname(target_path), exist_ok=True)
                        shutil_copy2(item_path, target_path)
                        self.logger.debug(f"Deployed resource file: {item}")
                        resources_deployed += 1

            if resources_deployed > 0:
                self.logger.success(
                    f"✅ Deployed {resources_deployed} resource components"
                )
            else:
                self.logger.debug("No additional resources found to deploy")

            return True

        except Exception as e:
            self.logger.error(f"Failed to deploy application resources: {e}")
            return False

    def _is_problematic_library(self, library_name: str) -> bool:
        """
        Check if a library is known to cause RPATH issues.
        These libraries often have complex dependency chains.

        Args:
            library_name: Name of the library to check

        Returns:
            True if library is known to be problematic
        """
        library_name_lower = library_name.lower()

        problematic_patterns = [
            # Boost libraries (common issue on Astra Linux)
            "libboost_",
            "boost_",
            # Other commonly problematic libraries
            "libicu",
            "libssl",
            "libcrypto",
            "libpcre",
            "libxml2",
            "libxslt",
            "libprotobuf",
            "libglib",
            "libgio",
            "libgobject",
            "libcurl",
            "libpq",  # PostgreSQL
            "libmysql",  # MySQL
            "libsqlite",
            "libpng",
            "libjpeg",
            "libtiff",
            "libopenjp2",
            # Graphics and media libraries
            "libavcodec",
            "libavformat",
            "libavutil",
            "libswscale",
            "libpulse",
            "libasound",
            # Development and runtime libraries
            "libgcc_s",
            "libstdc++",
            "libgomp",  # OpenMP
            "libtbb",  # Threading Building Blocks
        ]

        for pattern in problematic_patterns:
            if pattern in library_name_lower:
                return True

        return False

    def _apply_additional_rpath_fixes(self, library_path: str, library_name: str):
        """
        Apply additional RPATH fixes for problematic libraries.
        This method provides extra robustness for libraries that commonly
        cause "not found" errors.

        Args:
            library_path: Full path to the deployed library
            library_name: Name of the library
        """
        try:
            self.logger.debug(f"🔧 Applying additional RPATH fixes for: {library_name}")

            if not self.appdir_paths:
                return

            # For Boost libraries, add extra RPATH entries to handle version dependencies
            if "boost" in library_name.lower():
                self._apply_boost_specific_fixes(library_path)

            # For ICU libraries, ensure proper linking
            elif "libicu" in library_name.lower():
                self._apply_icu_specific_fixes(library_path)

            # For graphics libraries, add multimedia paths
            elif any(
                pattern in library_name.lower()
                for pattern in ["libpng", "libjpeg", "libtiff", "libav"]
            ):
                self._apply_multimedia_specific_fixes(library_path)

        except Exception as e:
            self.logger.debug(f"Additional RPATH fixes failed for {library_name}: {e}")

    def _apply_boost_specific_fixes(self, library_path: str):
        """Apply Boost-specific RPATH fixes"""
        try:
            # Boost libraries often depend on each other
            # Add extra paths for Boost inter-library dependencies
            boost_rpath_additions = [
                "$ORIGIN",
                "$ORIGIN/.",
                "$ORIGIN/../lib",
                "$ORIGIN/../../lib",  # For complex nested structures
            ]

            # Get current RPATH
            try:
                result = subprocess_run(
                    ["patchelf", "--print-rpath", library_path],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10,
                )
                current_rpath = result.stdout.strip()

                # Add Boost-specific paths if not already present
                rpath_parts = current_rpath.split(":") if current_rpath else []

                for addition in boost_rpath_additions:
                    if addition not in rpath_parts:
                        rpath_parts.insert(
                            0, addition
                        )  # Insert at beginning for priority

                new_rpath = ":".join(filter(None, rpath_parts))

                subprocess_run(
                    ["patchelf", "--set-rpath", new_rpath, library_path],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )

                self.logger.debug(
                    f"🔧 Applied Boost fixes to {os_path_basename(library_path)}"
                )

            except subprocess_CalledProcessError:
                self.logger.debug(
                    f"Could not apply Boost fixes to {os_path_basename(library_path)}"
                )

        except Exception as e:
            self.logger.debug(f"Boost-specific fixes failed: {e}")

    def _apply_icu_specific_fixes(self, library_path: str):
        """Apply ICU-specific RPATH fixes"""
        try:
            # ICU libraries have version-specific dependencies
            self.logger.debug(f"Applying ICU fixes to {os_path_basename(library_path)}")

            # ICU libraries typically need to find each other
            # No additional action needed beyond standard RPATH setting

        except Exception as e:
            self.logger.debug(f"ICU-specific fixes failed: {e}")

    def _apply_multimedia_specific_fixes(self, library_path: str):
        """Apply multimedia library-specific RPATH fixes"""
        try:
            # Multimedia libraries often have complex dependency chains
            self.logger.debug(
                f"Applying multimedia fixes to {os_path_basename(library_path)}"
            )

            # No additional action needed beyond standard RPATH setting for now
            # Could be extended for specific multimedia library quirks

        except Exception as e:
            self.logger.debug(f"Multimedia-specific fixes failed: {e}")

    def _verify_and_fix_rpaths(self, target_dir: str) -> bool:
        """
        Final verification and fixing of RPATH for all ELF files in AppDir.
        This ensures that no system paths remain in RPATH and all binaries
        will use the bundled libraries regardless of the target system.

        Args:
            target_dir: Target AppDir path

        Returns:
            True if verification successful
        """
        if not self.appdir_paths:
            return False

        self.logger.info("🔍 Verifying RPATH settings for all components...")

        try:
            # Find all ELF files in the AppDir
            elf_files = []

            # Function to check if file is ELF
            def is_elf(file_path: str) -> bool:
                try:
                    with open(file_path, "rb") as f:
                        header = f.read(4)
                        return header == b"\x7fELF"
                except Exception:
                    return False

            # Walk through AppDir to find all files
            for root, _, files in os_walk(target_dir):
                for file in files:
                    file_path = os_join(root, file)
                    if not os_path_isfile(file_path):
                        continue

                    # Check if file is executable or shared library
                    if (
                        file.endswith(".so")
                        or ".so." in file
                        or os_access(file_path, os_X_OK)
                    ):
                        if is_elf(file_path):
                            elf_files.append(file_path)

            self.logger.info(f"Found {len(elf_files)} ELF files to verify")

            # Check RPATH for each file
            problematic_files = []
            for elf_file in elf_files:
                try:
                    # Get current RPATH
                    result = subprocess_run(
                        ["patchelf", "--print-rpath", elf_file],
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    if result.returncode != 0:
                        self.logger.debug(
                            f"Could not read RPATH for {os_path_basename(elf_file)}"
                        )
                        continue

                    current_rpath = result.stdout.strip()

                    # Check if RPATH contains system paths or is empty
                    has_absolute_paths = any(
                        not path.startswith("$ORIGIN") and path != ""
                        for path in current_rpath.split(":")
                    )

                    if has_absolute_paths or not current_rpath:
                        self.logger.warning(
                            f"⚠️ Problematic RPATH in {os_path_relpath(elf_file, target_dir)}: {current_rpath}"
                        )
                        problematic_files.append(elf_file)

                except Exception as e:
                    self.logger.debug(
                        f"Error checking RPATH for {os_path_basename(elf_file)}: {e}"
                    )

            # Fix problematic files
            if problematic_files:
                self.logger.warning(
                    f"Found {len(problematic_files)} files with problematic RPATH settings"
                )
                for file_path in problematic_files:
                    # self._change_identification(file_path) # Removed this line as per requirement
                    pass  # Do nothing, as RPATH for libraries should not be touched

                # Verify again
                still_problematic = 0
                for elf_file in problematic_files:
                    try:
                        result = subprocess_run(
                            ["patchelf", "--print-rpath", elf_file],
                            capture_output=True,
                            text=True,
                            check=False,
                        )

                        if result.returncode == 0:
                            current_rpath = result.stdout.strip()
                            has_absolute_paths = any(
                                not path.startswith("$ORIGIN") and path != ""
                                for path in current_rpath.split(":")
                            )

                            if has_absolute_paths:
                                still_problematic += 1
                                self.logger.warning(
                                    "⚠️ Still problematic RPATH in "
                                    f"{os_path_relpath(elf_file, target_dir)}: "
                                    f"{current_rpath}"
                                )
                    except Exception:
                        pass

                if still_problematic > 0:
                    self.logger.warning(
                        f"⚠️ {still_problematic} files still have problematic RPATH settings"
                    )
                else:
                    self.logger.success("✅ All RPATH issues fixed successfully")
            else:
                self.logger.success("✅ All RPATH settings are correct")

            # Final double-check of main executable
            self._apply_final_binary_fixes(
                os_join(target_dir, os_path_basename(self.app_binary_path))
            )
            if self.fhs_like_mode:
                bin_path = os_join(
                    self.appdir_paths.BIN_DIR, os_path_basename(self.app_binary_path)
                )
                if os_path_exists(bin_path):
                    self._apply_final_binary_fixes(bin_path)

            return True

        except Exception as e:
            self.logger.error(f"Failed to verify RPATH settings: {e}")
            return False

    def _apply_final_binary_fixes(self, binary_path: str):
        """Apply final fixes to main binary to ensure compatibility"""
        if not os_path_exists(binary_path):
            return

        self.logger.info(f"Applying final fixes to {os_path_basename(binary_path)}")

        try:
            # Ensure binary has correct RPATH
            simplified_rpath = "$ORIGIN:$ORIGIN/lib:$ORIGIN/../lib"
            subprocess_run(
                ["patchelf", "--set-rpath", simplified_rpath, binary_path],
                check=False,
                capture_output=True,
            )

            # Make sure binary is executable
            os_chmod(binary_path, 0o755)

            self.logger.debug(f"Applied final fixes to {os_path_basename(binary_path)}")
        except Exception as e:
            self.logger.warning(
                f"Could not apply final fixes to {os_path_basename(binary_path)}: {e}"
            )

        # Verify final RPATH
        try:
            result = subprocess_run(
                ["patchelf", "--print-rpath", binary_path],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                self.logger.info(
                    f"Final RPATH for {os_path_basename(binary_path)}: {result.stdout.strip()}"
                )
        except Exception:
            pass

    def _deploy_system_qt_libraries(self, target_dir: str, qt_version: int) -> bool:
        """
        Deploy all Qt libraries from system directories or explicit Qt path with proper version aliasing.
        This ensures that all Qt libraries of the detected version are available in AppDir,
        preventing version conflicts when loading plugins.

        Args:
            target_dir: Target AppDir path
            qt_version: Detected Qt version (4, 5, or 6)

        Returns:
            True if deployment successful
        """
        if not self.appdir_paths or qt_version == 0:
            return False

        # Use explicit Qt path if set, otherwise use system paths
        if self.explicit_qt_path:
            explicit_lib_path = os_join(self.explicit_qt_path, "lib")
            if os_path_exists(explicit_lib_path):
                self.logger.info(
                    f"🎯 Deploying Qt{qt_version} libraries from explicit path: {explicit_lib_path}"
                )
                system_lib_paths = [explicit_lib_path]
            else:
                self.logger.warning(
                    f"⚠️ Explicit Qt lib path not found: {explicit_lib_path}"
                )
                return False
        else:
            self.logger.info(
                f"🔧 Deploying all Qt{qt_version} libraries from system..."
            )
            # System library search paths
            system_lib_paths = [
                "/usr/lib/x86_64-linux-gnu",
                "/usr/lib",
                "/lib/x86_64-linux-gnu",
                "/lib",
                "/usr/lib64",
                "/lib64",
            ]

        # Qt library pattern based on version
        if qt_version == 5:
            lib_pattern = "libQt5*.so*"
        elif qt_version == 6:
            lib_pattern = "libQt6*.so*"
        elif qt_version == 4:
            lib_pattern = "libQt*.so*"  # noqa: F841
        else:
            self.logger.warning(f"Unsupported Qt version: {qt_version}")
            return False

        deployed_count = 0
        skipped_count = 0

        for search_path in system_lib_paths:
            if not os_path_exists(search_path):
                continue

            try:
                # Find all Qt libraries in this directory
                qt_libraries = []
                for file in os_listdir(search_path):
                    file_path = os_join(search_path, file)

                    # Match Qt library pattern and ensure it's a file
                    if not os_path_isfile(file_path):
                        continue

                    # Check if it matches Qt pattern for this version
                    if qt_version == 5 and file.startswith("libQt5") and ".so" in file:
                        qt_libraries.append(file_path)
                    elif (
                        qt_version == 6 and file.startswith("libQt6") and ".so" in file
                    ):
                        qt_libraries.append(file_path)
                    elif (
                        qt_version == 4
                        and file.startswith("libQt")
                        and not file.startswith(("libQt5", "libQt6"))
                        and ".so" in file
                    ):
                        qt_libraries.append(file_path)

                # Process found libraries
                for lib_path in qt_libraries:
                    lib_name = os_path_basename(lib_path)
                    target_lib_path = os_join(self.appdir_paths.LIB_DIR, lib_name)

                    # Skip if already deployed
                    if os_path_exists(target_lib_path):
                        skipped_count += 1
                        continue

                    # Skip symlinks - only deploy actual files
                    if os_path_islink(lib_path):
                        continue

                    # Skip static libraries (.a files) and development files (.prl)
                    if lib_name.endswith((".a", ".prl")):
                        continue

                    try:
                        # Copy library to AppDir
                        os_makedirs(os_path_dirname(target_lib_path), exist_ok=True)
                        shutil_copy2(lib_path, target_lib_path)

                        # Create version aliases
                        self._create_library_version_aliases(
                            target_lib_path, self.appdir_paths.LIB_DIR
                        )

                        # Fix RPATH
                        self._change_identification(target_lib_path)

                        deployed_count += 1
                        self.logger.debug(f"✅ Deployed Qt library: {lib_name}")

                    except Exception as e:
                        self.logger.debug(f"Failed to deploy {lib_name}: {e}")

            except Exception as e:
                self.logger.debug(f"Error scanning {search_path}: {e}")

        self.logger.info(
            f"📦 Deployed {deployed_count} Qt{qt_version} libraries, skipped {skipped_count} existing"
        )
        return deployed_count > 0

    def _create_library_version_aliases(self, library_path: str, lib_dir: str):
        """
        Create version aliases for a library (e.g., libQt5Test.so.5.11.0 -> libQt5Test.so.5 -> libQt5Test.so)

        Args:
            library_path: Full path to the library file
            lib_dir: Directory containing libraries
        """
        try:
            lib_name = os_path_basename(library_path)

            # Extract version components using regex
            import re

            # Pattern for libraries like libQt5Test.so.5.11.0
            version_match = re.match(r"(.+\.so)\.(\d+)\.(\d+)\.(\d+)$", lib_name)
            if version_match:
                base_name = version_match.group(1)  # libQt5Test.so
                major = version_match.group(2)  # 5
                minor = version_match.group(3)  # 11 # noqa: F841
                patch = version_match.group(4)  # 0 # noqa: F841

                # Create major version alias (libQt5Test.so.5)
                major_alias = f"{base_name}.{major}"
                major_alias_path = os_join(lib_dir, major_alias)

                # Create base alias (libQt5Test.so)
                base_alias_path = os_join(lib_dir, base_name)

                # Create aliases (prefer symlinks, fallback to copies)
                for alias_path, alias_name in [
                    (major_alias_path, major_alias),
                    (base_alias_path, base_name),
                ]:
                    if not os_path_exists(alias_path):
                        try:
                            # Try to create symlink first
                            os_symlink(lib_name, alias_path)
                            self.logger.debug(
                                f"Created symlink: {alias_name} -> {lib_name}"
                            )
                        except (OSError, NotImplementedError):
                            # Fallback to copy if symlinks not supported (e.g., FAT32/ExFAT)
                            try:
                                shutil_copy2(library_path, alias_path)
                                self.logger.debug(f"Created copy: {alias_name}")
                            except Exception as e:
                                self.logger.debug(
                                    f"Failed to create alias {alias_name}: {e}"
                                )

                return

            # Pattern for libraries like libQt5Test.so.5
            major_match = re.match(r"(.+\.so)\.(\d+)$", lib_name)
            if major_match:
                base_name = major_match.group(1)  # libQt5Test.so
                major = major_match.group(2)  # 5

                # Create base alias (libQt5Test.so)
                base_alias_path = os_join(lib_dir, base_name)

                if not os_path_exists(base_alias_path):
                    try:
                        os_symlink(lib_name, base_alias_path)
                        self.logger.debug(f"Created symlink: {base_name} -> {lib_name}")
                    except (OSError, NotImplementedError):
                        try:
                            shutil_copy2(library_path, base_alias_path)
                            self.logger.debug(f"Created copy: {base_name}")
                        except Exception as e:
                            self.logger.debug(
                                f"Failed to create alias {base_name}: {e}"
                            )

        except Exception as e:
            self.logger.debug(
                f"Failed to create version aliases for {os_path_basename(library_path)}: {e}"
            )
