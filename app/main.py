import os
from flask import Flask
from app.api.routes import api_bp
from app.scheduler import jobs

def create_app():
    app_instance = Flask(__name__)
    app_instance.register_blueprint(api_bp)
    
    # Start the background dynamic scheduler as a daemon thread
    jobs.start_daemon()
    
    return app_instance

if __name__ == "__main__":
    app_server = create_app()
    port = int(os.environ.get("PORT", 5000))
    app_server.run(host="0.0.0.0", port=port, debug=False)
