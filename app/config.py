import os
from datetime import timedelta
from functools import lru_cache

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-for-development-only')
    
    # Database configuration
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File upload configuration
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx','xls','xlsx','csv'}
    
    # Groq API configuration - will be set dynamically in init_app
    GROQ_API_KEY = None
    GROQ_LLAMA_MODEL = "llama-3.1-8b-instant"
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///esb.db')


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    
    # In production, ensure you set a strong secret key in environment variables
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # Production specific settings
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True


# Create a config dictionary for easier access
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}