import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app,send_from_directory
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, IntegerField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange
from werkzeug.utils import secure_filename
import requests
from app import db
from app.models import Course, Chapter, Document, Enrollment
from app.services.file_service import save_file, allowed_file
from app.services.ai_service import generate_summary
from app.services.file_service import get_file_path, extract_text_from_file
from app.models import Document, Note, Enrollment
chapters_bp = Blueprint('chapters', __name__, url_prefix='/chapters')

# Forms
class ChapterForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=3, max=100)])
    order = IntegerField('Order', validators=[DataRequired(), NumberRange(min=1)], default=1)
    submit = SubmitField('Save Chapter')

class DocumentForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=3, max=100)])
    file = FileField('File', validators=[
        DataRequired(),
        FileAllowed(['pdf', 'doc', 'docx', 'ppt', 'pptx'], 'Only PDF, DOC, DOCX, PPT, and PPTX files are allowed!')
    ])
    submit = SubmitField('Upload Document')

# Routes
@chapters_bp.route('/create/<int:course_id>', methods=['GET', 'POST'])
@login_required
def create(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Only the teacher who created the course can add chapters
    if course.teacher_id != current_user.id:
        abort(403)
    
    form = ChapterForm()
    
    # Set the default order to be the next in sequence
    next_order = course.chapters.count() + 1
    form.order.default = next_order
    
    if form.validate_on_submit():
        chapter = Chapter(
            title=form.title.data,
            order=form.order.data,
            course_id=course_id
        )
        db.session.add(chapter)
        db.session.commit()
        
        flash(f'Chapter "{chapter.title}" has been created!', 'success')
        return redirect(url_for('courses.view', course_id=course_id))
    
    # If it's a GET request, set the default order
    if request.method == 'GET':
        form.order.data = next_order
    
    return render_template('chapters/create.html', 
                          title='Add Chapter',
                          form=form, 
                          course=course)

@chapters_bp.route('/<int:chapter_id>')
@login_required
def view(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    course = chapter.course
    
    # Check if user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id).first():
        flash('You need to enroll in this course first.', 'warning')
        return redirect(url_for('courses.enroll', course_id=course.id))
    
    # Get documents
    documents = chapter.documents.all()
    
    return render_template('chapters/view.html', 
                          title=chapter.title,
                          chapter=chapter,
                          course=course,
                          documents=documents)

@chapters_bp.route('/<int:chapter_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    course = chapter.course
    
    # Only the teacher who created the course can edit chapters
    if course.teacher_id != current_user.id:
        abort(403)
    
    form = ChapterForm()
    if form.validate_on_submit():
        chapter.title = form.title.data
        chapter.order = form.order.data
        db.session.commit()
        
        flash(f'Chapter "{chapter.title}" has been updated!', 'success')
        return redirect(url_for('chapters.view', chapter_id=chapter.id))
    
    # Pre-populate form with existing data
    if request.method == 'GET':
        form.title.data = chapter.title
        form.order.data = chapter.order
    
    return render_template('chapters/create.html', 
                          title=f'Edit {chapter.title}',
                          form=form, 
                          course=course,
                          chapter=chapter)

@chapters_bp.route('/<int:chapter_id>/delete', methods=['POST'])
@login_required
def delete(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    course = chapter.course
    
    # Only the teacher who created the course can delete chapters
    if course.teacher_id != current_user.id:
        abort(403)
    
    course_id = course.id
    title = chapter.title
    db.session.delete(chapter)
    db.session.commit()
    
    flash(f'Chapter "{title}" has been deleted!', 'success')
    return redirect(url_for('courses.view', course_id=course_id))

@chapters_bp.route('/<int:chapter_id>/upload', methods=['GET', 'POST'])
@login_required
def upload_document(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    course = chapter.course
    
    # Only the teacher who created the course can upload documents
    if course.teacher_id != current_user.id:
        abort(403)
    
    form = DocumentForm()
    if form.validate_on_submit():
        if form.file.data and allowed_file(form.file.data.filename):
            # Save the file
            filename = secure_filename(form.file.data.filename)
            file_path = save_file(form.file.data, chapter_id)
            file_type = filename.rsplit('.', 1)[1].lower()
            
            # Create the document in the database
            document = Document(
                title=form.title.data,
                file_path=file_path,
                file_type=file_type,
                chapter_id=chapter_id
            )
            db.session.add(document)
            db.session.commit()
            
            # Generate summary asynchronously (in a real app, this should be a background task)
            try:
                summary = generate_summary(file_path, file_type)
                document.summary = summary
                db.session.commit()
                flash('Document summary has been generated.', 'success')
            except Exception as e:
                flash(f'Document uploaded but summary generation failed: {str(e)}', 'warning')
            
            flash(f'Document "{document.title}" has been uploaded!', 'success')
            return redirect(url_for('chapters.view', chapter_id=chapter_id))
    
    return render_template('chapters/upload.html',
                          title='Upload Document',
                          form=form,
                          chapter=chapter,
                          course=course)

@chapters_bp.route('/document/<int:document_id>')
@login_required
def view_document(document_id):
    document = Document.query.get_or_404(document_id)
    chapter = document.chapter
    course = chapter.course
    
    # Check if user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id).first():
        flash('You need to enroll in this course first.', 'warning')
        return redirect(url_for('courses.enroll', course_id=course.id))
    
    # Get notes for this document by the current user
    notes = Note.query.filter_by(
        document_id=document_id,
        user_id=current_user.id
    ).order_by(Note.created_at.desc()).all()
    
    return render_template('chapters/document.html',
                          title=document.title,
                          document=document,
                          chapter=chapter,
                          course=course,
                          notes=notes)  # Add notes to the template context
@chapters_bp.route('/document/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    document = Document.query.get_or_404(document_id)
    chapter = document.chapter
    course = chapter.course
    
    # Only the teacher who created the course can delete documents
    if course.teacher_id != current_user.id:
        abort(403)
    
    # Delete the file
    try:
        os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], document.file_path))
    except Exception as e:
        flash(f'Warning: File could not be deleted: {str(e)}', 'warning')
    
    # Delete from database
    chapter_id = chapter.id
    title = document.title
    db.session.delete(document)
    db.session.commit()
    
    flash(f'Document "{title}" has been deleted!', 'success')
    return redirect(url_for('chapters.view', chapter_id=chapter_id))

@chapters_bp.route('/uploads/<path:filename>')
def serve_uploads(filename):
    """
    Route to serve files from the uploads directory
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uploads_dir = os.path.join(base_dir, 'uploads')
    return send_from_directory(uploads_dir, filename)



@chapters_bp.route('/<int:chapter_id>/generate-summary', methods=['GET', 'POST'])
def generate_full_chapter_summary(chapter_id):
    """
    Generate a comprehensive summary of an entire chapter by combining individual document summaries.
    If a chapter summary already exists, return it instead of generating a new one.
    
    Args:
        chapter_id (int): ID of the chapter to summarize
        
    Returns:
        str: Generated chapter summary or existing summary
    """
    try:
        # Get the chapter
        chapter = Chapter.query.get_or_404(chapter_id)
        
        # Check if summary already exists
        if chapter.summary:
            current_app.logger.info(f"Using existing summary for chapter {chapter_id}")
            
            if request.method == 'GET':
                # Return a rendered template for GET requests
                return render_template('chapters/summary.html', 
                                      chapter=chapter, 
                                      course=Course.query.get(chapter.course_id))
            else:
                # For POST requests (API), return the summary text
                return chapter.summary
        
        # Get API key from config
        api_key = current_app.config.get('GROQ_API_KEY')
        if not api_key:
            raise ValueError("Groq API key is not configured")
        
        # Get the model from config
        model = current_app.config.get('GROQ_LLAMA_MODEL')
        
        # Get all documents in the chapter
        documents = Document.query.filter_by(chapter_id=chapter_id).all()
        
        if not documents:
            raise ValueError("No documents available in this chapter to summarize")
        
        # Get course information
        course = Course.query.get(chapter.course_id)
        course_title = course.title if course else "Unknown Course"
        
        # First, get summaries for each individual document
        document_summaries = []
        for document in documents:
            try:
                # Try to get existing summary from the document if it exists
                if document.summary:
                    doc_summary = document.summary
                    current_app.logger.info(f"Using existing summary for document {document.id}")
                else:
                    # Generate a new summary for this document
                    current_app.logger.info(f"Generating new summary for document {document.id}")
                    doc_summary = generate_summary(file_path=document.file_path, file_type=document.file_type)
                    
                    # Save the summary to the document if you have a summary field in Document model
                    if hasattr(document, 'summary'):
                        document.summary = doc_summary
                
                document_summaries.append({
                    "title": document.title,
                    "summary": doc_summary,
                    "type": document.file_type
                })
            except Exception as e:
                current_app.logger.error(f"Error generating summary for {document.title}: {str(e)}")
                # Continue with other documents even if one fails
                document_summaries.append({
                    "title": document.title,
                    "summary": f"[Error generating summary: {str(e)}]",
                    "type": document.file_type
                })
        
        # Commit document summaries to database if you updated them
        if any(hasattr(doc, 'summary') for doc in documents):
            db.session.commit()
        
        # Create document summaries list in text format
        summaries_text = ""
        for i, doc in enumerate(document_summaries, 1):
            summaries_text += f"\n\nDOCUMENT {i}: {doc['title']} (Type: {doc['type']})\n"
            summaries_text += f"SUMMARY:\n{doc['summary']}"
        
        # Identify if the documents contain TD or TP
        # (TD = Travaux Dirigés, TP = Travaux Pratiques - common in French education)
        td_tp_check = "In your analysis, if the content contains any practical exercises (TP) " \
                      "or directed work sessions (TD), please clearly identify them in the summary."
        
        # Prepare the prompt for the chapter-level summary
        prompt = f"""
        Please provide a comprehensive, structured summary of the following chapter titled "{chapter.title}" 
        from the course "{course_title}". I'll provide you with summaries of all documents in the chapter.
        
        Your task is to:
        
        1. Create a cohesive, well-structured chapter summary that integrates information from all document summaries
        2. Identify main concepts, theories, and key points across all documents
        3. Highlight connections between the different documents
        4. {td_tp_check}
        5. The summary can be as long as needed to accurately represent all important content
        6. Use clear headings and subheadings to organize the information
        7. Maintain the same language used in the original documents
        
        Here are summaries of all documents in the chapter:
        {summaries_text}
        
        CHAPTER SUMMARY:
        """
        
        # Call Groq API for the chapter-level summary
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an educational assistant that provides comprehensive, well-structured summaries of educational content. You excel at combining information from multiple sources into a cohesive summary."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
            "max_tokens": 12000
        }
        
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        data = response.json()
        chapter_summary = data['choices'][0]['message']['content'].strip()
        
        # Save the chapter summary to the database
        chapter.summary = chapter_summary
        db.session.commit()
        current_app.logger.info(f"Generated and saved summary for chapter {chapter_id}")
        
        if request.method == 'GET':
            # Return a rendered template for GET requests
            return render_template('chapters/summary.html', 
                                  chapter=chapter, 
                                  course=course)
        else:
            # For POST requests (API), return the summary text
            return chapter_summary
            
    except Exception as e:
        current_app.logger.error(f"Error in chapter summary generation: {str(e)}")
        if request.method == 'GET':
            flash(f"Error generating summary: {str(e)}", "danger")
            return redirect(url_for('courses.view', course_id=chapter.course_id))
        else:
            return f"Error generating chapter summary: {str(e)}"
        

@chapters_bp.route('/<int:chapter_id>/summary', methods=['GET'])
def view_summary(chapter_id):
    """View the full summary of a chapter"""
    chapter = Chapter.query.get_or_404(chapter_id)
    course = Course.query.get(chapter.course_id)
    
    # Check if the user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id).first():
        flash('You need to enroll in this course first.', 'warning')
        return redirect(url_for('courses.enroll', course_id=course.id))
    
    # Generate summary if it doesn't exist
    if not chapter.summary:
        return redirect(url_for('chapters.generate_full_chapter_summary', chapter_id=chapter.id))
    
    return render_template('chapters/summary.html', chapter=chapter, course=course)

@chapters_bp.route('/<int:chapter_id>/generate-summary', methods=['POST'])
@login_required
def generate_chapter_summary(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    course = chapter.course
    
    # Only the teacher who created the course can generate summaries
    if course.teacher_id != current_user.id:
        abort(403)
    
    # Get all document summaries
    documents = chapter.documents.all()
    if not documents:
        flash('No documents found in this chapter to generate a summary.', 'warning')
        return redirect(url_for('chapters.view', chapter_id=chapter_id))
    
    # Combine summaries
    combined_text = " ".join([doc.summary for doc in documents if doc.summary])
    
    # If there are no summaries yet
    if not combined_text:
        flash('No document summaries available. Please ensure documents have been processed.', 'warning')
        return redirect(url_for('chapters.view', chapter_id=chapter_id))
    
    # Generate chapter summary
    try:
        chapter.summary = generate_summary(text_content=combined_text)
        db.session.commit()
        flash('Chapter summary has been generated successfully!', 'success')
    except Exception as e:
        flash(f'Failed to generate chapter summary: {str(e)}', 'danger')
    
    return redirect(url_for('chapters.view', chapter_id=chapter_id))