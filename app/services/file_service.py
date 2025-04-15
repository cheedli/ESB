import os
import uuid
from flask import current_app
from werkzeug.utils import secure_filename

def allowed_file(filename):
    """Check if the file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def save_file(file, chapter_id):
    """Save the file to the upload folder and return the path"""
    # Generate unique filename to prevent collisions
    original_filename = secure_filename(file.filename)
    file_extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
    
    # Create directory structure based on chapter ID
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], f'chapter_{chapter_id}')
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, unique_filename)
    relative_path = os.path.join(f'chapter_{chapter_id}', unique_filename)
    
    # Save the file
    file.save(file_path)
    
    return relative_path

def get_file_path(relative_path):
    """Get the absolute file path from the relative path stored in the database"""
    return os.path.join(current_app.config['UPLOAD_FOLDER'], relative_path)

def extract_text_from_file(file_path):
    """Extract text from various file types"""
    file_extension = file_path.rsplit('.', 1)[1].lower() if '.' in file_path else ''
    
    if file_extension == 'pdf':
        return extract_text_from_pdf(file_path)
    elif file_extension in ['doc', 'docx']:
        return extract_text_from_doc(file_path)
    elif file_extension in ['ppt', 'pptx']:
        return extract_text_from_ppt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_extension}")

def extract_text_from_pdf(file_path):
    """Extract text from PDF files"""
    try:
        # Using PyPDF2 (you'll need to add this to requirements.txt)
        from PyPDF2 import PdfReader
        
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        return text
    except Exception as e:
        current_app.logger.error(f"Error extracting text from PDF: {str(e)}")
        return f"Error extracting text: {str(e)}"

def extract_text_from_doc(file_path):
    """Extract text from DOC/DOCX files"""
    try:
        # Using python-docx for DOCX (you'll need to add this to requirements.txt)
        if file_path.endswith('.docx'):
            import docx
            
            doc = docx.Document(file_path)
            return "\n".join([paragraph.text for paragraph in doc.paragraphs])
        else:
            # For DOC files, you might need a more specialized library
            # This is a simplified placeholder
            return "Text extraction from DOC files not fully implemented yet."
    except Exception as e:
        current_app.logger.error(f"Error extracting text from DOC/DOCX: {str(e)}")
        return f"Error extracting text: {str(e)}"

def extract_text_from_ppt(file_path):
    """Extract text from PPT/PPTX files"""
    try:
        # Using python-pptx for PPTX (you'll need to add this to requirements.txt)
        if file_path.endswith('.pptx'):
            from pptx import Presentation
            
            text = []
            prs = Presentation(file_path)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text.append(shape.text)
            
            return "\n".join(text)
        else:
            # For PPT files, you might need a specialized library
            return "Text extraction from PPT files not fully implemented yet."
    except Exception as e:
        current_app.logger.error(f"Error extracting text from PPT/PPTX: {str(e)}")
        return f"Error extracting text: {str(e)}"