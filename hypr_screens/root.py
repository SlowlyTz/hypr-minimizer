"""Running a one-time setup script as root: pkexec (a password dialog) from the
settings window, sudo from a terminal."""
import os
import shutil
import subprocess
import tempfile


def run_as_root(text: str, graphical: bool) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as script:
        script.write(text)
    try:
        elevate = ["pkexec"] if graphical or not shutil.which("sudo") else ["sudo"]
        return subprocess.run([*elevate, "/bin/sh", script.name], check=False).returncode == 0
    finally:
        os.unlink(script.name)
