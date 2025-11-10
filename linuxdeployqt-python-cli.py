#!/usr/bin/env python3
"""
linuxdeployqt-python - Deploy Qt applications on Linux

A Python implementation of linuxdeployqt tool for creating AppDir bundles.
Based on official linuxdeployqt matching shared.cpp and main.cpp logic.
"""
from sys import exit as sys_exit

from os import X_OK as os_X_OK
from os import getcwd as os_getcwd
from os import access as os_access
from os import makedirs as os_makedirs
from os.path import join as os_join
from os.path import isdir as os_isdir
from os.path import isfile as os_isfile
from os.path import exists as os_exists
from os.path import abspath as os_abspath
from os.path import dirname as os_dirname
from os.path import splitext as os_splitext
from os.path import basename as os_basename

from glob import glob as glob_glob
from shutil import copy2 as shutil_copy2

from pathlib import Path
from argparse import ArgumentParser as argparse_ArgumentParser

from logger.logger import Logger
from tools.qt_deployer import QtDeployer


def show_desktop_file_example():
    """Show example .desktop file content."""
    example = """[Desktop Entry]
Type=Application
Name=YourAppName
Comment=Brief description of your application
Exec=YourAppName
Icon=your-app-icon
Categories=Office;Utility;
Terminal=false
StartupNotify=true
MimeType=application/pdf;text/html;
"""
    print("\n📋 Example .desktop file content:")
    print(example)
    print(
        "💡 Save this content to a file like 'myapp.desktop' and use --desktop-file myapp.desktop"
    )


def show_icon_requirements():
    """Show icon file requirements."""
    print("\n🎨 Icon file requirements:")
    print("   • Supported formats: PNG, SVG, ICO")
    print("   • Recommended size: 128x128 or higher")
    print("   • Should be square aspect ratio")
    print("   • Example: --icon resources/myapp.png")


def parse_arguments():
    """Parse command line arguments matching main.cpp options."""
    parser = argparse_ArgumentParser(
        description="Deploy Qt applications on Linux by creating AppDir bundles",
        prog="linuxdeployqt-python",
    )

    parser.add_argument(
        "--binary-path",
        type=str,
        required=True,
        help="Path to the application binary (e.g., ./build/release/LumReportViewer)",
    )

    parser.add_argument(
        "--output-path",
        type=str,
        help="Path where to place the constructed AppDir. If empty, places in current directory",
    )

    parser.add_argument(
        "--qml-dir",
        type=str,
        action="append",
        help="""Path to custom QML components directory. Used by qmlimportscanner to find QML imports.
        Can be specified multiple times. Supports ~, ., .. path resolution.
        Example: --qml-dir ./qml --qml-dir ./resources/qml""",
    )

    parser.add_argument(
        "--qt-path",
        type=str,
        help="""Explicit path to Qt installation directory (e.g., /opt/Qt5.15.17).
        Forces deployment to use ONLY this Qt installation, preventing ABI conflicts
        between system and custom Qt builds. When specified, qmake will be searched
        in {qt-path}/bin/qmake and all Qt libraries/plugins will be taken from this path.
        Example: --qt-path /opt/Qt5.15.17""",
    )

    parser.add_argument(
        "--desktop-file",
        type=str,
        required=True,
        help="Path to .desktop file for the application (REQUIRED)",
    )

    parser.add_argument(
        "--icon",
        type=str,
        required=True,
        help="Path to application icon file (REQUIRED)",
    )

    parser.add_argument(
        "--apprun-file",
        type=str,
        help="Path to custom AppRun script file (optional)",
    )

    parser.add_argument(
        "--bundle-non-qt-libs",
        action="store_true",
        default=True,  # True for better cross-distro compatibility
        help="Bundle non-Qt libraries (enabled by default for better compatibility)",
    )

    parser.add_argument(
        "--no-strip",
        action="store_true",
        help="Don't run strip on binaries",
    )

    parser.add_argument(
        "--always-overwrite",
        action="store_true",
        help="Copy files even if target exists",
    )

    parser.add_argument(
        "--verbose",
        type=int,
        choices=[0, 1, 2],
        default=1,
        help="""Verbosity level: 0=(warnings and errors only)
        1=(information, success, warnings, errors messages)
        2=(debug, information, success, warnings, errors messages)
        (default: 1)""",
    )

    parser.add_argument(
        "--version", action="version", version="linuxdeployqt-python 1.0.0"
    )

    # Add hidden help flags for examples
    parser.add_argument(
        "--show-desktop-example",
        action="store_true",
        help="Show example .desktop file content and exit",
    )

    parser.add_argument(
        "--show-icon-help",
        action="store_true",
        help="Show icon file requirements and exit",
    )

    return parser.parse_args()


def resolve_path(path_str: str) -> str:
    """Resolve path with support for ~, ., .. symbols."""
    if not path_str:
        return ""

    # Expand user home directory (~)
    path = Path(path_str).expanduser()

    # Resolve relative paths (., ..)
    path = path.resolve()

    return str(path)


def validate_arguments(args):
    """Validate parsed arguments matching main.cpp validation."""
    logger = Logger("INFO", "linuxdeployqt")

    # Validate binary path
    binary_path = resolve_path(args.binary_path)
    if not os_exists(binary_path):
        logger.error(f"❌ Executable not found: {binary_path}")
        sys_exit(1)

    if not os_isfile(binary_path):
        logger.error(f"❌ Path is not a file: {binary_path}")
        sys_exit(1)

    if not os_access(binary_path, os_X_OK):
        logger.error(f"❌ File is not executable: {binary_path}")
        sys_exit(1)

    # Validate output path
    output_path = args.output_path
    if output_path:
        output_path = resolve_path(output_path)
        output_dir = os_dirname(output_path)
        if output_dir and not os_exists(output_dir):
            logger.error(f"❌ Output directory does not exist: {output_dir}")
            sys_exit(1)
    else:
        # Use current directory with binary name + .AppDir
        binary_name = os_splitext(os_basename(binary_path))[0]
        output_path = os_join(os_getcwd(), f"{binary_name}.AppDir")

    # Validate QML directories if provided
    qml_dirs = []
    if args.qml_dir:
        for qml_dir in args.qml_dir:
            resolved_qml_dir = resolve_path(qml_dir)
            if not os_exists(resolved_qml_dir):
                logger.error(f"❌ QML directory not found: {resolved_qml_dir}")
                sys_exit(1)
            if not os_isdir(resolved_qml_dir):
                logger.error(f"❌ QML path is not a directory: {resolved_qml_dir}")
                sys_exit(1)
            qml_dirs.append(resolved_qml_dir)

    # Validate desktop file
    desktop_file = resolve_path(args.desktop_file)
    if not os_exists(desktop_file):
        logger.error(f"❌ Desktop file not found: {desktop_file}")
        logger.info("💡 Use --show-desktop-example to see an example .desktop file")
        sys_exit(1)
    if not os_isfile(desktop_file):
        logger.error(f"❌ Desktop path is not a file: {desktop_file}")
        sys_exit(1)

    # Validate icon file
    icon_file = resolve_path(args.icon)
    if not os_exists(icon_file):
        logger.error(f"❌ Icon file not found: {icon_file}")
        logger.info("💡 Use --show-icon-help to see icon requirements")
        sys_exit(1)
    if not os_isfile(icon_file):
        logger.error(f"❌ Icon path is not a file: {icon_file}")
        sys_exit(1)

    # Validate apprun file if provided
    apprun_file = ""
    if args.apprun_file:
        apprun_file = resolve_path(args.apprun_file)
        if not os_exists(apprun_file):
            logger.error(f"❌ AppRun file not found: {apprun_file}")
            sys_exit(1)
        if not os_isfile(apprun_file):
            logger.error(f"❌ AppRun path is not a file: {apprun_file}")
            sys_exit(1)

    # Validate Qt path if provided
    qt_path = ""
    if args.qt_path:
        qt_path = resolve_path(args.qt_path)
        if not os_exists(qt_path):
            logger.error(f"❌ Qt installation directory not found: {qt_path}")
            sys_exit(1)
        if not os_isdir(qt_path):
            logger.error(f"❌ Qt path is not a directory: {qt_path}")
            sys_exit(1)

        # Verify that this looks like a Qt installation
        qt_bin_dir = os_join(qt_path, "bin")
        qt_lib_dir = os_join(qt_path, "lib")

        if not os_exists(qt_bin_dir):
            logger.error(f"❌ Qt bin directory not found: {qt_bin_dir}")
            logger.info(
                "💡 Expected Qt installation structure: {qt-path}/bin/, {qt-path}/lib/, etc."
            )
            sys_exit(1)

        if not os_exists(qt_lib_dir):
            logger.error(f"❌ Qt lib directory not found: {qt_lib_dir}")
            logger.info(
                "💡 Expected Qt installation structure: {qt-path}/bin/, {qt-path}/lib/, etc."
            )
            sys_exit(1)

        # Check for qmake in bin directory
        qmake_path = os_join(qt_bin_dir, "qmake")
        if not os_exists(qmake_path):
            logger.error(f"❌ qmake not found in Qt bin directory: {qmake_path}")
            logger.info("💡 Make sure the specified Qt installation is complete")
            sys_exit(1)

        logger.info(f"🎯 Using explicit Qt installation: {qt_path}")

    return (
        binary_path,
        output_path,
        qml_dirs,
        desktop_file,
        icon_file,
        apprun_file,
        qt_path,
    )


def get_log_level_name(verbose_level: int) -> str:
    """Convert verbose level to log level name matching main.cpp logLevel."""
    level_mapping = {0: "SUCCESS", 1: "INFO", 2: "DEBUG"}
    return level_mapping.get(verbose_level, "INFO")


def main():
    """Main entry point matching main.cpp logic."""
    try:
        # Parse arguments
        args = parse_arguments()

        # Handle help flags
        if args.show_desktop_example:
            show_desktop_file_example()
            sys_exit(0)

        if args.show_icon_help:
            show_icon_requirements()
            sys_exit(0)

        # Get log level
        log_level = get_log_level_name(args.verbose)
        logger = Logger(log_level, "linuxdeployqt")

        logger.info("🚀 Starting linuxdeployqt-python...")
        logger.debug(f"Arguments: {vars(args)}")

        # Validate arguments
        (
            binary_path,
            output_path,
            qml_dirs,
            desktop_file,
            icon_file,
            apprun_file,
            qt_path,
        ) = validate_arguments(args)

        logger.info(f"📦 Binary: {binary_path}")
        logger.info(f"📁 Output: {output_path}")
        if qml_dirs:
            for i, qml_dir in enumerate(qml_dirs):
                logger.info(f"🎨 QML dir {i + 1}: {qml_dir}")
        logger.info(f"🖥️ Desktop file: {desktop_file}")
        logger.info(f"🎨 Icon: {icon_file}")
        if apprun_file:
            logger.info(f"🖥️ AppRun file: {apprun_file}")
        if qt_path:
            logger.info(f"🎯 Qt path: {qt_path}")

        # Determine project root - go up from script location to find the project root
        script_dir = os_dirname(os_dirname(os_abspath(__file__)))
        project_root = script_dir  # The ReportViewerQML directory

        logger.debug(f"Project root: {project_root}")

        # Create deployer and deploy (matches main.cpp deployQtLibraries call)
        deployer = QtDeployer(project_root, log_level)

        # Set explicit Qt path if provided
        if qt_path:
            deployer.set_explicit_qt_path(qt_path)

        # Configure deployer based on arguments (matches main.cpp flags)
        deployer.bundle_all_but_core_libs = args.bundle_non_qt_libs
        deployer.dependency_collector.set_bundle_mode(
            bundle_all_but_core_libs=args.bundle_non_qt_libs, bundle_everything=False
        )
        deployer.run_strip_enabled = not args.no_strip
        deployer.always_overwrite_enabled = args.always_overwrite

        # Set custom QML directories if provided (matches -qmldir from main.cpp)
        if qml_dirs:
            for qml_dir in qml_dirs:
                deployer.set_custom_qml_dir(qml_dir)
                logger.debug(f"Added custom QML directory: {qml_dir}")
        else:
            # Auto-detect QML directories in project (matches main.cpp logic)
            # "Convenience: Look for .qml files in the current directoty if no -qmldir specified."
            project_qml_dir = os_join(os_dirname(binary_path), "qml")
            if os_exists(project_qml_dir):
                deployer.set_custom_qml_dir(project_qml_dir)
                logger.debug(f"Auto-detected QML directory: {project_qml_dir}")

            # Additional auto-detection for QML dirs in common locations
            additional_qml_dirs = [
                os_join(project_root, "qml"),
                os_join(project_root, "src/qml"),
                os_join(project_root, "ui"),
            ]

            for qml_dir in additional_qml_dirs:
                if os_exists(qml_dir) and qml_dir != project_qml_dir:
                    deployer.set_custom_qml_dir(qml_dir)
                    logger.debug(f"Auto-detected additional QML directory: {qml_dir}")

        # After deployment, verify QtWebEngine resources
        def verify_webengine_resources(output_path):
            """Verify and fix QtWebEngine resources if needed"""
            # Check for essential WebEngine resources
            resources_dir = os_join(output_path, "resources")
            qtwebengine_locales_dir = os_join(
                output_path, "translations", "qtwebengine_locales"
            )

            if not os_exists(resources_dir) or not os_exists(qtwebengine_locales_dir):
                logger.warning(
                    "⚠️ QtWebEngine resources not found, attempting to fix..."
                )

                # Common locations to search for QtWebEngine resources
                resource_locations = [
                    "/usr/share/qt5/resources",
                    "/usr/share/qt6/resources",
                    "/usr/lib/qt5/resources",
                    "/usr/lib/qt6/resources",
                    "/usr/lib/x86_64-linux-gnu/qt5/resources",
                    "/usr/lib/x86_64-linux-gnu/qt6/resources",
                ]

                # Find and copy resources
                for res_path in resource_locations:
                    if os_exists(res_path):
                        logger.info(f"Found QtWebEngine resources at: {res_path}")
                        # Ensure resources directory exists
                        os_makedirs(resources_dir, exist_ok=True)

                        for resource_file in glob_glob(os_join(res_path, "*.pak")):
                            dest_file = os_join(
                                resources_dir, os_basename(resource_file)
                            )
                            shutil_copy2(resource_file, dest_file)
                            logger.info(
                                f"Copied WebEngine resource: {os_basename(resource_file)}"
                            )

                        # Only check one found location
                        break

                # Also look for locales
                locale_locations = [
                    "/usr/share/qt5/translations/qtwebengine_locales",
                    "/usr/share/qt6/translations/qtwebengine_locales",
                    "/usr/lib/qt5/translations/qtwebengine_locales",
                    "/usr/lib/qt6/translations/qtwebengine_locales",
                    "/usr/lib/x86_64-linux-gnu/qt5/translations/qtwebengine_locales",
                    "/usr/lib/x86_64-linux-gnu/qt6/translations/qtwebengine_locales",
                ]

                for locale_path in locale_locations:
                    if os_exists(locale_path):
                        logger.info(f"Found QtWebEngine locales at: {locale_path}")
                        # Ensure locales directory exists
                        os_makedirs(qtwebengine_locales_dir, exist_ok=True)

                        for locale_file in glob_glob(os_join(locale_path, "*.pak")):
                            dest_file = os_join(
                                qtwebengine_locales_dir, os_basename(locale_file)
                            )
                            shutil_copy2(locale_file, dest_file)
                            logger.debug(
                                f"Copied WebEngine locale: {os_basename(locale_file)}"
                            )

                        logger.success(
                            f"Added {len(glob_glob(os_join(locale_path, '*.pak')))} WebEngine locales"
                        )
                        break

        # Deploy (matches main.cpp workflow)
        success = deployer.deploy_qt(
            binary_path, output_path, desktop_file, icon_file, apprun_file
        )

        if success:
            # Verify QtWebEngine resources after deployment
            verify_webengine_resources(output_path)

            # NSS libraries are now handled by qt_deployer.py during normal dependency collection
            # This prevents conflicts between manual copying and automatic exclusion logic
            logger.info(
                "NSS libraries for QtWebEngine are handled automatically by dependency collector"
            )

            logger.success(f"✅ Successfully deployed to: {output_path}")
            logger.info("🎉 Deployment completed successfully!")
            logger.info(
                f"💡 To test your AppDir, run: {os_join(output_path, 'AppRun')}"
            )
        else:
            logger.error("❌ Deployment failed!")

        sys_exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        sys_exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys_exit(1)


if __name__ == "__main__":
    main()
