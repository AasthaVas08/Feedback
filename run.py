"""Entry point for running the Flask application.

Usage
-----
    export FLASK_APP=run.py
    flask run            # development server
    flask db upgrade     # apply migrations
    python run.py        # alternative: runs on port 5000
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
