# ESB Adaptive Learning Platform

An adaptive learning platform where teachers can create courses with chapters, upload documents, and students can interact with an AI assistant to learn from the content.

## Features

- User authentication with teacher and student roles
- Course and chapter management
- Document upload and management (PDF, DOC, DOCX, PPT, PPTX)
- AI-powered summaries for documents and chapters
- AI chatbot that can answer questions about specific documents
- Clean, responsive UI with a red color theme

## Tech Stack

- **Backend:** Flask, SQLAlchemy, Flask-Login
- **Frontend:** Bootstrap 5, JavaScript
- **Database:** SQLite (development), PostgreSQL (production-ready)
- **AI Integration:** Groq API with Llama model

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- A Groq API key

### Installation

1. Clone the repository
   ```
   git clone https://github.com/cheedli/ESB.git
   cd ESB
   ```

2. Create and activate a virtual environment
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies
   ```
   pip install -r requirements.txt
   ```

4. Set up environment variables
   - Copy the `.env.example` file to `.env`
   - Update the variables in the `.env` file, especially the `GROQ_API_KEY`

5. Initialize the database
   ```
   python -m flask db init
   python -m flask db migrate -m "Add choices to quiz_question"
   python -m flask db upgrade

   ```

6. Run the application
   ```
   flask run or py run.py
   ```

7. Access the application at http://127.0.0.1:5000

### Configuration

- The application can be configured through the `.env` file or environment variables.
- Different configurations (development, testing, production) are defined in `app/config.py`.

## Usage

1. Register as either a teacher or a student
2. Teachers can:
   - Create courses and chapters
   - Upload documents (PDF, DOC, DOCX, PPT, PPTX)
   - Generate summaries for chapters and documents
3. Students can:
   - Enroll in courses
   - Browse through course materials
   - View documents and their summaries
   - Use the AI assistant to ask questions about specific documents
   - Do Quizes

## Project Structure

```
ESB_platform/
│
├── app/                      # Application package
│   ├── __init__.py           # Flask app initialization
│   ├── config.py             # Configuration settings
│   ├── models.py             # Database models
│   ├── routes/               # Routes for different features
│   ├── services/             # Services (file handling, AI)
│   ├── static/               # Static assets
│   └── templates/            # HTML templates
│
├── migrations/               # Database migrations
├── uploads/                  # Uploaded files
├── .env                      # Environment variables
├── requirements.txt          # Project dependencies
└── run.py                    # Application entry point
```

## License

This project is licensed under the MIT License.
