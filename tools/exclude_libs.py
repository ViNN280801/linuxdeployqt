"""
Exclude list for libraries based on official linuxdeployqt excludelist.h
Matches the logic from shared.cpp parseLddLibraryLine()
See: https://github.com/probonopd/linuxdeployqt/blob/master/linuxdeployqt/excludelist.h
"""

from os.path import basename as os_path_basename

# Generated exclude list matching official linuxdeployqt excludelist.h
# This list should be kept in sync with upstream excludelist
GENERATED_EXCLUDE_LIST = [
    "ld-linux.so.2",
    "ld-linux-x86-64.so.2",
    "libanl.so.1",
    "libasound.so.2",
    "libBrokenLocale.so.1",
    "libcidn.so.1",
    "libcom_err.so.2",
    "libc.so.6",
    "libdl.so.2",
    "libdrm.so.2",
    "libEGL.so.1",
    "libexpat.so.1",
    "libfontconfig.so.1",
    "libfreetype.so.6",
    "libfribidi.so.0",
    "libgbm.so.1",
    "libgcc_s.so.1",
    "libgdk_pixbuf-2.0.so.0",
    "libgio-2.0.so.0",
    "libglapi.so.0",
    "libGLdispatch.so.0",
    "libglib-2.0.so.0",
    "libGL.so.1",
    "libGLX.so.0",
    "libgobject-2.0.so.0",
    "libgpg-error.so.0",
    "libharfbuzz.so.0",
    "libICE.so.6",
    "libjack.so.0",
    "libm.so.6",
    "libmvec.so.1",
    "libnss_compat.so.2",
    "libnss_db.so.2",
    "libnss_dns.so.2",
    "libnss_files.so.2",
    "libnss_hesiod.so.2",
    "libnss_nisplus.so.2",
    "libnss_nis.so.2",
    "libp11-kit.so.0",
    "libpango-1.0.so.0",
    "libpangocairo-1.0.so.0",
    "libpangoft2-1.0.so.0",
    "libpthread.so.0",
    "libresolv.so.2",
    "librt.so.1",
    "libSM.so.6",
    "libstdc++.so.6",
    "libthai.so.0",
    "libthread_db.so.1",
    "libusb-1.0.so.0",
    "libutil.so.1",
    "libuuid.so.1",
    "libX11.so.6",
    "libxcb-dri2.so.0",
    "libxcb-dri3.so.0",
    "libxcb.so.1",
    "libz.so.1",
]

# Libraries that should never be excluded, even if they match the exclude list
# This is crucial for cross-distribution compatibility, especially for Astra Linux
NEVER_EXCLUDE_LIST = [
    # Critical Qt platform libraries
    "libQt5Concurrent.so",
    "libQt5QuickControls2.so",
    "libQt5Svg.so",
    "libQt5Widgets.so",
    "libQt5Gui.so",
    "libQt5Core.so",
    "libQt5Network.so",
    "libQt5PrintSupport.so",
    "libQt5Sql.so",
    "libQt5Test.so",
    "libQt5XcbQpa.so",
    "libQt5DBus.so",
    "libQt5XcbQpa.so.5",
    "libQt5DBus.so.5",
    "libQt6XcbQpa.so",
    "libQt6DBus.so",
    "libQt6XcbQpa.so.6",
    "libQt6DBus.so.6",
    # Critical Qt Quick Controls 2 libraries - MUST be included
    "libQt5QuickControls2.so",
    "libQt5QuickTemplates2.so",
    "libQt5QuickControls2.so.5",
    "libQt5QuickTemplates2.so.5",
    "libQt6QuickControls2.so",
    "libQt6QuickTemplates2.so",
    "libQt6QuickControls2.so.6",
    "libQt6QuickTemplates2.so.6",
    # Critical plugins' dependencies
    "libxcb-render-util.so",
    "libxcb-image.so",
    "libxcb-icccm.so",
    "libxcb-shm.so",
    "libxcb-keysyms.so",
    "libxcb-randr.so",
    "libxcb-render.so",
    "libxcb-shape.so",
    "libxcb-sync.so",
    "libxcb-xfixes.so",
    "libxcb-xkb.so",
]


def should_exclude_library(library_path: str) -> bool:
    """
    Check if a library should be excluded from the AppImage.
    Some libraries are system-specific and should be excluded.
    """
    library_name = os_path_basename(library_path)

    # Never exclude NSS libraries needed by QtWebEngine
    webengine_required_libs = [
        "libsoftokn3.so",
        "libfreebl3.so",
        "libnss3.so",
        "libnssutil3.so",
        "libsmime3.so",
        "libssl3.so",
        "libsqlite3.so",
    ]

    for nss_lib in webengine_required_libs:
        if library_name.startswith(nss_lib):
            return False

    # Standard exclusion patterns
    if not library_path:
        return True

    # First check NEVER_EXCLUDE_LIST
    for never_exclude in NEVER_EXCLUDE_LIST:
        if library_name == never_exclude or library_name.startswith(
            never_exclude + "."
        ):
            return False

    # Check against exclude list - exact matching like original linuxdeployqt
    for excluded in GENERATED_EXCLUDE_LIST:
        # Check if library basename matches exactly
        if library_name == excluded:
            return True

        # Also check if library name without version matches
        # e.g., "libc.so.6.1" should match "libc.so.6"
        if library_name.startswith(excluded + "."):
            return True

    return False


def should_bundle_library(
    library_path: str,
    bundle_all_but_core_libs: bool = False,
    bundle_everything: bool = False,
) -> bool:
    """
    Determines if a library should be bundled in the AppImage.
    """
    if bundle_everything:
        return True

    library_name = os_path_basename(library_path)

    # Always include NSS libraries needed by QtWebEngine
    webengine_required_libs = [
        "libsoftokn3.so",
        "libfreebl3.so",
        "libnss3.so",
        "libnssutil3.so",
        "libsmime3.so",
        "libssl3.so",
        "libsqlite3.so",
    ]

    for nss_lib in webengine_required_libs:
        if library_name.startswith(nss_lib):
            return True

    if bundle_all_but_core_libs:
        # Bundle all EXCEPT those in exclude list
        return not should_exclude_library(library_path)

    # Default mode: only specific libraries (matches original logic)

    # Always bundle libicu (special case from shared.cpp)
    if "libicu" in library_name:
        return True

    # Bundle Qt libraries (including platform-specific ones)
    # Use case-insensitive matching for Qt libraries
    library_name_lower = library_name.lower()
    if "libqt" in library_name_lower:
        return True

    # Bundle critical Qt platform libraries that are often missed
    critical_qt_patterns = [
        "libqt5xcbqpa",
        "libqt5dbus",
        "libqt6xcbqpa",
        "libqt6dbus",
        # Critical Qt Quick Controls 2 libraries
        "libqt5quickcontrols2",
        "libqt5quicktemplates2",
        "libqt6quickcontrols2",
        "libqt6quicktemplates2",
        # Additional critical Qt libraries for WebEngine and other components
        "libqt5webengine",
        "libqt5webenginecore",
        "libqt5webenginewidgets",
        "libqt6webengine",
        "libqt6webenginecore",
        "libqt6webenginewidgets",
        "libqt5test",
        "libqt6test",
        "libqt4test",
    ]
    for pattern in critical_qt_patterns:
        if pattern in library_name_lower:
            return True

    # Bundle xcb extension libraries that Qt platform plugins need
    # These are often missing and cause "Could not load Qt platform plugin" errors
    xcb_extension_patterns = [
        "libxcb-dpms",
        "libxcb-icccm",
        "libxcb-image",
        "libxcb-keysyms",
        "libxcb-present",
        "libxcb-randr",
        "libxcb-render",
        "libxcb-render-util",
        "libxcb-shape",
        "libxcb-shm",
        "libxcb-sync",
        "libxcb-util",
        "libxcb-xfixes",
        "libxcb-xinerama",
        "libxcb-xkb",
        "libxcb-xinput",
    ]

    for pattern in xcb_extension_patterns:
        if pattern in library_name_lower:
            return True

    # Bundle Qt-related tools
    if "libqgsttools" in library_name_lower:
        return True

    # Bundle Qt Quick related libraries (absolutely essential for QML apps)
    qt_quick_patterns = [
        "libqt5quick",
        "libqt6quick",
        "libqt5qml",
        "libqt6qml",
        "libqt5declarative",
        "libqt6declarative",
    ]
    for pattern in qt_quick_patterns:
        if pattern in library_name_lower:
            return True

    # Bundle Boost libraries (especially important for Astra Linux)
    if "boost" in library_name_lower:
        return True

    # In default mode, don't bundle system libraries
    return False
