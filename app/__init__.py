import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
import markdown
from markupsafe import Markup

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app(config_name=None):
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        from app.config import DevelopmentConfig
        app.config.from_object(DevelopmentConfig)
    else:
        config_module = __import__(f'app.config', fromlist=[f'{config_name}Config'])
        config_class = getattr(config_module, f'{config_name}Config')
        app.config.from_object(config_class)
        config_class.init_app(app)
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Configure login
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    
    # Register template filters
    register_template_filters(app)
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.courses import courses_bp
    from app.routes.chapters import chapters_bp
    from app.routes.ai import ai_bp
    from app.routes.quiz import quiz_bp
    from app.routes.notes import notes
    from app.routes.insights_routes import insights_bp  
    from app.routes.superuser import superuser  

    app.register_blueprint(insights_bp, url_prefix='/insights')  
    app.register_blueprint(quiz_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(chapters_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(superuser)
    app.register_blueprint(notes, url_prefix='/notes')
    from app.cli import register_cli_commands
    register_cli_commands(app)


    return app

def register_template_filters(app):
    @app.template_filter('markdown')
    def markdown_filter(text):
        if text is None:
            return ""
        html = markdown.markdown(text, extensions=['extra'])
        return Markup(html)