from os.path import join as os_path_join


class AppDirPaths:
    """AppDir structure constants matching official linuxdeployqt behavior"""

    def __init__(
        self, appdir_path: str, fhs_like_mode: bool = False, fhs_prefix: str = ""
    ):
        self.appdir_path = appdir_path
        self.fhs_like_mode = fhs_like_mode
        self.fhs_prefix = fhs_prefix

        # Core paths
        self.APPRUN = os_path_join(appdir_path, "AppRun")

        if fhs_like_mode:
            # FHS-like mode: usr structure
            self.BIN_DIR = os_path_join(appdir_path, "usr", "bin")
            self.LIB_DIR = os_path_join(appdir_path, "usr", "lib")
            self.PLUGINS_DIR = os_path_join(appdir_path, "usr", "plugins")
            self.QML_DIR = os_path_join(appdir_path, "usr", "qml")
            self.TRANSLATIONS_DIR = os_path_join(appdir_path, "usr", "translations")
            self.SHARE_DIR = os_path_join(appdir_path, "usr", "share")
            self.DOC_DIR = os_path_join(appdir_path, "usr", "share", "doc")
            self.LIBEXEC_DIR = os_path_join(appdir_path, "usr", "libexec")
            self.RESOURCES_DIR = os_path_join(appdir_path, "usr", "resources")

            # Relative paths for qt.conf (relative to binary)
            self.QT_CONF_PREFIX = "../"
            self.QT_CONF_PLUGINS = "plugins"
            self.QT_CONF_QML = "qml"
            self.QT_CONF_TRANSLATIONS = "translations"

        else:
            # Traditional AppDir mode: flat structure
            self.BIN_DIR = appdir_path  # Binary is in root
            self.LIB_DIR = os_path_join(appdir_path, "lib")
            self.PLUGINS_DIR = os_path_join(appdir_path, "plugins")
            self.QML_DIR = os_path_join(appdir_path, "qml")
            self.TRANSLATIONS_DIR = os_path_join(appdir_path, "translations")
            self.SHARE_DIR = os_path_join(appdir_path, "share")
            self.DOC_DIR = os_path_join(appdir_path, "doc")
            self.LIBEXEC_DIR = os_path_join(appdir_path, "libexec")
            self.RESOURCES_DIR = os_path_join(appdir_path, "resources")

            # Relative paths for qt.conf (relative to binary)
            self.QT_CONF_PREFIX = "./"
            self.QT_CONF_PLUGINS = "plugins"
            self.QT_CONF_QML = "qml"
            self.QT_CONF_TRANSLATIONS = "translations"

    @property
    def bundle_library_directory(self) -> str:
        """Get the bundle library directory path (relative to appdir)"""
        if self.fhs_like_mode:
            relative_prefix = self.fhs_prefix.replace(self.appdir_path + "/", "")
            return os_path_join(relative_prefix, "lib")
        else:
            return "lib"
