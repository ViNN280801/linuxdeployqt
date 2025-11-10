#!/usr/bin/env python3

from os import makedirs as os_makedirs
from os.path import dirname as os_path_dirname
from os.path import abspath as os_path_abspath
from os.path import join as os_path_join
from os.path import basename as os_path_basename
from os.path import exists as os_path_exists

from sys import exit as sys_exit
from sys import path as sys_path

from shutil import copy2 as shutil_copy2
from argparse import ArgumentParser as argparse_ArgumentParser

# Add path to find tools module when running as separate process
script_dir = os_path_dirname(os_path_abspath(__file__))
project_root = os_path_dirname(
    os_path_dirname(script_dir)
)  # Go up 2 levels: gui/core -> gui -> linuxdeployqt
sys_path.insert(0, project_root)

from tools.ldd_dependency_collector import LddDependencyCollector


class LddDeploymentWorker:
    """Worker class for LDD deployment process"""

    def __init__(self, log_level="INFO"):
        self.log_level = log_level

    def deploy_libraries(
        self,
        binary_path,
        deploy_path,
        bundle_all_but_core=True,
        bundle_everything=False,
    ):
        """Deploy libraries using LDD analysis"""
        try:
            # Get binary name for directory
            binary_name = os_path_basename(binary_path).split(".")[0]
            lib_dir = os_path_join(deploy_path, f"{binary_name}_lib")

            print(f"🔍 Starting LDD analysis for: {binary_path}")
            print(f"📁 Target directory: {lib_dir}")

            # Initialize collector
            collector = LddDependencyCollector(log_level=self.log_level)
            collector.set_bundle_mode(
                bundle_all_but_core_libs=bundle_all_but_core,
                bundle_everything=bundle_everything,
            )

            # Get libraries
            libraries = collector.get_libs(binary_path)

            if not libraries:
                print("⚠️  No libraries found to deploy")
                return False

            print(f"📦 Found {len(libraries)} libraries to deploy")

            # Create lib directory
            os_makedirs(lib_dir, exist_ok=True)
            print(f"📁 Created directory: {lib_dir}")

            # Copy libraries with progress
            total = len(libraries)
            for i, lib_path in enumerate(libraries):
                try:
                    if os_path_exists(lib_path):
                        lib_name = os_path_basename(lib_path)
                        dest_path = os_path_join(lib_dir, lib_name)
                        shutil_copy2(lib_path, dest_path)
                        progress = int((i + 1) * 100 / total)
                        print(f"PROGRESS:{progress}:✅ Copied: {lib_name}")
                    else:
                        print(f"⚠️  Library not found: {lib_path}")
                except Exception as e:
                    print(f"❌ Failed to copy {lib_path}: {str(e)}")

            print(f"🎉 Successfully deployed {len(libraries)} libraries to {lib_dir}")
            return True

        except Exception as e:
            print(f"❌ Deployment failed: {str(e)}")
            return False


def main():
    """Main function for command line usage"""
    parser = argparse_ArgumentParser(
        description="Deploy library dependencies using LDD"
    )
    parser.add_argument("binary_path", help="Path to binary/shared library")
    parser.add_argument("deploy_path", help="Target deployment directory")
    parser.add_argument(
        "--bundle-all-but-core",
        action="store_true",
        default=True,
        help="Bundle all but core libraries",
    )
    parser.add_argument(
        "--bundle-everything",
        action="store_true",
        default=False,
        help="Bundle all libraries",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Create worker and run deployment
    worker = LddDeploymentWorker(log_level=args.log_level)
    success = worker.deploy_libraries(
        binary_path=args.binary_path,
        deploy_path=args.deploy_path,
        bundle_all_but_core=args.bundle_all_but_core,
        bundle_everything=args.bundle_everything,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys_exit(main())
