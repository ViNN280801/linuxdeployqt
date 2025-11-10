import subprocess
from pathlib import Path
from typing import Optional, Union, List, Dict


class DeployCommandComposer:
    """
    Composes and executes linuxdeployqt-python deployment commands
    based on GUI parameters. Handles all arguments from linuxdeployqt-python-cli.py.
    """

    def __init__(self, verbose_level: int = 1):
        self.verbose_level = verbose_level

    def compose_command(
        self,
        binary_path: str,
        deploy_path: str,
        qml_dirs: List[str],
        desktop_file: str,
        icon_file: str,
        apprun_file: Optional[str] = None,
        qt_path: Optional[str] = None,
        bundle_non_qt_libs: bool = True,
        no_strip: bool = False,
        always_overwrite: bool = False,
    ) -> List[str]:
        """
        Compose the full deployment command as a list of arguments.

        Args match all parameters from linuxdeployqt-python-cli.py
        """
        cmd = [
            "python3",
            str(Path(__file__).parent.parent.parent / "linuxdeployqt-python-cli.py"),
            "--binary-path",
            binary_path,
            "--output-path",
            deploy_path,
            "--desktop-file",
            desktop_file,
            "--icon",
            icon_file,
            "--verbose",
            str(self.verbose_level),
        ]

        # Add QML directories (can be multiple)
        for qml_dir in qml_dirs:
            if qml_dir.strip():  # Skip empty entries
                cmd.extend(["--qml-dir", qml_dir])

        # Add optional Qt path
        if qt_path and qt_path.strip():
            cmd.extend(["--qt-path", qt_path])

        # Add AppRun script if specified
        if apprun_file and apprun_file.strip():
            cmd.extend(["--apprun-file", apprun_file])

        # Add bundling flags
        if not bundle_non_qt_libs:
            cmd.append("--no-bundle-non-qt-libs")

        if no_strip:
            cmd.append("--no-strip")

        if always_overwrite:
            cmd.append("--always-overwrite")

        return cmd

    def execute_deployment(self, cmd: List[str]) -> Dict[str, Union[int, str]]:
        """
        Execute the deployment command in a subprocess.
        Returns dict with:
        - return_code: Process exit code
        - output: Combined stdout/stderr
        """
        try:
            result = subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            return {"return_code": result.returncode, "output": result.stdout}

        except Exception as e:
            return {"return_code": 1, "output": f"Failed to execute command: {str(e)}"}
