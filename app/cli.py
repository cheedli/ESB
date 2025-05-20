import click
from flask.cli import with_appcontext
from app import db
from app.models import User

@click.command('create-superuser')
@click.argument('username')
@click.argument('email')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
@with_appcontext
def create_superuser_command(username, email, password):
    """Create a new superuser account"""
    user = User.query.filter_by(username=username).first()
    if user:
        click.echo("Username already exists")
        return
        
    user = User.query.filter_by(email=email).first()
    if user:
        click.echo("Email already exists")
        return
    
    superuser = User(
        username=username,
        email=email,
        is_teacher=True,  # Superuser is also a teacher
        is_superuser=True
    )
    superuser.set_password(password)
    
    db.session.add(superuser)
    db.session.commit()
    
    click.echo(f"Superuser {username} created successfully")

def register_cli_commands(app):
    """Register CLI commands with the Flask application"""
    app.cli.add_command(create_superuser_command)