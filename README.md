# AI Tutor

This project provides a simple web and CLI tool for translating Chinese sentences into English using an LLM API.

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Set the `OPENAI_API_KEY` environment variable with your API key.

## Usage

### Web Interface

Run the web server:

```bash
python app.py
```

Open your browser and visit `http://localhost:5000` to access the translator.

### Command Line

Run the interactive translator:

```bash
python main.py
```

Then input Chinese sentences to receive English translations. Type `exit` to quit.
