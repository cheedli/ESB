from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy import func, text, extract, case, and_, desc
from sqlalchemy.sql import label
from app import db
from app.models import User, Course, Enrollment, Quiz, QuizQuestion, Document, ChatSession, ChatMessage, Chapter
from app.models import UserSession
import calendar
from collections import defaultdict
import json

insights_bp = Blueprint('insights', __name__)




@insights_bp.route('/teacher/insights/course/<int:course_id>')
@login_required
def course_insights(course_id):
    """Insights for a specific course"""
    if not current_user.is_teacher:
        flash('Access denied. Teacher permissions required.', 'danger')
        return redirect(url_for('courses.index'))
    
    # Check if the course belongs to the teacher
    course = Course.query.filter_by(id=course_id, teacher_id=current_user.id).first_or_404()
    
    # Get enrolled students
    enrollments = Enrollment.query.filter_by(course_id=course_id).all()
    enrolled_students = []
    
    for enrollment in enrollments:
        student = User.query.get(enrollment.student_id)
        
        # Get chapters for this course
        chapters = Chapter.query.filter_by(course_id=course_id).all()
        chapter_ids = [chapter.id for chapter in chapters]
        
        # Get documents for these chapters
        document_ids = []
        if chapter_ids:
            documents = Document.query.filter(Document.chapter_id.in_(chapter_ids)).all()
            document_ids = [doc.id for doc in documents]
        
        # Get quiz statistics for this student
        total_quizzes = 0
        avg_score = 0
        
        if document_ids:
            # Count quizzes taken
            total_quizzes = Quiz.query.filter(
                Quiz.student_id == student.id,
                Quiz.document_id.in_(document_ids)
            ).count()
            
            # Get average quiz score
            result = db.session.query(func.avg(Quiz.score).label('avg_score')).filter(
                Quiz.student_id == student.id,
                Quiz.document_id.in_(document_ids),
                Quiz.score.isnot(None)
            ).first()
            
            avg_score = round(result.avg_score, 2) if result.avg_score and result.avg_score > 0 else 0
        
        # Get chat sessions count (engagement)
        chat_sessions_count = 0
        if document_ids:
            chat_sessions_count = ChatSession.query.filter(
                ChatSession.user_id == student.id,
                ChatSession.document_id.in_(document_ids)
            ).count()
        
        enrolled_students.append({
            'student': student,
            'enrolled_at': enrollment.enrolled_at,
            'total_quizzes': total_quizzes,
            'avg_score': avg_score,
            'engagement': chat_sessions_count
        })
    
    # Sort students by average score (descending)
    enrolled_students.sort(key=lambda x: x['avg_score'], reverse=True)
    
    # Get performance by chapter
    chapter_performance = []
    chapters = Chapter.query.filter_by(course_id=course_id).order_by(Chapter.order).all()
    
    for chapter in chapters:
        # Get documents for this chapter
        documents = Document.query.filter_by(chapter_id=chapter.id).all()
        document_ids = [doc.id for doc in documents]
        
        if not document_ids:
            continue
            
        # Get average quiz score for this chapter
        result = db.session.query(func.avg(Quiz.score).label('avg_score')).filter(
            Quiz.document_id.in_(document_ids),
            Quiz.score.isnot(None)
        ).first()
        
        avg_score = round(result.avg_score, 2) if result.avg_score else 0
        
        # Get quiz count
        quiz_count = Quiz.query.filter(Quiz.document_id.in_(document_ids)).count()
        
        # Skip chapters with no quiz activity
        if quiz_count > 0:
            chapter_performance.append({
                'chapter': chapter.title,
                'avg_score': avg_score,
                'quiz_count': quiz_count
            })
    
    return render_template(
        'insights/course_insights.html',
        title=f'Insights for {course.title}',
        course=course,
        enrolled_students=enrolled_students,
        chapter_performance=chapter_performance
    )

@insights_bp.route('/api/insights/student/<int:student_id>/activity')
@login_required
def student_activity_api(student_id):
    """API endpoint for student activity data - for AJAX charts"""
    if not current_user.is_teacher:
        return jsonify({'error': 'Access denied'}), 403
    
    # Verify the student exists
    student = User.query.filter_by(id=student_id, is_teacher=False).first_or_404()
    
    # Check if the student is enrolled in any of the teacher's courses
    student_enrollments = db.session.query(Enrollment)\
        .join(Course, Enrollment.course_id == Course.id)\
        .filter(
            Enrollment.student_id == student_id,
            Course.teacher_id == current_user.id
        ).all()
    
    if not student_enrollments:
        return jsonify({'error': 'Student not enrolled in your courses'}), 403
    
    # Get course IDs where the student is enrolled
    course_ids = [enrollment.course_id for enrollment in student_enrollments]
    
    # Get document IDs from the courses the student is enrolled in
    chapter_ids = []
    for course_id in course_ids:
        chapters = Chapter.query.filter_by(course_id=course_id).all()
        chapter_ids.extend([chapter.id for chapter in chapters])
    
    document_ids = []
    if chapter_ids:
        documents = Document.query.filter(Document.chapter_id.in_(chapter_ids)).all()
        document_ids = [doc.id for doc in documents]
    
    # Get activity data for the last 30 days
    days = 30
    data = {
        'dates': [],
        'quiz_count': [],
        'chat_count': []
    }
    
    today = datetime.now().date()
    
    for i in range(days-1, -1, -1):
        date = today - timedelta(days=i)
        data['dates'].append(date.strftime('%b %d'))
        
        # Count quizzes on this date
        quiz_count = 0
        if document_ids:
            quiz_count = Quiz.query.filter(
                Quiz.student_id == student_id,
                Quiz.document_id.in_(document_ids),
                func.date(Quiz.created_at) == date
            ).count()
        
        data['quiz_count'].append(quiz_count)
        
        # Count chat sessions on this date
        chat_count = 0
        if document_ids:
            chat_count = ChatSession.query.filter(
                ChatSession.user_id == student_id,
                ChatSession.document_id.in_(document_ids),
                func.date(ChatSession.created_at) == date
            ).count()
        
        data['chat_count'].append(chat_count)
    
    return jsonify(data)

@insights_bp.route('/teacher/insights/student/<int:student_id>/course/<int:course_id>')
@login_required
def student_course_details(student_id, course_id):
    """Detailed insights for a specific student's performance in a course"""
    if not current_user.is_teacher:
        flash('Access denied. Teacher permissions required.', 'danger')
        return redirect(url_for('courses.index'))
    
    # Verify the student exists
    student = User.query.filter_by(id=student_id, is_teacher=False).first_or_404()
    
    # Verify the course belongs to the teacher
    course = Course.query.filter_by(id=course_id, teacher_id=current_user.id).first_or_404()
    
    # Check if the student is enrolled in this course
    enrollment = Enrollment.query.filter_by(
        student_id=student_id,
        course_id=course_id
    ).first_or_404()
    
    # Get chapters for this course
    chapters = Chapter.query.filter_by(course_id=course_id).order_by(Chapter.order).all()
    chapter_data = []
    
    for chapter in chapters:
        # Get documents for this chapter
        documents = Document.query.filter_by(chapter_id=chapter.id).all()
        document_data = []
        
        chapter_quiz_count = 0
        chapter_avg_score = 0
        total_quiz_scores = 0
        quiz_count_with_scores = 0
        
        for document in documents:
            # Get quizzes for this document by the student
            doc_quizzes = Quiz.query.filter_by(
                document_id=document.id,
                student_id=student_id
            ).order_by(Quiz.created_at.desc()).all()
            
            document_quiz_count = len(doc_quizzes)
            document_avg_score = 0
            
            # Calculate average score for document quizzes
            if document_quiz_count > 0:
                doc_scores = [q.score for q in doc_quizzes if q.score is not None]
                if doc_scores:
                    document_avg_score = sum(doc_scores) / len(doc_scores)
                    total_quiz_scores += sum(doc_scores)
                    quiz_count_with_scores += len(doc_scores)
            
            # Get chat sessions for this document by the student
            chat_sessions = ChatSession.query.filter_by(
                document_id=document.id,
                user_id=student_id
            ).order_by(ChatSession.created_at.desc()).all()
            
            document_chat_data = []
            
            for chat in chat_sessions:
                # Get chat messages
                messages = ChatMessage.query.filter_by(session_id=chat.id).order_by(ChatMessage.timestamp).all()
                
                # Calculate session duration using timestamp of last message
                duration = None
                if messages:
                    last_message = messages[-1]
                    duration = (last_message.timestamp - chat.created_at).total_seconds() / 60  # in minutes
                
                document_chat_data.append({
                    'session': chat,
                    'message_count': len(messages),
                    'messages': messages,
                    'duration': round(duration, 1) if duration else None
                })
            
            chapter_quiz_count += document_quiz_count
            
            document_data.append({
                'document': document,
                'quizzes': doc_quizzes,
                'quiz_count': document_quiz_count,
                'avg_score': document_avg_score,
                'chat_sessions': document_chat_data,
                'chat_count': len(document_chat_data)
            })
        
        # Calculate chapter average score
        if quiz_count_with_scores > 0:
            chapter_avg_score = total_quiz_scores / quiz_count_with_scores
        
        chapter_data.append({
            'chapter': chapter,
            'documents': document_data,
            'quiz_count': chapter_quiz_count,
            'avg_score': chapter_avg_score
        })
    
    return render_template(
        'insights/student_course_details.html',
        title=f'{student.username} - {course.title}',
        student=student,
        course=course,
        enrollment=enrollment,
        chapters=chapter_data
    )



# Add this function to the insights_routes.py file

def get_teacher_students(teacher_id):
    """Get all students for a specific teacher"""
    teacher = User.query.get_or_404(teacher_id)
    if not teacher.is_teacher:
        return []
    
    return teacher.get_all_students()

# Then update all relevant routes in insights_routes.py to only show students for this teacher

@insights_bp.route('/teacher/insights')
@login_required
def teacher_insights_dashboard():
    """Main insights dashboard for teachers showing all their courses and students"""
    if not current_user.is_teacher:
        flash('Access denied. Teacher permissions required.', 'danger')
        return redirect(url_for('courses.index'))
    
    # Get all courses taught by the teacher
    courses = Course.query.filter_by(teacher_id=current_user.id).all()
    
    # Get student counts for each course
    course_stats = []
    for course in courses:
        student_count = Enrollment.query.filter_by(course_id=course.id).count()
        
        # Get quiz count for the course
        chapter_ids = [chapter.id for chapter in course.chapters]
        document_ids = []
        if chapter_ids:
            documents = Document.query.filter(Document.chapter_id.in_(chapter_ids)).all()
            document_ids = [doc.id for doc in documents]
        
        quiz_count = 0
        if document_ids:
            quiz_count = Quiz.query.filter(Quiz.document_id.in_(document_ids)).count()
        
        # Calculate average score for course quizzes
        avg_score = 0
        if quiz_count > 0 and document_ids:
            result = db.session.query(func.avg(Quiz.score).label('avg_score')).filter(
                Quiz.document_id.in_(document_ids),
                Quiz.score.isnot(None)
            ).first()
            avg_score = round(result.avg_score, 2) if result.avg_score else 0
        
        course_stats.append({
            'course': course,
            'student_count': student_count,
            'quiz_count': quiz_count,
            'avg_score': avg_score
        })
    
    # Get students for this teacher (not all students)
    enrolled_students_query = get_teacher_students(current_user.id)
    
    return render_template(
        'insights/teacher_dashboard.html',
        title='Teacher Insights Dashboard',
        courses=courses,
        course_stats=course_stats,
        enrolled_students=enrolled_students_query
    )

@insights_bp.route('/teacher/insights/student/<int:student_id>')
@login_required
def student_insights(student_id):
    """Detailed insights for a specific student"""
    # Import needed modules at the beginning of the function
    from sqlalchemy import func, extract, text
    import calendar
    from datetime import datetime
    
    if not current_user.is_teacher:
        flash('Access denied. Teacher permissions required.', 'danger')
        return redirect(url_for('courses.index'))
    
    # Verify the student exists
    student = User.query.filter_by(id=student_id, is_teacher=False).first_or_404()
    
    # Check if student belongs to this teacher
    is_teacher_student = False
    try:
        if hasattr(current_user, 'has_student'):
            is_teacher_student = current_user.has_student(student)
        
        if not is_teacher_student:
            # Try direct query to the association table
            result = db.session.execute(text(
                "SELECT 1 FROM teacher_student WHERE teacher_id = :teacher_id AND student_id = :student_id"
            ), {"teacher_id": current_user.id, "student_id": student_id}).fetchone()
            
            is_teacher_student = result is not None
        
        if not is_teacher_student:
            flash('Access denied. This student is not associated with you.', 'danger')
            return redirect(url_for('insights.teacher_insights_dashboard'))
    except Exception as e:
        print(f"Error checking teacher-student relationship: {e}")
        flash('Error checking student relationship. Please try again.', 'danger')
        return redirect(url_for('insights.teacher_insights_dashboard'))
    
    # Get basic student info
    try:
        # Find enrollments in teacher's courses
        course_ids = [course.id for course in current_user.courses_created]
        student_enrollments = Enrollment.query.filter(
            Enrollment.student_id == student_id,
            Enrollment.course_id.in_(course_ids) if course_ids else False
        ).all()
        
        courses_enrolled = []
        for enrollment in student_enrollments:
            course = Course.query.get(enrollment.course_id)
            if course:
                courses_enrolled.append({
                    'course': course,
                    'enrolled_at': enrollment.enrolled_at
                })
    except Exception as e:
        print(f"Error getting student enrollments: {e}")
        courses_enrolled = []
    
    # Get quiz statistics
    try:
        # Get document IDs from the courses the student is enrolled in
        chapter_ids = []
        for course_id in course_ids:
            chapters = Chapter.query.filter_by(course_id=course_id).all()
            chapter_ids.extend([chapter.id for chapter in chapters])
        
        document_ids = []
        if chapter_ids:
            documents = Document.query.filter(Document.chapter_id.in_(chapter_ids)).all()
            document_ids = [doc.id for doc in documents]
        
        # Get quiz data
        student_quizzes = []
        if document_ids:
            quizzes = Quiz.query.filter(
                Quiz.student_id == student_id,
                Quiz.document_id.in_(document_ids)
            ).order_by(Quiz.created_at.desc()).all()
            
            for quiz in quizzes:
                document = Document.query.get(quiz.document_id) if quiz.document_id else None
                chapter = Chapter.query.get(document.chapter_id) if document else None
                course = Course.query.get(chapter.course_id) if chapter else None
                
                correct_answers = QuizQuestion.query.filter(
                    QuizQuestion.quiz_id == quiz.id,
                    QuizQuestion.is_correct == True
                ).count()
                
                total_questions = QuizQuestion.query.filter(
                    QuizQuestion.quiz_id == quiz.id
                ).count()
                
                student_quizzes.append({
                    'quiz': quiz,
                    'document': document,
                    'chapter': chapter,
                    'course': course,
                    'correct_answers': correct_answers,
                    'total_questions': total_questions
                })
    except Exception as e:
        print(f"Error getting quiz data: {e}")
        student_quizzes = []
    
    # Get chat session data
    try:
        chat_sessions = []
        if document_ids:
            sessions = ChatSession.query.filter(
                ChatSession.user_id == student_id,
                ChatSession.document_id.in_(document_ids)
            ).order_by(ChatSession.created_at.desc()).all()
            
            for session in sessions:
                document = Document.query.get(session.document_id)
                chapter = Chapter.query.get(document.chapter_id) if document else None
                course = Course.query.get(chapter.course_id) if chapter else None
                
                # Count messages in this session
                message_count = ChatMessage.query.filter_by(session_id=session.id).count()
                user_messages = ChatMessage.query.filter_by(
                    session_id=session.id, 
                    is_user=True
                ).count()
                
                # Get the last message timestamp to calculate session duration
                last_message = ChatMessage.query.filter_by(session_id=session.id)\
                    .order_by(ChatMessage.timestamp.desc()).first()
                
                duration = None
                if last_message:
                    duration = (last_message.timestamp - session.created_at).total_seconds() / 60  # in minutes
                
                chat_sessions.append({
                    'session': session,
                    'document': document,
                    'chapter': chapter,
                    'course': course,
                    'message_count': message_count,
                    'user_messages': user_messages,
                    'duration': round(duration, 1) if duration else None
                })
    except Exception as e:
        print(f"Error getting chat sessions: {e}")
        chat_sessions = []
    
    # Get login/logout activity
    try:
        login_sessions = UserSession.query.filter_by(user_id=student_id)\
            .order_by(UserSession.login_time.desc())\
            .limit(30).all()
    except Exception as e:
        print(f"Error getting login sessions: {e}")
        login_sessions = []
    
    # Calculate activity statistics
    try:
        # Calculate total time spent (from login sessions)
        total_session_time = 0
        completed_sessions = [s for s in login_sessions if s.logout_time is not None]
        for session in completed_sessions:
            total_session_time += (session.logout_time - session.login_time).total_seconds() / 60  # in minutes
        
        # Calculate session activity
        session_dates = [session.login_time.date() for session in login_sessions]
        unique_session_dates = len(set(session_dates))
        
        # Last login date
        last_login = login_sessions[0].login_time if login_sessions else None
        
        # Calculate average session time
        avg_session_time = round(total_session_time / len(completed_sessions), 1) if completed_sessions else 0
        
        # Calculate quiz time (if completions are tracked)
        quiz_time = 0
        completed_quizzes = [q['quiz'] for q in student_quizzes if q['quiz'].completed_at is not None]
        for quiz in completed_quizzes:
            if quiz.created_at and quiz.completed_at:
                quiz_time += (quiz.completed_at - quiz.created_at).total_seconds() / 60  # in minutes
        
        # Calculate chat session time
        chat_time = sum([s['duration'] for s in chat_sessions if s['duration'] is not None])
        
        # Total estimated study time
        total_study_time = total_session_time  # Use login sessions as the primary metric
    except Exception as e:
        print(f"Error calculating activity statistics: {e}")
        total_study_time = 0
        avg_session_time = 0
        unique_session_dates = 0
        last_login = None
        quiz_time = 0
        chat_time = 0
    
    # Calculate monthly activity
    try:
        current_year = datetime.utcnow().year
        monthly_activity = [0] * 12  # Initialize with zeros for each month
        
        # Count login activity by month
        monthly_login_counts = db.session.query(
            extract('month', UserSession.login_time).label('month'),
            func.count(UserSession.id).label('count')
        ).filter(
            UserSession.user_id == student_id,
            extract('year', UserSession.login_time) == current_year
        ).group_by('month').all()
        
        for month, count in monthly_login_counts:
            if 1 <= month <= 12:
                monthly_activity[int(month)-1] += count
        
        # Count quiz activity by month
        if document_ids:
            monthly_quiz_counts = db.session.query(
                extract('month', Quiz.created_at).label('month'),
                func.count(Quiz.id).label('count')
            ).filter(
                Quiz.student_id == student_id,
                Quiz.document_id.in_(document_ids),
                extract('year', Quiz.created_at) == current_year
            ).group_by('month').all()
            
            for month, count in monthly_quiz_counts:
                if 1 <= month <= 12:
                    monthly_activity[int(month)-1] += count
        
        # Format for chart
        import json
        activity_labels = [calendar.month_name[i+1] for i in range(12)]
        activity_data = monthly_activity
    except Exception as e:
        print(f"Error calculating monthly activity: {e}")
        activity_labels = [calendar.month_name[i+1] for i in range(12)]
        activity_data = [0] * 12
    
    # Get performance by course
    try:
        performance_by_course = []
        
        for course_id in course_ids:
            course = Course.query.get(course_id)
            if not course:
                continue
                
            chapters = Chapter.query.filter_by(course_id=course_id).all()
            chapter_ids = [chapter.id for chapter in chapters]
            
            course_documents = []
            if chapter_ids:
                course_documents = Document.query.filter(Document.chapter_id.in_(chapter_ids)).all()
            
            document_ids = [doc.id for doc in course_documents]
            
            avg_score = 0
            quiz_count = 0
            
            if document_ids:
                # Get average quiz score for this course
                result = db.session.query(func.avg(Quiz.score).label('avg_score')).filter(
                    Quiz.student_id == student_id,
                    Quiz.document_id.in_(document_ids),
                    Quiz.score.isnot(None)
                ).first()
                
                avg_score = round(result.avg_score , 2) if result.avg_score else 0
                
                # Get quiz count
                quiz_count = Quiz.query.filter(
                    Quiz.student_id == student_id,
                    Quiz.document_id.in_(document_ids)
                ).count()
            
            # Skip courses with no quiz activity
            if quiz_count > 0:
                performance_by_course.append({
                    'course': course.title,
                    'avg_score': avg_score,
                    'quiz_count': quiz_count
                })
    except Exception as e:
        print(f"Error calculating course performance: {e}")
        performance_by_course = []
    
    # Make sure to return a proper response
    return render_template(
        'insights/student_insights.html',
        title=f'Insights for {student.username}',
        student=student,
        courses_enrolled=courses_enrolled,
        student_quizzes=student_quizzes,
        chat_sessions=chat_sessions,
        login_sessions=login_sessions,
        total_study_time=round(total_study_time, 1),
        avg_session_time=avg_session_time,
        unique_session_dates=unique_session_dates,
        last_login=last_login,
        quiz_time=round(quiz_time, 1),
        chat_time=round(chat_time, 1),
        activity_labels=json.dumps(activity_labels),
        activity_data=json.dumps(activity_data),
        performance_by_course=performance_by_course
    )