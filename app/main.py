import os
from flask import Flask
from flasgger import Swagger
from app.api.routes import api_bp
from app.core import discovery, speaker_cache
from app.scheduler import jobs

def create_app():
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
    
    # Start the device IP cache (one mDNS scan now, refresh every 5 min)
    discovery.start_device_cache()
    
    # Start WebSocket listeners for each speaker found in the cache
    speaker_cache.start_ws_listeners(discovery.get_all_cached_devices())
    
    return app_instance

if __name__ == "__main__":
    app_server = create_app()
    port = int(os.environ.get("PORT", 9001))
    app_server.run(host="0.0.0.0", port=port, debug=False)
