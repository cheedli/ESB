from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length
from app.models import Course, Chapter, Enrollment, User
from app import db

courses_bp = Blueprint('courses', __name__, url_prefix='/courses')

# Forms
class CourseForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField('Description', validators=[Length(max=500)])
    submit = SubmitField('Save Course')

@courses_bp.route('/')
@login_required
def index():
    if current_user.is_teacher:
        # Teachers see courses they created
        courses = Course.query.filter_by(teacher_id=current_user.id).order_by(Course.created_at.desc()).all()
        available_courses = None
    else:
        # Students see courses they're enrolled in
        enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
        courses = [enrollment.course for enrollment in enrollments]
        
        # Get teacher IDs for teachers associated with this student
        try:
            # Get teachers for this student via the relationship
            teachers = current_user.teachers.all()
            teacher_ids = [teacher.id for teacher in teachers]
            
            # If relationship fails, try direct query to the association table
            if not teacher_ids:
                from sqlalchemy import text
                result = db.session.execute(text(
                    "SELECT teacher_id FROM teacher_student WHERE student_id = :student_id"
                ), {"student_id": current_user.id}).fetchall()
                teacher_ids = [row[0] for row in result]
            
            # Get enrolled course IDs
            enrolled_course_ids = [enrollment.course_id for enrollment in enrollments]
            
            # Get available courses from associated teachers that student isn't enrolled in yet
            available_courses = Course.query.filter(
                Course.teacher_id.in_(teacher_ids),
                ~Course.id.in_(enrolled_course_ids) if enrolled_course_ids else True
            ).all()
        except Exception as e:
            print(f"Error getting available courses: {e}")
            available_courses = []
    
    return render_template('courses/index.html', 
                          title='Courses',
                          courses=courses,
                          available_courses=available_courses)

@courses_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    # Only teachers can create courses
    if not current_user.is_teacher:
        flash('Only teachers can create courses.', 'warning')
        return redirect(url_for('courses.index'))
    
    form = CourseForm()
    if form.validate_on_submit():
        course = Course(
            title=form.title.data,
            description=form.description.data,
            teacher_id=current_user.id
        )
        db.session.add(course)
        db.session.commit()
        
        flash(f'Course "{course.title}" has been created!', 'success')
        return redirect(url_for('courses.view', course_id=course.id))
    
    return render_template('courses/create.html', title='Create Course', form=form)

@courses_bp.route('/<int:course_id>')
@login_required
def view(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Check if user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course_id).first():
        flash('You need to enroll in this course first.', 'warning')
        return redirect(url_for('courses.enroll', course_id=course_id))
    
    # Get chapters in order
    chapters = course.chapters.order_by(Chapter.order).all()
    
    return render_template('courses/view.html', 
                          title=course.title,
                          course=course,
                          chapters=chapters)

@courses_bp.route('/<int:course_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Only the teacher who created the course can edit it
    if course.teacher_id != current_user.id:
        abort(403)
    
    form = CourseForm()
    if form.validate_on_submit():
        course.title = form.title.data
        course.description = form.description.data
        db.session.commit()
        
        flash(f'Course "{course.title}" has been updated!', 'success')
        return redirect(url_for('courses.view', course_id=course.id))
    
    # Pre-populate form with existing data
    if request.method == 'GET':
        form.title.data = course.title
        form.description.data = course.description
    
    return render_template('courses/create.html', 
                          title=f'Edit {course.title}',
                          form=form, 
                          course=course)

@courses_bp.route('/<int:course_id>/delete', methods=['POST'])
@login_required
def delete(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Only the teacher who created the course can delete it
    if course.teacher_id != current_user.id:
        abort(403)
    
    title = course.title
    db.session.delete(course)
    db.session.commit()
    
    flash(f'Course "{title}" has been deleted!', 'success')
    return redirect(url_for('courses.index'))

@courses_bp.route('/<int:course_id>/enroll', methods=['GET', 'POST'])
@login_required
def enroll(course_id):
    # Only students can enroll in courses
    if current_user.is_teacher:
        flash('Teachers cannot enroll in courses.', 'warning')
        return redirect(url_for('courses.index'))
    
    course = Course.query.get_or_404(course_id)
    teacher = User.query.get(course.teacher_id)
    
    if not teacher:
        flash('Error: Course has no assigned teacher.', 'danger')
        return redirect(url_for('courses.index'))
    
    # Check if the student is associated with the teacher
    is_associated = False
    try:
        # Try using the relationship method if available
        if hasattr(teacher, 'has_student'):
            is_associated = teacher.has_student(current_user)
        
        # If relationship check fails, try a direct query to the association table
        if not is_associated:
            from sqlalchemy import text
            result = db.session.execute(text(
                "SELECT 1 FROM teacher_student WHERE teacher_id = :teacher_id AND student_id = :student_id"
            ), {"teacher_id": teacher.id, "student_id": current_user.id}).fetchone()
            
            is_associated = result is not None
        
        if not is_associated:
            flash('You cannot enroll in this course. Please contact the teacher.', 'danger')
            return redirect(url_for('courses.index'))
    except Exception as e:
        print(f"Error checking teacher-student relationship: {e}")
    
    # Check if already enrolled
    existing_enrollment = Enrollment.query.filter_by(
        student_id=current_user.id, 
        course_id=course_id
    ).first()
    
    if existing_enrollment:
        flash(f'You are already enrolled in "{course.title}".', 'info')
        return redirect(url_for('courses.view', course_id=course_id))
    
    # Process enrollment
    if request.method == 'POST':
        enrollment = Enrollment(
            student_id=current_user.id,
            course_id=course_id
        )
        db.session.add(enrollment)
        db.session.commit()
        
        flash(f'You have successfully enrolled in "{course.title}"!', 'success')
        return redirect(url_for('courses.view', course_id=course_id))
    
    return render_template('courses/enroll.html', title='Enroll in Course', course=course)
