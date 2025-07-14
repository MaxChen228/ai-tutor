"""Command line interface for the translator."""

from translator import translate, check_api_key

def main() -> None:
    """Run the interactive translator."""
    print("AI 中翻英家教 - 請輸入中文句子 (輸入 'exit' 結束)")
    try:
        check_api_key()
    except RuntimeError as exc:
        print(exc)
        return

    while True:
        text = input("中文: ")
        if text.strip().lower() == "exit":
            break
        try:
            print("英文:", translate(text))
        except Exception as exc:
            print("Error:", exc)

if __name__ == '__main__':
    main()
