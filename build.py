"""Convenience build script for GermanSpeak PDF Reader .exe"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

def main():
    print("Activating venv and building GermanSpeak-PDF-Reader.exe ...")
    # On Windows the venv python is reliable
    python = HERE / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = sys.executable

    cmd = [
        str(python), "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "GermanSpeak-PDF-Reader",
        "--icon", "icons/icon48.jpg",
        "--add-data", "icons;icons",
        "app.py"
    ]

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=HERE)
    print("\n✅ Build finished!")
    print(f"   Your .exe is here: {HERE / 'dist' / 'GermanSpeak-PDF-Reader.exe'}")

if __name__ == "__main__":
    main()
