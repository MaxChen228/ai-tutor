# AI Tutor

This project provides a simple web and command line tool for translating Chinese sentences into English using the OpenAI API.

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Set the `OPENAI_API_KEY` environment variable with your OpenAI API key. For example:

```bash
export OPENAI_API_KEY="sk-..."
```

## Usage

### Web Interface

Run the web server:

```bash
python app.py
```

Open your browser and visit `http://localhost:5000` to access the translator. Enter Chinese text and the page will return the English translation.

### Command Line

Run the interactive translator:

```bash
python main.py
```

Then enter Chinese sentences to receive English translations. Type `exit` to quit the program.

### Python API

You can also import the `translate` function in your own scripts:

```python
from translator import translate

print(translate("你好"))
```
