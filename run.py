"""
Run the Event Analytics Dashboard on port 3005.
Usage: python run.py
Then open http://localhost:3005 in your browser.
"""

from server import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3005, debug=True)
