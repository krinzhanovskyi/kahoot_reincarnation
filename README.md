# Kahoot Reincarnation Parser

A simple desktop Python application for searching public Kahoot quizzes and viewing their questions and correct answers.

This project was created for a Software Development course to practice Python, working with APIs, and building graphical user interfaces.

## Features

- Search for public Kahoot quizzes using a quiz title or question text.
- View questions and available correct answers.
- Copy an answer to the clipboard with one click.
- Press **F9** to bring the app to the front and search using text from the clipboard.
- Use a dark-themed interface built with CustomTkinter.
- Export quiz questions and answers to a JSON file.

## Technologies Used

- **Python 3** — programming language
- **CustomTkinter** — graphical user interface
- **Requests** — HTTP requests to retrieve quiz data
- **keyboard** — global F9 shortcut
- **pyperclip** — clipboard support
- **JSON** — exporting quiz data

## Project Structure

```text
kahoot_reincarnation/
├── api/
│   ├── __init__.py
│   ├── client.py         # HTTP requests and API errors
│   ├── config.py         # API configuration
│   ├── fetch.py          # Retrieve and parse quiz questions
│   └── search.py         # Search for public quizzes
├── core/
│   ├── __init__.py
│   └── controller.py     # Application logic
├── gui/
│   ├── __init__.py
│   └── app.py            # Desktop interface
├── tests/
│   └── test_api_errors.py
├── icon.ico
├── main.py               # Start the application
├── requirements.txt      # Dependencies
├── LICENCE               # MIT License
└── README.md
```

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/krinzhanovskyi/kahoot_reincarnation.git
cd kahoot_reincarnation
```

**2. Create a virtual environment**

```bash
python -m venv venv
```

Activate it using the command for your operating system:

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```cmd
venv\Scripts\activate.bat
```

macOS / Linux:

```bash
source venv/bin/activate
```

**3. Install dependencies**

```bash
python -m pip install -r requirements.txt
```

**4. Run the application**

```bash
python main.py
```

## How to Use

1. Enter a quiz title or question in the search field.
2. Click **Search** or press **Enter**.
3. Select a quiz from the search results.
4. View the questions and available correct answers.
5. Click **Copy Answer** to copy an answer to the clipboard.
6. Click **Export JSON** to save the loaded questions and answers.

### F9 Shortcut

Copy a quiz title or question to your clipboard and press **F9**. The application will come to the front and start a search using the copied text.

The F9 shortcut may require additional permissions on some operating systems.

## Running Tests

Run the unit tests from the project directory:

```bash
python -m unittest discover -s tests -v
```

## Known Limitations

- The application searches publicly available quizzes only.
- Results depend on the Kahoot API and the available quiz data.
- Some question formats, such as puzzles or typed answers, are not yet supported.
- Correct answers may be unavailable for some questions.
- The global F9 shortcut may not work on every operating system.

## Disclaimer

This is an educational project intended for studying Python and reviewing public quiz content. It is not intended for cheating or bypassing access restrictions.

This project is not affiliated with or endorsed by Kahoot.

## License

This project is released under the MIT License. See [LICENCE](LICENCE) for details.
