import os
from app import create_app
from config import Config, ProductionConfig

config_class = ProductionConfig if os.getenv('CAREERHUB_ENV', '').lower() == 'production' else Config
app = create_app(config_class)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
