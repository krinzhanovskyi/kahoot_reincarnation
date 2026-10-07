# Kahoot reincarnation Parcer 1.0

A desktop Python application designed to search and parse public Kahoot quizzes. It enables users to locate quizzes by title, instantly retrieve correct answers, copy them to the clipboard with a single click.

This app was created as a project for a personal portfolio and not allowed use for cheating.

## Key Features

- **Intelligent Search:** Query public quizzes via the open Kahoot API using the quiz title or question text.
- **Global Hotkey Integration (F9):** Operates as a background process. Pressing `F9` brings the application to the foreground, reads the system clipboard, and automatically initiates a search query.
- **Clipboard Management:** Copy correct answers to the system clipboard via a single UI interaction.
- **Modern Interface:** Card-based UI and dark mode built on the `customtkinter` framework.

## Technology Stack

- **Language:** Python 3.x
- **GUI:** `customtkinter`
- **Networking:** `requests`
- **System Integration:** `keyboard`, `pyperclip`

## Project Structure

```Text
kahoot_reincarnation/
├── api/                   # Kahoot API communication module
│   ├── __init__.py
│   ├── config.py          # Headers and endpoint URL configuration
│   ├── fetch.py           # JSON retrieval and parsing for specific quizzes
│   └── search.py          # Search queries via the Discover catalog
├── core/                  # Application business logic
│   ├── __init__.py
│   └── controller.py      # Orchestrator linking UI with API and managing threads
├── gui/                   # Graphical User Interface
│   ├── __init__.py
│   └── app.py             # CustomTkinter interface rendering
├── main.py                # Entry point and Dependency Injection initialization
└── requirements.txt       # Project dependencies

```

## Installation and Execution

1.  Clone or download the repository.
2.  Create and activate a virtual environment:
    Bash

    ```bash
    python -m venv venv

    # For Windows:
    venv\Scripts\activate

    # For macOS/Linux:
    source venv/bin/activate
    ```

3.  Install the required dependencies:
    Bash

    ```bash
    pip install -r requirements.txt
    ```

4.  Execute the application:
    Bash
    ```bash
    python main.py
    ```

## Usage Guide

1.  Enter the suspected quiz title or the text of the first question into the search bar.
2.  Click **Search** (or press `Enter`).
3.  Select the appropriate quiz from the search results based on its title.
4.  The application will load the list of questions. Click the green answer button to copy it to the clipboard.

> **Note:** By cloning or downloading this project, you agree that you do not use it as a cheat program, and I, as the creator, am not responsible for your actions.
