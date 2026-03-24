import logging
import os
import atexit
import threading
from flask import Flask
from flasgger import Swagger
from app.api.routes import api_bp
from app.core import discovery, speaker_cache
from app.scheduler import jobs


_shutdown_registered = False
_shutdown_lock = threading.Lock()


def _shutdown_background_services() -> None:
    speaker_cache.stop_ws_listeners()
    discovery.stop_device_cache()
    jobs.shutdown_daemon()


def _register_shutdown_once() -> None:
    global _shutdown_registered
    with _shutdown_lock:
        if _shutdown_registered:
            return
        atexit.register(_shutdown_background_services)
        _shutdown_registered = True


def configure_logging():
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

def create_app():
    configure_logging()
    _register_shutdown_once()
    app_instance = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
        static_url_path="/app-static"
    )
    
    # Initialize OpenAPI specification and Swagger UI on /apidocs/
    Swagger(app_instance, template={
        "info": {
            "title": "SoundTouch Service API",
            "description": "API for discovering, controlling, and scheduling SoundTouch speakers.",
            "version": "1.0.0"
        }
    })
    
    app_instance.register_blueprint(api_bp)
    
    # Start the background dynamic scheduler as a daemon thread
    jobs.start_daemon()
    
    # Refresh the discovery cache immediately and attach listeners for newly found speakers.
    discovery.start_device_cache(on_refresh=speaker_cache.start_ws_listeners)
    
    return app_instance

if __name__ == "__main__":
    app_server = create_app()
    port = int(os.environ.get("PORT", 9001))
    app_server.run(host="0.0.0.0", port=port, debug=False)
