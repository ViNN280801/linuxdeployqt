"""
Qt Component Analyzer based on official linuxdeployqt implementation
Matches the plugin detection logic from shared.cpp
"""

from typing import Dict, Set, Union
from os.path import basename as os_basename

from logger.logger import Logger
from .qml_analyzer import QmlAnalyzer


class QtComponentAnalyzer:
    """
    Analyzes Qt application components to determine required plugins, modules, and libraries
    Based on the logic from deployPlugins() in shared.cpp
    """

    def __init__(
        self, dependency_collector, project_root: str, log_level: str = "DEBUG"
    ):
        self.dependency_collector = dependency_collector
        self.project_root = project_root
        self.logger = Logger(log_level, self.__class__.__name__)

        # QML analyzer for custom QML directories
        self.qml_analyzer = QmlAnalyzer(project_root, log_level)

        # Plugin mapping based on deployPlugins logic from shared.cpp
        self.qt5_plugins = {
            "libQt5Gui": [
                "platforms/libqxcb.so",
                "platforminputcontexts",
                "iconengines",
                "imageformats",
            ],
            "libQt5OpenGL": ["xcbglintegrations"],
            "libQt5Svg": ["iconengines/libqsvgicon.so"],
            "libQt5PrintSupport": ["printsupport"],
            "libQt5Network": ["bearer"],
            "libQt5Sql": ["sqldrivers"],
            "libQt5Positioning": ["position"],
            "libQt5Multimedia": ["audio", "mediaservice"],
            "libQt53DRender": [
                "geometryloaders",
                "renderers",
                "renderplugins",
                "sceneparsers",
            ],
            "libQt5WebEngineCore": [],  # Special handling needed
        }

        self.qt6_plugins = {
            "libQt6Gui": [
                "platforms/libqxcb.so",
                "platforminputcontexts",
                "iconengines",
                "imageformats",
                "accessible",
                "virtualkeyboard",
            ],
            "libQt6OpenGL": ["xcbglintegrations"],
            "libQt6Svg": ["iconengines/libqsvgicon.so"],
            "libQt6PrintSupport": ["printsupport"],
            "libQt6Network": ["networkaccess", "networkinformation", "tls"],
            "libQt6Sql": ["sqldrivers"],
            "libQt6Positioning": ["position"],
            "libQt6Multimedia": [
                "audio",
                "mediaservice",
                "playlistformats",
                "multimedia",
            ],
            "libQt63DRender": [
                "geometryloaders",
                "renderers",
                "renderplugins",
                "sceneparsers",
            ],
            "libQt6Sensors": ["sensorgestures", "sensors"],
            "libQt6SerialBus": ["canbus"],
            "libQt6TextToSpeech": ["texttospeech"],
            "libQt6Location": ["geoservices"],
            "libQt6Quick": ["qmltooling", "scenegraph"],
            "libQt6Declarative": ["qml1tooling"],
            "libQt6Gamepad": ["gamepads"],
            "libQt6WebView": ["webview"],
            "libQt6WebEngineCore": [],  # Special handling needed
        }

    def set_custom_qml_dir(self, qml_dir: str):
        """Set custom QML directory for analysis"""
        self.qml_analyzer.add_custom_qml_dir(qml_dir)

    def analyze_required_components(
        self, executable_path: str
    ) -> Dict[str, Union[Set[str], bool]]:
        """
        Analyze required Qt components (matches logic from deployPlugins in shared.cpp)

        Returns:
            Dict with keys: qt_libraries, plugins, qml_modules, webengine
        """
        try:
            self.logger.debug(f"Analyzing components for: {executable_path}")

            # Get dependencies using ldd
            dependencies = self.dependency_collector.get_libs(executable_path)

            # Analyze Qt libraries
            qt_libraries = self._analyze_qt_libraries(dependencies)
            if not qt_libraries:
                self.logger.warning("No Qt libraries found in dependencies")
                return {}

            # Determine Qt version
            qt_version = self._detect_qt_version(qt_libraries)
            self.logger.debug(f"Detected Qt version: {qt_version}")

            # Determine required plugins based on libraries
            required_plugins = self._determine_plugins_from_libraries(
                qt_libraries, qt_version
            )

            # Analyze QML requirements
            qml_modules = self._analyze_qml_requirements()

            # Check for WebEngine usage
            uses_webengine = self._check_webengine_usage(qt_libraries)

            result = {
                "qt_libraries": qt_libraries,
                "plugins": required_plugins,
                "qml_modules": qml_modules,
                "webengine_needed": uses_webengine,
            }

            self.logger.info(
                f"Found {len(qt_libraries)} Qt libraries, "
                f"{len(required_plugins)} plugins, "
                f"{len(qml_modules)} QML modules"
            )

            return result

        except Exception as e:
            self.logger.error(f"Failed to analyze components: {e}")
            return {}

    def _analyze_qt_libraries(self, dependencies: list) -> Set[str]:
        """Analyze Qt libraries from dependencies"""
        qt_libraries = set()

        for dep in dependencies:
            lib_name = os_basename(dep)

            # Match Qt libraries (Qt5/Qt6)
            if lib_name.startswith(("libQt5", "libQt6")):
                # Extract base library name (e.g., "libQt5Core.so.5" -> "libQt5Core")
                base_name = lib_name.split(".")[0]
                qt_libraries.add(base_name)

        self.logger.debug(f"Found Qt libraries: {sorted(qt_libraries)}")
        return qt_libraries

    def _detect_qt_version(self, qt_libraries: Set[str]) -> int:
        """Detect Qt version from libraries"""
        for lib in qt_libraries:
            if lib.startswith("libQt6"):
                return 6
            elif lib.startswith("libQt5"):
                return 5
            elif lib.startswith("libQt4"):
                return 4
        return 0

    def _determine_plugins_from_libraries(
        self, qt_libraries: Set[str], qt_version: int
    ) -> Set[str]:
        """Determine required plugins based on Qt libraries (matches deployPlugins from shared.cpp)

        Args:
            qt_libraries: Set of Qt library names (e.g., "libQt5Core", "libQt6Gui")
            qt_version: Qt version (5 or 6)

        Returns:
            Set of plugin paths to deploy
        """
        plugins = set()

        # Select appropriate plugin mapping based on Qt version
        plugin_map = self.qt5_plugins if qt_version == 5 else self.qt6_plugins

        # Iterate through plugin mapping (matching deployPlugins logic)
        for lib_name, plugin_list in plugin_map.items():
            # Check if this library is used
            lib_found = any(lib for lib in qt_libraries if lib_name in lib)

            if lib_found:
                self.logger.debug(
                    f"Library {lib_name} found, adding plugins: {plugin_list}"
                )
                plugins.update(plugin_list)

        # Special handling for always-included plugins when Gui is present
        gui_lib = f"libQt{qt_version}Gui" if qt_version in [5, 6] else "libQt4Gui"
        if any(gui_lib in lib for lib in qt_libraries):
            # Always include xcb platform plugin (matches original behavior)
            plugins.add("platforms/libqxcb.so")

        self.logger.debug(f"Determined plugins for Qt{qt_version}: {sorted(plugins)}")
        return plugins

    def _analyze_qml_requirements(self) -> Set[str]:
        """Analyze QML module requirements.

        Returns:
            Set of required QML module names
        """
        try:
            return self.qml_analyzer.analyze_qml_imports()
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to analyze QML requirements: {e}")
            return set()

    def _check_webengine_usage(self, qt_libraries: Set[str]) -> bool:
        """Check if WebEngine is being used.

        Args:
            qt_libraries: Set of Qt library names

        Returns:
            True if WebEngine is used
        """
        # Check for Qt WebEngine libraries (matches original logic)
        for lib in qt_libraries:
            if any(
                webengine_name in lib
                for webengine_name in [
                    "WebEngine",
                    "WebEngineCore",
                    "WebEngineWidgets",
                    "WebEngineQuick",
                ]
            ):
                return True
        return False
