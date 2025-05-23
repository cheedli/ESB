from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager
import os
from flask import current_app
from werkzeug.utils import secure_filename
from datetime import datetime

class UserSession(db.Model):
    """Model to track user login/logout activities"""
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    login_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    logout_time = db.Column(db.DateTime, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv6 can be up to 45 chars
    user_agent = db.Column(db.String(255), nullable=True)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('sessions', lazy=True))
    
    def __init__(self, user_id, ip_address=None, user_agent=None):
        self.user_id = user_id
        self.ip_address = ip_address
        self.user_agent = user_agent
    
    def record_logout(self):
        """Record the logout time for this session"""
        self.logout_time = datetime.utcnow()
        
    @property
    def duration(self):
        """Calculate session duration in minutes"""
        if self.logout_time:
            return round((self.logout_time - self.login_time).total_seconds() / 60, 1)
        return None
    
    @property
    def is_active(self):
        """Check if the session is still active (no logout recorded)"""
        return self.logout_time is None
    
    def __repr__(self):
        return f'<UserSession {self.id} - User {self.user_id}>'

class TeacherStudent(db.Model):
    __tablename__ = 'teacher_student'
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)

    # Optional: Add extra fields like timestamp or status if needed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    teacher = db.relationship('User', foreign_keys=[teacher_id], backref='teacher_links')
    student = db.relationship('User', foreign_keys=[student_id], backref='student_links')


# Creating a Class model for student assignment
class Classe(db.Model):
    __tablename__ = 'classe'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    students = db.relationship('User', backref='classe', lazy='dynamic')
    
    def __repr__(self):
        return f'<Classe {self.name}>'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_teacher = db.Column(db.Boolean, default=False)
    is_superuser = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_first_login = db.Column(db.Boolean, default=False)
    groq_api_key = db.Column(db.String(255))
    
    # Adding class relationship
    class_id = db.Column(db.Integer, db.ForeignKey('classe.id'), nullable=True)

    courses_created = db.relationship('Course', backref='teacher', lazy='dynamic')
    enrollments = db.relationship('Enrollment', backref='student', lazy='dynamic')

    students = db.relationship(
        'User',
        secondary='teacher_student',
        primaryjoin='User.id == TeacherStudent.teacher_id',
        secondaryjoin='User.id == TeacherStudent.student_id',
        backref=db.backref('teachers', lazy='dynamic', overlaps="teacher_links,student_links"),
        lazy='dynamic',
        overlaps="teacher_links,student_links" 
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(
            password, 
            method='pbkdf2:sha256', 
        )
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def add_student(self, student):
        if not (self.is_teacher or self.is_superuser) or student.is_teacher or self.has_student(student):
            return False
        link = TeacherStudent(teacher=self, student=student)
        db.session.add(link)
        return True

    def remove_student(self, student):
        if not (self.is_teacher or self.is_superuser):
            return False
        link = TeacherStudent.query.filter_by(teacher_id=self.id, student_id=student.id).first()
        if link:
            db.session.delete(link)
            return True
        return False

    def has_student(self, student):
        return TeacherStudent.query.filter_by(teacher_id=self.id, student_id=student.id).count() > 0

    def get_all_students(self):
        return [link.student for link in self.teacher_links]
        
    # Superuser specific methods
    def create_user(self, username, email, password, is_teacher=False, is_superuser=False, class_id=None):
        """Create a new user (superuser only)"""
        if not self.is_superuser:
            return None
            
        user = User(
            username=username,
            email=email,
            is_teacher=is_teacher,
            is_superuser=is_superuser,
            class_id=class_id
        )
        user.set_password(password)
        db.session.add(user)
        return user
    
    def link_teacher_student(self, teacher_id, student_id):
        """Create a relationship between teacher and student (superuser only)"""
        if not self.is_superuser:
            return False
            
        teacher = User.query.get(teacher_id)
        student = User.query.get(student_id)
        
        if not teacher or not student or not teacher.is_teacher or student.is_teacher:
            return False
            
        # Check if relationship already exists
        if TeacherStudent.query.filter_by(teacher_id=teacher_id, student_id=student_id).first():
            return False
            
        link = TeacherStudent(teacher_id=teacher_id, student_id=student_id)
        db.session.add(link)
        return True
    
    def link_teacher_to_class(self, teacher_id, class_id):
        """Link a teacher to all students in a class (superuser only)"""
        if not self.is_superuser:
            return False, "Superuser privileges required"
            
        teacher = User.query.get(teacher_id)
        class_obj = Classe.query.get(class_id)
        
        if not teacher or not class_obj:
            return False, "Teacher or class not found"
            
        if not teacher.is_teacher:
            return False, "Selected user is not a teacher"
            
        # Get all students in the class
        students = User.query.filter_by(class_id=class_id, is_teacher=False).all()
        
        success_count = 0
        for student in students:
            # Check if relationship already exists
            if not TeacherStudent.query.filter_by(teacher_id=teacher_id, student_id=student.id).first():
                link = TeacherStudent(teacher_id=teacher_id, student_id=student.id)
                db.session.add(link)
                success_count += 1
        
        return True, f"Added {success_count} students to teacher"
    
    def unlink_teacher_student(self, teacher_id, student_id):
        """Remove a relationship between teacher and student (superuser only)"""
        if not self.is_superuser:
            return False
            
        link = TeacherStudent.query.filter_by(teacher_id=teacher_id, student_id=student_id).first()
        if link:
            db.session.delete(link)
            return True
        return False
    
    def promote_to_teacher(self, user_id):
        """Promote a user to teacher role (superuser only)"""
        if not self.is_superuser:
            return False
            
        user = User.query.get(user_id)
        if user:
            user.is_teacher = True
            return True
        return False
    
    def demote_from_teacher(self, user_id):
        """Demote a teacher to regular user (superuser only)"""
        if not self.is_superuser:
            return False
            
        user = User.query.get(user_id)
        if user and user.is_teacher and not user.is_superuser:  # Cannot demote superusers
            user.is_teacher = False
            return True
        return False
    
    def get_all_users(self):
        """Get all users in the system (superuser only)"""
        if not self.is_superuser:
            return []
            
        return User.query.all()
    
    def get_all_teachers(self):
        """Get all teachers in the system (superuser only)"""
        if not self.is_superuser:
            return []
            
        return User.query.filter_by(is_teacher=True).all()

    def __repr__(self):
        return f'<User {self.username}>'




@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


# Create superuser command function (to be used in a CLI command)
def create_superuser(username, email, password):
    """
    Create a new superuser account
    This function should be called from a Flask CLI command
    """
    user = User.query.filter_by(username=username).first()
    if user:
        return False, "Username already exists"
        
    user = User.query.filter_by(email=email).first()
    if user:
        return False, "Email already exists"
    
    superuser = User(
        username=username,
        email=email,
        is_teacher=True,  # Superuser is also a teacher
        is_superuser=True
    )
    superuser.set_password(password)
    
    db.session.add(superuser)
    db.session.commit()
    
    return True, f"Superuser {username} created successfully"


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    chapters = db.relationship('Chapter', backref='course', lazy='dynamic', cascade='all, delete-orphan')
    enrollments = db.relationship('Enrollment', backref='course', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Course {self.title}>'

class Chapter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    documents = db.relationship('Document', backref='chapter', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Chapter {self.title}>'
        
    def has_summary(self):
        """Check if the chapter has a summary"""
        return self.summary is not None and len(self.summary.strip()) > 0
        
    def clear_summary(self):
        """Clear the chapter summary"""
        self.summary = None
        
    def get_document_count(self):
        """Get the number of documents in the chapter"""
        return self.documents.count()
        
    def get_all_documents(self):
        """Get all documents in the chapter"""
        return self.documents.all()
        
    def has_documents(self):
        """Check if the chapter has any documents"""
        return self.get_document_count() > 0
        
    @property
    def truncated_summary(self, max_length=200):
        """Get a truncated version of the summary for display"""
        if not self.summary:
            return "No summary available."
        
        if len(self.summary) <= max_length:
            return self.summary
            
        return self.summary[:max_length] + "..."

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='unique_enrollment'),
    )
    
    def __repr__(self):
        return f'<Enrollment {self.student_id} - {self.course_id}>'

class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    messages = db.relationship('ChatMessage', backref='session', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<ChatSession {self.id}>'

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_user = db.Column(db.Boolean, default=True)  # True if from user, False if from AI
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ChatMessage {self.id}>'

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)  # pdf, doc, docx, ppt, pptx
    summary = db.Column(db.Text)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapter.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = db.relationship('Note', backref='document', lazy=True, cascade="all, delete-orphan")

    
    def __repr__(self):
        return f'<Document {self.title}>'

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=True)  # Changed to nullable=True
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    num_questions = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Float, nullable=True) 
    feedback = db.Column(db.Text, nullable=True)  
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    document = db.relationship('Document', backref=db.backref('quizzes', cascade='all, delete-orphan'), lazy='joined')
    student = db.relationship('User', backref='quizzes')
    questions = db.relationship('QuizQuestion', backref='quiz', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Quiz {self.id} - {self.difficulty}>'


class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    choice_a = db.Column(db.Text, nullable=False)
    choice_b = db.Column(db.Text, nullable=False)
    choice_c = db.Column(db.Text, nullable=False)
    correct_choice = db.Column(db.String(1), nullable=False)  # 'A', 'B', or 'C'
    student_choice = db.Column(db.String(1), nullable=True)  # 'A', 'B', or 'C'
    is_correct = db.Column(db.Boolean, nullable=True)
    explanation = db.Column(db.Text, nullable=True)  # Explanation for the correct answer
    
    def __repr__(self):
        return f'<QuizQuestion {self.id}>'
  
class Note(db.Model):
    __tablename__ = 'notes'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Fixed foreign key references to match actual table names
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('notes', lazy=True))
    
    # Remove duplicate relationship since Document already has notes relationship
    # document = db.relationship('Document', backref=db.backref('notes', lazy=True))
    
    def __init__(self, user_id, document_id, content=None, image_file=None):
        self.user_id = user_id
        self.document_id = document_id
        self.content = content
        
        # Handle image upload if provided
        if image_file:
            filename = secure_filename(image_file.filename)
            # Create a unique filename to avoid collisions
            unique_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
            # Path is relative to upload folder config
            self.image_path = os.path.join('notes_images', unique_filename)
            
            # Create directory if it doesn't exist
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'notes_images')
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            
            # Save the file
            image_file.save(os.path.join(upload_dir, unique_filename))
    
    def to_dict(self):
        """Convert the note object to a dictionary for JSON responses"""
        from flask import url_for
        
        result = {
            'id': self.id,
            'content': self.content,
            'created_at': self.created_at.strftime('%b %d, %Y, %I:%M %p'),
            'user_id': self.user_id,
            'document_id': self.document_id
        }
        
        if self.image_path:
            result['image_path'] = self.image_path
            result['image_url'] = url_for('notes.serve_note_image', filename=self.image_path)
        
        return result
    
    def delete_file(self):
        """Delete the associated image file if it exists"""
        if self.image_path:
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], self.image_path)
            if os.path.exists(file_path):
                os.remove(file_path)