from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, session
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import TextAreaField, SubmitField
from wtforms.validators import DataRequired
from app import db  # Import the main Flask app instance
from app.models import Document, ChatSession, ChatMessage, Enrollment, Chapter, Course
from app.services.ai_service import get_ai_response

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

# Forms
class ChatForm(FlaskForm):
    message = TextAreaField('Your Question', validators=[DataRequired()])
    submit = SubmitField('Send')

# Routes
@ai_bp.route('/chat/<int:document_id>', methods=['GET', 'POST'])
@login_required
def chat(document_id):
    document = Document.query.get_or_404(document_id)
    chapter = document.chapter
    course = chapter.course
    
    # Check if user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id).first():
        flash('You need to enroll in this course first.', 'warning')
        return redirect(url_for('courses.enroll', course_id=course.id))
    
    # Get or create chat session
    session = ChatSession.query.filter_by(
        user_id=current_user.id,
        document_id=document_id
    ).first()
    
    if not session:
        session = ChatSession(
            user_id=current_user.id,
            document_id=document_id
        )
        db.session.add(session)
        db.session.commit()
    
    # Get previous messages
    messages = session.messages.order_by(ChatMessage.timestamp).all()
    
    form = ChatForm()
    if form.validate_on_submit():
        # Save user message
        user_message = ChatMessage(
            session_id=session.id,
            content=form.message.data,
            is_user=True
        )
        db.session.add(user_message)
        db.session.commit()
        
        # Generate AI response
        try:
            # Pass document summary as context
            ai_content = get_ai_response(
                user_message=form.message.data,
                document_summary=document.summary,
                chat_history=messages
            )
            
            # Save AI response
            ai_message = ChatMessage(
                session_id=session.id,
                content=ai_content,
                is_user=False
            )
            db.session.add(ai_message)
            db.session.commit()
            
            # Refresh messages list
            messages = session.messages.order_by(ChatMessage.timestamp).all()
            
        except Exception as e:
            flash(f'Failed to get AI response: {str(e)}', 'danger')
        
        # Clear the form
        form.message.data = ''
    
    return render_template('ai/chat.html',
                          title=f'Chat about {document.title}',
                          document=document,
                          chapter=chapter,
                          course=course,
                          form=form,
                          messages=messages,
                          is_chapter_chat=False,
                          summary=document.summary,
                          chapter_id=None)  # Pass None for chapter_id in document chats

@ai_bp.route('/chapter-chat/<int:chapter_id>', methods=['GET', 'POST'])
@login_required
def chapter_chat(chapter_id):
    """Chat interface for asking questions about an entire chapter"""
    
    # Get the chapter
    chapter = Chapter.query.get_or_404(chapter_id)
    course = chapter.course
    
    # Check if user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id).first():
        flash('You need to enroll in this course first.', 'warning')
        return redirect(url_for('courses.enroll', course_id=course.id))
    
    # If the chapter doesn't have a summary yet, generate one
    if not chapter.summary:
        flash('Generating chapter summary...', 'info')
        return redirect(url_for('chapters.generate_full_chapter_summary', chapter_id=chapter.id))
    
    # Create a special session ID for chapter-level chats
    chapter_session_id = f"chapter_{chapter_id}"
    
    # Get existing chat history from session
    messages = []
    if 'chapter_chat_history' in session and chapter_session_id in session['chapter_chat_history']:
        # Convert session chat history to a format similar to the database messages
        chat_history = session['chapter_chat_history'][chapter_session_id]
        for i, msg in enumerate(chat_history):
            messages.append(ChatMessage(
                id=i,  # Temporary ID for template compatibility
                session_id=0,  # Placeholder
                content=msg['content'],
                is_user=msg['is_user'],
                timestamp=None  # We don't have timestamps for session messages
            ))
    
    form = ChatForm()
    if form.validate_on_submit():
        user_message = form.message.data
        
        if user_message:
            # Create a temporary user message object for the template
            user_msg = ChatMessage(
                id=len(messages) if messages else 0,
                session_id=0,
                content=user_message,
                is_user=True,
                timestamp=None
            )
            messages.append(user_msg)
            
            # Add to session history
            if 'chapter_chat_history' not in session:
                session['chapter_chat_history'] = {}
            if chapter_session_id not in session['chapter_chat_history']:
                session['chapter_chat_history'][chapter_session_id] = []
                
            session['chapter_chat_history'][chapter_session_id].append({
                'is_user': True,
                'content': user_message
            })
            
            try:
                # Get AI response using the chapter summary as context
                ai_response = get_ai_response(
                    user_message=user_message,
                    document_summary=chapter.summary,
                    chat_history=None  # We're handling chat history in the session
                )
                
                # Create a temporary AI message object for the template
                ai_msg = ChatMessage(
                    id=len(messages),
                    session_id=0,
                    content=ai_response,
                    is_user=False,
                    timestamp=None
                )
                messages.append(ai_msg)
                
                # Add to session history
                session['chapter_chat_history'][chapter_session_id].append({
                    'is_user': False,
                    'content': ai_response
                })
                session.modified = True
                
                # Clear the form
                form.message.data = ''
                
            except Exception as e:
                flash(f"Error getting AI response: {str(e)}", "danger")
    
    # Create a dummy document for template compatibility
    dummy_document = type('obj', (object,), {
        'id': 0,
        'title': f"Chapter: {chapter.title}",
    })
    
    return render_template('ai/chat.html',
                         title=f'Chat about Chapter: {chapter.title}',
                         document=dummy_document,  # Add a dummy document for template compatibility
                         chapter=chapter,
                         course=course,
                         form=form,
                         messages=messages,
                         is_chapter_chat=True,
                         summary=chapter.summary,
                         chapter_id=chapter_id)
@ai_bp.route('/api/chat/<int:document_id>', methods=['POST'])
@login_required
def api_chat(document_id):
    document = Document.query.get_or_404(document_id)
    chapter = document.chapter
    course = chapter.course
    
    # Check if user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id).first():
        return jsonify({'error': 'Access denied'}), 403
    
    # Get or create chat session
    session = ChatSession.query.filter_by(
        user_id=current_user.id,
        document_id=document_id
    ).first()
    
    if not session:
        session = ChatSession(
            user_id=current_user.id,
            document_id=document_id
        )
        db.session.add(session)
        db.session.commit()
    
    # Get user message from request
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400
    
    user_message_text = data['message']
    
    # Save user message
    user_message = ChatMessage(
        session_id=session.id,
        content=user_message_text,
        is_user=True
    )
    db.session.add(user_message)
    db.session.commit()
    
    # Get previous messages for context
    messages = session.messages.order_by(ChatMessage.timestamp).all()
    
    try:
        # Generate AI response
        ai_content = get_ai_response(
            user_message=user_message_text,
            document_summary=document.summary,
            chat_history=messages
        )
        
        # Save AI response
        ai_message = ChatMessage(
            session_id=session.id,
            content=ai_content,
            is_user=False
        )
        db.session.add(ai_message)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'response': ai_content,
            'message_id': ai_message.id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@ai_bp.route('/api/chapter-chat/<int:chapter_id>', methods=['POST'])
@login_required
def api_chapter_chat(chapter_id):
    """API endpoint for chapter-wide chat"""
    chapter = Chapter.query.get_or_404(chapter_id)
    course = chapter.course
    
    # Check if user has access to this course
    if not current_user.is_teacher and not Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id).first():
        return jsonify({'error': 'Access denied'}), 403
    
    # Check if chapter has a summary
    if not chapter.summary:
        return jsonify({'error': 'Chapter summary not available'}), 400
    
    # Get user message from request
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400
    
    user_message_text = data['message']
    
    # Create a special session ID for chapter-level chats
    chapter_session_id = f"chapter_{chapter_id}"
    
    # Add to session history
    if 'chapter_chat_history' not in session:
        session['chapter_chat_history'] = {}
    if chapter_session_id not in session['chapter_chat_history']:
        session['chapter_chat_history'][chapter_session_id] = []
        
    session['chapter_chat_history'][chapter_session_id].append({
        'is_user': True,
        'content': user_message_text
    })
    
    try:
        # Generate AI response
        ai_content = get_ai_response(
            user_message=user_message_text,
            document_summary=chapter.summary,
            chat_history=None  # We're handling history in the session
        )
        
        # Add to session history
        session['chapter_chat_history'][chapter_session_id].append({
            'is_user': False,
            'content': ai_content
        })
        session.modified = True
        
        return jsonify({
            'success': True,
            'response': ai_content,
            'message_id': len(session['chapter_chat_history'][chapter_session_id])
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@ai_bp.route('/clear/<int:document_id>', methods=['POST'])
@login_required
def clear_chat(document_id):
    session = ChatSession.query.filter_by(
        user_id=current_user.id,
        document_id=document_id
    ).first()
    
    if session:
        # Delete all messages
        ChatMessage.query.filter_by(session_id=session.id).delete()
        db.session.commit()
        flash('Chat history has been cleared.', 'success')
    
    return redirect(url_for('ai.chat', document_id=document_id))

@ai_bp.route('/chapter-chat/<int:chapter_id>/clear', methods=['POST'])
@login_required
def clear_chapter_chat(chapter_id):
    """Clear chat history for a chapter"""
    chapter_session_id = f"chapter_{chapter_id}"
    if 'chapter_chat_history' in session and chapter_session_id in session['chapter_chat_history']:
        session['chapter_chat_history'].pop(chapter_session_id)
        session.modified = True
        flash('Chat history has been cleared.', 'success')
    
    return redirect(url_for('ai.chapter_chat', chapter_id=chapter_id))