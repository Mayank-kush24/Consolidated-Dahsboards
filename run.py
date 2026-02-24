"""
Run the Event Analytics Dashboard on port 3005.
Usage: python run.py
Then open http://localhost:3005 in your browser.
"""

import subprocess
import sys

if __name__ == "__main__":
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.port=3005",
            "--server.headless=true",
        ],
        check=True,
    )
