import os
import openai
from flask import Flask, request, render_template_string

# 從環境變數讀取 API 金鑰並建立客戶端
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
            # 使用新的 client.chat.completions.create 語法
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You translate Chinese to English."},
                    {"role": "user", "content": text}
                ]
            )
            translation = response.choices[0].message.content.strip()
    return render_template_string(HTML, translation=translation)

if __name__ == "__main__":
    app.run(debug=True)