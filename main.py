import os
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

PROMPT_SYSTEM = "You translate Chinese to English."

def main():
    print("AI 中翻英家教 - 請輸入中文句子 (輸入 'exit' 結束)")
    while True:
        text = input('中文: ')
        if text.strip().lower() == 'exit':
            break
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": PROMPT_SYSTEM},
                {"role": "user", "content": text}
            ]
        )
        print('英文:', response.choices[0].message.content.strip())

if __name__ == '__main__':
    main()
