import os
import json
import requests
from flask import current_app
from app.services.file_service import get_file_path, extract_text_from_file
from app.models import Chapter, Document, Course

def generate_summary(file_path=None, file_type=None, text_content=None):
    """
    Generate a summary of a document or text content using Groq API
    
    Args:
        file_path (str, optional): Path to the file to summarize
        file_type (str, optional): Type of the file
        text_content (str, optional): Text content to summarize directly
        
    Returns:
        str: Generated summary
    """
    # Get API key from config
    api_key = current_app.config.get('GROQ_API_KEY')
    if not api_key:
        raise ValueError("Groq API key is not configured")
    
    # Get the model from config
    model = current_app.config.get('GROQ_LLAMA_MODEL')
    
    # Extract text from file if file_path is provided
    if file_path and not text_content:
        full_path = get_file_path(file_path)
        text_content = extract_text_from_file(full_path)
    
    if not text_content:
        raise ValueError("No content available to summarize")
    
    # Prepare the prompt
    prompt = f"""
    Please provide a concise summary of the following content. Focus on the key concepts, 
    main ideas, and important details that would be useful for educational purposes.
    the summary should be in the same language as the content
    CONTENT:
    {text_content[:10000]}  # Limit to first 10000 chars to avoid token limits
    
    SUMMARY:
    """
    
    # Call Groq API
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
                "content": "You are an educational assistant that provides clear, concise summaries of educational content."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 10000
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        data = response.json()
        summary = data['choices'][0]['message']['content'].strip()
        
        return summary
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error calling Groq API: {str(e)}")
        raise ValueError(f"Error generating summary: {str(e)}")

def get_ai_response(user_message, document_summary, chat_history=None):
    """
    Get AI response for a chat message using Groq API
    
    Args:
        user_message (str): User's message/question
        document_summary (str): Summary of the document for context
        chat_history (list, optional): List of previous chat messages
        
    Returns:
        str: AI response
    """
    # Get API key from config
    api_key = current_app.config.get('GROQ_API_KEY')
    if not api_key:
        raise ValueError("Groq API key is not configured")
    
    # Get the model from config
    model = current_app.config.get('GROQ_LLAMA_MODEL')
    
    # Prepare chat history
    messages = [
        {
        "role": "system",
        "content": f"""YYou are an adaptive educational assistant helping a student learn from a specific document. 
        Use the provided summary to answer their questions accurately. 
        Only respond to questions directly related to the document; 
        if a question is off-topic, gently redirect the student to focus on the document. 
        Answer clearly, concisely, and in the same language as the question. Do not mention the summary or your reasoning process. 
        Avoid any special formatting such as asterisks or markdown.
        Answer in the same language that you aere asked with
        Document Summary:
        {document_summary}
        """


        }
    ]
    
    # Add chat history if provided
    if chat_history:
        for msg in chat_history:
            role = "user" if msg.is_user else "assistant"
            messages.append({"role": role, "content": msg.content})
    
    # Add the current user message
    messages.append({"role": "user", "content": user_message})
    
    # Call Groq API
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        data = response.json()
        ai_response = data['choices'][0]['message']['content'].strip()
        
        return ai_response
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error calling Groq API: {str(e)}")
        raise ValueError(f"Error generating response: {str(e)}")

def generate_quiz_questions(document_summary, num_questions):
    """
    Generate multiple choice quiz questions based on document content
    
    Args:
        document_summary (str): Summary of the document
        difficulty (str): 'easy', 'medium', or 'hard'
        num_questions (int): Number of questions to generate
        
    Returns:
        list: List of dictionaries containing questions, choices, and correct answers
    """
    # Get API key from config
    api_key = current_app.config.get('GROQ_API_KEY')
    if not api_key:
        raise ValueError("Groq API key is not configured")
    
    # Get the model from config
    model = current_app.config.get('GROQ_LLAMA_MODEL')   
    prompt = f"""
    Based on the following document summary, generate {num_questions}  level multiple-choice quiz questions.
    
    For each question:
    1. The question should be clear and specific
    3. Provide exactly THREE answer choices labeled A, B, and C
    4. Only ONE of the choices should be correct
    5. Clearly indicate which choice is correct (A, B, or C)
    6. Include a brief explanation of why the correct answer is right
    
    Document Summary:
    {document_summary}
    
    Please format your response as a JSON array of objects, with the following structure:
    [
        {{
            "question": "What is the main topic of this document?",
            "choice_a": "Machine learning algorithms",
            "choice_b": "Data structures",
            "choice_c": "Network protocols",
            "correct_choice": "A",
            "explanation": "The document primarily focuses on explaining different machine learning algorithms and their applications."
        }},
        ...
    ]
    """
    
    # Call Groq API
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
                "content": "You are an educational quiz generator that creates multiple-choice questions based on document content."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.5,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        data = response.json()
        content = data['choices'][0]['message']['content']
        
        # Parse the JSON response
        questions_data = json.loads(content)
        
        # If the response is wrapped in an extra object, extract the questions array
        if isinstance(questions_data, dict) and 'questions' in questions_data:
            questions_data = questions_data['questions']
        
        return questions_data
    except Exception as e:
        current_app.logger.error(f"Error generating quiz questions: {str(e)}")
        raise ValueError(f"Error generating quiz questions: {str(e)}")

def generate_quiz_feedback(questions, score, document_summary):
    """
    Generate personalized feedback based on quiz performance
    
    Args:
        questions (list): List of QuizQuestion objects
        score (float): Quiz score percentage
        document_summary (str): Summary of the document
        
    Returns:
        str: Personalized feedback
    """
    # Get API key from config
    api_key = current_app.config.get('GROQ_API_KEY')
    if not api_key:
        raise ValueError("Groq API key is not configured")
    
    # Get the model from config
    model = current_app.config.get('GROQ_LLAMA_MODEL')
    
    # Prepare information about incorrect answers
    incorrect_questions = [q for q in questions if not q.is_correct]
    correct_questions = [q for q in questions if q.is_correct]
    
    incorrect_info = []
    for q in incorrect_questions:
        incorrect_info.append({
            "question": q.question_text,
            "student_choice": q.student_choice,
            "correct_choice": q.correct_choice,
            "choice_a": q.choice_a,
            "choice_b": q.choice_b,
            "choice_c": q.choice_c,
            "explanation": q.explanation
        })
    
    # Prepare the prompt
    prompt = f"""
    Generate personalized feedback for a student who completed a multiple-choice quiz on the following topic:
    
    Document Summary:
    {document_summary}
    
    Quiz Performance:
    - Score: {score:.1f}%
    - {len(correct_questions)} correct answers out of {len(questions)} questions
    
    Incorrect Answers:
    {json.dumps(incorrect_info, indent=2)}
    
    Please provide:
    1. An overall assessment of their performance
    2. Specific feedback on areas they should focus on based on their incorrect answers
    3. Recommendations for improvement
    4. Encouragement and positive reinforcement
    
    The feedback should be constructive, specific to their mistakes, and reference the content they were tested on.
    """
    
    # Call Groq API
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
                "content": "You are an educational assistant that provides personalized and constructive feedback on quiz performance."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        data = response.json()
        feedback = data['choices'][0]['message']['content'].strip()
        
        return feedback
    except Exception as e:
        current_app.logger.error(f"Error generating quiz feedback: {str(e)}")
        raise ValueError(f"Error generating quiz feedback: {str(e)}")    

def evaluate_quiz_answer(student_answer, correct_answer, question_text):
    """
    Evaluate if a student's answer is correct using AI
    
    Args:
        student_answer (str): The student's response
        correct_answer (str): The correct answer
        question_text (str): The question being asked
        
    Returns:
        bool: Whether the answer is correct
        str: Feedback on the answer (optional)
    """
    # Get API key from config
    api_key = current_app.config.get('GROQ_API_KEY')
    if not api_key:
        raise ValueError("Groq API key is not configured")
    
    # Get the model from config
    model = current_app.config.get('GROQ_LLAMA_MODEL')
    
    # Prepare the prompt
    prompt = f"""
    Please evaluate the student's answer to the following question:
    
    Question: {question_text}
    
    Correct answer: {correct_answer}
    
    Student's answer: {student_answer}
    
    Is the student's answer conceptually correct? Consider the meaning rather than exact wording.
    The answer is correct if it demonstrates understanding of the core concept, even if it doesn't
    match the expected answer word-for-word. Spelling mistakes, grammatical errors, and
    slightly different phrasing should be tolerated if the main point is correct.
    
    Respond in JSON format with two fields:
    1. "is_correct": true or false
    2. "feedback": brief specific feedback on the answer (what was good or what was missing)
    
    Example response:
    {{
        "is_correct": true,
        "feedback": "Your answer correctly identifies the main concept but could be more specific about X."
    }}
    """
    
    # Call Groq API
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
                "content": "You are an educational assistant that evaluates student answers fairly and constructively."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 500,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        data = response.json()
        content = data['choices'][0]['message']['content']
        
        # Parse the JSON response
        result = json.loads(content)
        
        return result.get('is_correct', False), result.get('feedback', '')
    except Exception as e:
        current_app.logger.error(f"Error evaluating answer: {str(e)}")
        # Fall back to simple string matching if the API call fails
        is_correct = student_answer.lower().strip() == correct_answer.lower().strip()
        return is_correct, "Unable to generate detailed feedback."