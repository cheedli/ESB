from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, RadioField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, NumberRange
from datetime import datetime
from app import db
from app.models import Document, Quiz, QuizQuestion, Enrollment, Course, Chapter
from app.services.ai_service import generate_quiz_questions, generate_quiz_feedback
import re
from flask import Markup

quiz_bp = Blueprint('quiz', __name__, url_prefix='/quiz')

# Forms
class QuizSetupForm(FlaskForm):
    difficulty = SelectField('Difficulty', 
                           choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')],
                           validators=[DataRequired()])
    num_questions = IntegerField('Number of Questions', 
                               validators=[DataRequired(), NumberRange(min=3, max=20)],
                               default=5)
    submit = SubmitField('Start Quiz')

class QuizAnswerForm(FlaskForm):
    answer = RadioField('Your Answer', 
                      choices=[('A', 'A'), ('B', 'B'), ('C', 'C')],
                      validators=[DataRequired()])
    submit = SubmitField('Submit Answer')

# Routes
@quiz_bp.route('/setup/<int:document_id>', methods=['GET', 'POST'])
@login_required
def setup(document_id):
    document = Document.query.get_or_404(document_id)
    chapter = document.chapter
    course = chapter.course
    
    # Check if user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id).first():
        flash('You need to enroll in this course first.', 'warning')
        return redirect(url_for('courses.enroll', course_id=course.id))
    
    # Only students can take quizzes
    if current_user.is_teacher:
        flash('Only students can take quizzes.', 'warning')
        return redirect(url_for('chapters.view_document', document_id=document_id))
    
    form = QuizSetupForm()
    if form.validate_on_submit():
        # Create a new quiz
        quiz = Quiz(
            document_id=document_id,
            student_id=current_user.id,
            difficulty=form.difficulty.data,
            num_questions=form.num_questions.data
        )
        db.session.add(quiz)
        db.session.commit()
        
        # Generate questions
        try:
            # Use document summary as context for generating questions
            questions = generate_quiz_questions(
                document_summary=document.summary,
                difficulty=form.difficulty.data,
                num_questions=form.num_questions.data
            )
            
            # Save the generated questions
            for question_data in questions:
                quiz_question = QuizQuestion(
                    quiz_id=quiz.id,
                    question_text=question_data['question'],
                    choice_a=question_data['choice_a'],
                    choice_b=question_data['choice_b'],
                    choice_c=question_data['choice_c'],
                    correct_choice=question_data['correct_choice'],
                    explanation=question_data.get('explanation', '')
                )
                db.session.add(quiz_question)
            
            db.session.commit()
            flash('Quiz has been created. Good luck!', 'success')
            return redirect(url_for('quiz.take', quiz_id=quiz.id, question_index=0))
            
        except Exception as e:
            db.session.delete(quiz)
            db.session.commit()
            flash(f'Failed to generate quiz questions: {str(e)}', 'danger')
            return redirect(url_for('quiz.setup', document_id=document_id))
    
    return render_template('quiz/setup.html',
                          title='Quiz Setup',
                          document=document,
                          chapter=chapter,
                          course=course,
                          form=form)

@quiz_bp.route('/take/<int:quiz_id>/<int:question_index>', methods=['GET', 'POST'])
@login_required
def take(quiz_id, question_index):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Ensure the current user owns this quiz
    if quiz.student_id != current_user.id:
        abort(403)
    
    # Check if quiz is already completed
    if quiz.completed_at is not None:
        flash('This quiz has already been completed.', 'info')
        return redirect(url_for('quiz.results', quiz_id=quiz_id))
    
    # Get the document and course for breadcrumbs
    document = quiz.document
    chapter = document.chapter
    course = chapter.course
    
    # Get all questions and check if the index is valid
    questions = quiz.questions.all()
    if question_index >= len(questions):
        # If we've gone beyond the last question, calculate score and redirect to results
        return redirect(url_for('quiz.complete', quiz_id=quiz_id))
    
    current_question = questions[question_index]
    form = QuizAnswerForm()
    
    if form.validate_on_submit():
        # Save the student's choice
        student_choice = form.answer.data
        current_question.student_choice = student_choice
        
        # Check if the answer is correct
        is_correct = student_choice == current_question.correct_choice
        current_question.is_correct = is_correct
        
        db.session.commit()
        
        # Move to the next question
        return redirect(url_for('quiz.take', quiz_id=quiz_id, question_index=question_index + 1))
    
    # For GET request or form validation failure
    total_questions = len(questions)
    progress = (question_index / total_questions) * 100
    
    return render_template('quiz/take.html',
                          title='Take Quiz',
                          quiz=quiz,
                          document=document,
                          chapter=chapter,
                          course=course,
                          question=current_question,
                          question_index=question_index,
                          total_questions=total_questions,
                          progress=progress,
                          form=form)

@quiz_bp.route('/complete/<int:quiz_id>', methods=['GET'])
@login_required
def complete(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Ensure the current user owns this quiz
    if quiz.student_id != current_user.id:
        abort(403)
    
    # Check if quiz is already completed
    if quiz.completed_at is not None:
        flash('This quiz has already been completed.', 'info')
        return redirect(url_for('quiz.results', quiz_id=quiz_id))
    
    # Calculate the score
    questions = quiz.questions.all()
    correct_count = sum(1 for q in questions if q.is_correct)
    total_count = len(questions)
    
    if total_count > 0:
        score = (correct_count / total_count) * 100
    else:
        score = 0
    
    quiz.score = score
    quiz.completed_at = datetime.utcnow()
    
    # Generate feedback
    try:
        feedback = generate_quiz_feedback(
            questions=questions,
            score=score,
            document_summary=quiz.document.summary
        )
        quiz.feedback = feedback
    except Exception as e:
        flash(f'Failed to generate detailed feedback: {str(e)}', 'warning')
        quiz.feedback = f"You scored {score:.1f}% on this quiz."
    
    db.session.commit()
    
    return redirect(url_for('quiz.results', quiz_id=quiz_id))

@quiz_bp.route('/results/<int:quiz_id>', methods=['GET'])
@login_required
def results(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Ensure the current user owns this quiz
    if quiz.student_id != current_user.id:
        abort(403)
    
    # Ensure quiz is completed
    if quiz.completed_at is None:
        flash('Please complete the quiz first.', 'warning')
        return redirect(url_for('quiz.take', quiz_id=quiz_id, question_index=0))
    
    document = quiz.document
    chapter = document.chapter
    course = chapter.course
    questions = quiz.questions.all()
    
    return render_template('quiz/results.html',
                          title='Quiz Results',
                          quiz=quiz,
                          document=document,
                          chapter=chapter,
                          course=course,
                          questions=questions)

@quiz_bp.route('/history/<int:document_id>', methods=['GET'])
@login_required
def history(document_id):
    document = Document.query.get_or_404(document_id)
    chapter = document.chapter
    course = chapter.course
    
    # Check if user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id).first():
        flash('You need to enroll in this course first.', 'warning')
        return redirect(url_for('courses.enroll', course_id=course.id))
    
    # Get quizzes for this document by the current user
    quizzes = Quiz.query.filter_by(
        document_id=document_id,
        student_id=current_user.id
    ).order_by(Quiz.created_at.desc()).all()
    
    return render_template('quiz/history.html',
                          title='Quiz History',
                          document=document,
                          chapter=chapter,
                          course=course,
                          quizzes=quizzes)

@quiz_bp.app_template_filter('md_to_html')
def md_to_html(text):
    """
    Convert basic markdown to HTML:
    - **text** to <strong>text</strong>
    - Preserves <br> tags
    """
    if text is None:
        return ""

    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = text.replace('<br>', '\n')    
    text = text.replace('\n', '<br />')
    return Markup(text)