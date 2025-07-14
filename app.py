"""Simple web interface for the translator."""

from flask import Flask, request, render_template_string

from translator import translate, check_api_key

HTML = """
<!doctype html>
<title>AI Translator</title>
<h1>AI 中翻英家教</h1>
<form method=post>
  <input name=text placeholder="輸入中文" autocomplete="off">
  <input type=submit value=Translate>
</form>
{% if translation %}
<p>英文: {{ translation }}</p>
{% endif %}
"""

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    translation = None
    if request.method == "POST":
        text = request.form.get("text", "")
        if text:
            try:
                check_api_key()
                translation = translate(text)
            except Exception as exc:
                translation = f"Error: {exc}"
    return render_template_string(HTML, translation=translation)

if __name__ == "__main__":
    app.run(debug=True)
