"""
Run the Event Analytics Dashboard.
Usage: python run.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from h2s_cdi_auth import register_with_portal
from server import app, MODULE_PAGES

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3005))
    module_name = os.environ.get("MODULE_NAME", "Consolidated Event Dashboard")
    base_url = os.environ.get("BASE_URL", f"http://localhost:{port}")
    register_with_portal(MODULE_PAGES, module_name=module_name, base_url=base_url)
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
