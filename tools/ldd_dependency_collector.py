from os.path import exists as os_path_exists
from os.path import relpath as os_path_relpath
from os.path import basename as os_path_basename

from re import compile as re_compile

from subprocess import run as subprocess_run
from subprocess import CalledProcessError as subprocess_CalledProcessError

from typing import List, Set, Optional
from dataclasses import dataclass, field

from logger.logger import Logger
from .exclude_libs import should_bundle_library


@dataclass
class LibraryInfo:
    """
    Library information matching LibraryInfo class from shared.h
    """

    library_directory: str = ""
    library_name: str = ""
    library_path: str = ""
    binary_directory: str = ""
    binary_name: str = ""
    binary_path: str = ""
    source_file_path: str = ""
    library_destination_directory: str = ""
    binary_destination_directory: str = ""
    rpath_used: str = ""
    version: str = ""
    install_name: str = ""
    deployed_install_name: str = ""
    is_dylib: bool = True


@dataclass
class DylibInfo:
    """
    Dylib information matching DylibInfo class from shared.h
    """

    binary_path: str = ""


@dataclass
class LddInfo:
    """
    LDD information matching LddInfo class from shared.h
    """

    install_name: str = ""
    binary_path: str = ""
    dependencies: List[DylibInfo] = field(default_factory=list)


class LddDependencyCollector:
    """
    Collects library dependencies using ldd, matching official linuxdeployqt behavior.

    Based on findDependencyInfo() and parseLddLibraryLine() from shared.cpp
    """

    def __init__(self, log_level: str = "DEBUG"):
        self.logger = Logger(log_level, self.__class__.__name__)

        # Configuration matching shared.cpp globals
        self.bundle_all_but_core_libs = (
            False  # Default to false like original linuxdeployqt
        )
        self.bundle_everything = False
        self.qt_detected = 0
        self.qt_detection_complete = False
        self.library_search_path = []

        # Pattern for parsing ldd output (from shared.cpp)
        # Handle different ldd output formats:
        # 1. "libname.so => /path/to/lib (0x...)"
        # 2. "libname.so (0x...)" - virtual libs like linux-vdso
        # 3. "/absolute/path/to/lib (0x...)" - ld-linux
        self.ldd_pattern = re_compile(r"^.+ => (.+) \(")
        self.ldd_pattern_absolute = re_compile(r"^(\S+\.so[^\s]*)\s+\(")
        self.ldd_pattern_virtual = re_compile(r"^(\S+\.so[^\s]*)\s+\(")

    def set_bundle_mode(
        self, bundle_all_but_core_libs: bool = False, bundle_everything: bool = False
    ):
        """Set bundling mode matching shared.cpp flags"""
        self.bundle_all_but_core_libs = bundle_all_but_core_libs
        self.bundle_everything = bundle_everything

    def get_libs(self, executable_path: str) -> List[str]:
        """
        Get all library dependencies for executable.

        This is the main entry point, equivalent to calling findDependencyInfo()
        and then collecting all dependencies recursively.

        Args:
            executable_path: Path to executable to analyze

        Returns:
            List of library paths that should be bundled
        """
        try:
            self.logger.info(f"🔍 Analyzing dependencies for: {executable_path}")

            # Get initial dependency info (matches findDependencyInfo)
            ldd_info = self._find_dependency_info(executable_path)

            if not ldd_info.dependencies:
                self.logger.warning("No dependencies found")
                return []

            # Collect all libraries recursively
            all_libraries = self._collect_all_libraries([executable_path], set())

            # Filter libraries based on bundling rules
            bundled_libraries = []
            excluded_count = 0
            for lib_path in all_libraries:
                lib_name = os_path_basename(lib_path)
                if should_bundle_library(
                    lib_path, self.bundle_all_but_core_libs, self.bundle_everything
                ):
                    bundled_libraries.append(lib_path)
                    self.logger.debug(f"✅ Will bundle: {lib_name}")
                else:
                    # More detailed exclusion logging
                    from .exclude_libs import should_exclude_library

                    if should_exclude_library(lib_path):
                        self.logger.debug(f"⏭️  Excluding (blacklisted): {lib_name}")
                    else:
                        self.logger.debug(f"⏭️  Excluding (bundling rules): {lib_name}")
                        excluded_count += 1

            self.logger.info(f"📦 Found {len(bundled_libraries)} libraries to bundle")
            self.logger.info(
                f"📦 Excluded {excluded_count} libraries, because of bundling rules"
            )
            return sorted(set(bundled_libraries))

        except Exception as e:
            self.logger.error(f"Failed to analyze dependencies: {e}")
            return []

    def get_qt_libraries(
        self, executable_path: str, app_dir_path: str, rpaths: Set[str]
    ) -> List[LibraryInfo]:
        """
        Get Qt libraries with full LibraryInfo matching getQtLibraries() from shared.cpp

        Args:
            executable_path: Path to executable
            app_dir_path: AppDir path
            rpaths: Set of rpaths to use

        Returns:
            List of LibraryInfo objects
        """
        try:
            ldd_info = self._find_dependency_info(executable_path)
            libraries = []

            for dylib_info in ldd_info.dependencies:
                lib_info = self._parse_ldd_library_line(
                    dylib_info.binary_path, app_dir_path, rpaths
                )
                if lib_info and lib_info.library_name:
                    libraries.append(lib_info)

            return libraries

        except Exception as e:
            self.logger.error(f"Failed to get Qt libraries: {e}")
            return []

    def _find_dependency_info(self, binary_path: str) -> LddInfo:
        """
        Find dependency info using ldd, matching findDependencyInfo() from shared.cpp

        Args:
            binary_path: Path to binary to analyze

        Returns:
            LddInfo object with dependencies
        """
        ldd_info = LddInfo()
        ldd_info.binary_path = binary_path

        try:
            self.logger.debug(f"Running ldd on: {binary_path}")

            # Run ldd command (matches shared.cpp)
            result = subprocess_run(
                ["ldd", binary_path], capture_output=True, text=True, check=True
            )

            if result.returncode != 0:
                self.logger.error(f"ldd failed: {result.stderr}")
                return ldd_info

            # Parse ldd output (matches shared.cpp logic)
            output_lines = result.stdout.strip().split("\n")
            if len(output_lines) < 2:
                if "statically linked" not in result.stdout:
                    self.logger.error(f"Could not parse ldd output: {result.stdout}")
                return ldd_info

            for line in output_lines:
                self._detect_qt_version_from_line(line)

                dep_path = None

                # Parse dependency (matches shared.cpp regex)
                # Try format: "libname.so => /path/to/lib (0x...)"
                match = self.ldd_pattern.match(line)
                if match:
                    dep_path = match.group(1).strip()
                else:
                    # Try format: "/absolute/path/to/lib (0x...)" or "libname.so (0x...)"
                    match = self.ldd_pattern_absolute.match(line)
                    if match:
                        candidate_path = match.group(1).strip()
                        # Skip virtual libraries like linux-vdso.so.1
                        if not candidate_path.startswith(
                            "linux-vdso"
                        ) and os_path_exists(candidate_path):
                            dep_path = candidate_path
                        # Don't skip other libraries, just warn if they don't exist
                        elif not candidate_path.startswith("linux-vdso"):
                            self.logger.debug(
                                f"Library path doesn't exist: {candidate_path}"
                            )

                if dep_path:
                    dylib_info = DylibInfo(binary_path=dep_path)
                    ldd_info.dependencies.append(dylib_info)
                    self.logger.debug(f"Found dependency: {dep_path}")
                elif "not found" in line and self.qt_detection_complete:
                    # Error handling for not found libraries (matches shared.cpp)
                    self.logger.error(f"Library not found: {line.strip()}")
                    raise RuntimeError(f"Library not found: {line.strip()}")

            return ldd_info

        except subprocess_CalledProcessError as e:
            self.logger.error(f"ldd command failed: {e}")
            return ldd_info
        except Exception as e:
            self.logger.error(f"Error finding dependencies: {e}")
            return ldd_info

    def _detect_qt_version_from_line(self, line: str):
        """Detect Qt version from ldd output line (matches shared.cpp logic)"""
        if "libQt6" in line:
            self.qt_detected = 6
        elif "libQt5" in line:
            self.qt_detected = 5
        elif "libQtCore.so.4" in line:
            self.qt_detected = 4

    def _parse_ldd_library_line(
        self, line: str, app_dir_path: str, rpaths: Set[str]
    ) -> Optional[LibraryInfo]:
        """
        Parse ldd library line, matching parseLddLibraryLine() from shared.cpp

        Args:
            line: Library path from ldd output
            app_dir_path: AppDir path
            rpaths: Set of rpaths

        Returns:
            LibraryInfo object or None
        """
        info = LibraryInfo()
        trimmed = line.strip()

        if not trimmed:
            return None

        self.logger.debug(f"Parsing library line: {trimmed}")

        # Check bundling rules (matches shared.cpp logic)
        if not self.bundle_everything:
            if self.bundle_all_but_core_libs:
                # Bundle all except blacklisted
                if not should_bundle_library(trimmed, True, False):
                    self.logger.debug(f"Skipping blacklisted: {trimmed}")
                    return None
            else:
                # Default mode: only Qt + special libs
                if not should_bundle_library(trimmed, False, False):
                    return None

        # Determine bundle library directory (matches shared.cpp)
        bundle_lib_dir = "lib"  # Simplified for now

        # Parse library path components
        parts = trimmed.split("/")
        if not parts:
            return None

        # Extract library name and path
        library_file = parts[-1]
        library_dir = "/".join(parts[:-1])

        if not library_file or not library_dir:
            return None

        # Fill LibraryInfo (matches shared.cpp)
        info.library_name = library_file
        info.binary_name = library_file
        info.library_directory = library_dir + "/"
        info.binary_directory = library_dir + "/"
        info.library_path = trimmed
        info.binary_path = trimmed
        info.source_file_path = trimmed
        info.is_dylib = True
        info.deployed_install_name = "$ORIGIN"

        # Set destination directory
        if app_dir_path in trimmed:
            # Library already in AppDir
            info.library_destination_directory = os_path_relpath(
                library_dir, app_dir_path
            )
        else:
            info.library_destination_directory = bundle_lib_dir + "/"

        info.binary_destination_directory = info.library_destination_directory

        return info

    def _collect_all_libraries(
        self, binary_paths: List[str], processed: Set[str]
    ) -> Set[str]:
        """
        Recursively collect all library dependencies.

        Args:
            binary_paths: List of binaries to process
            processed: Set of already processed binaries

        Returns:
            Set of all library paths
        """
        libraries = set()

        for binary_path in binary_paths:
            if binary_path in processed:
                continue

            processed.add(binary_path)

            try:
                ldd_info = self._find_dependency_info(binary_path)

                for dylib_info in ldd_info.dependencies:
                    lib_path = dylib_info.binary_path
                    libraries.add(lib_path)

                    # Recursively process this library
                    if lib_path not in processed and os_path_exists(lib_path):
                        sub_libs = self._collect_all_libraries([lib_path], processed)
                        libraries.update(sub_libs)

            except Exception as e:
                self.logger.warning(f"Failed to process {binary_path}: {e}")

        return libraries
