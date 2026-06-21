from config_loader import load_config
from ai.chat import chat_with_ai


def main():
    config = load_config()
    conversation_history = []
    print("Anime Assistant Started")
    print(f"Anime {config['assistant_name']} starting...")
    print("输入 exit 退出聊天\n")

    while True:

        user_message = input("You: ")
        conversation_history.append(
    {
        "role": "user",
        "content": user_message
    }
)
        if user_message.lower() == "exit":
            print("Goodbye!")
            break

        reply = chat_with_ai(
            conversation_history,
            config['api_key'],
            config['model']
        )
        conversation_history.append(
    {
        "role": "assistant",
        "content": reply
    }
)
        print("\nAnime Assistant:")
        print(reply)
        print()

if __name__ == '__main__':
    main()