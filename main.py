from googletrans import Translator

def main():
    translator = Translator()
    print("AI 中翻英家教 - 請輸入中文句子 (輸入 'exit' 結束)")
    while True:
        text = input('中文: ')
        if text.strip().lower() == 'exit':
            break
        result = translator.translate(text, src='zh-cn', dest='en')
        print('英文:', result.text)

if __name__ == '__main__':
    main()
