from config_loader import load_config
from ai.chat import chat_with_ai
from memory_manager import load_memory, save_memory
from emotion_manager import load_emotion, save_emotion, update_emotion
def main():
    config = load_config()
    conversation_history = load_memory()
    print("Anime Assistant Started")
    print(f"Anime {config['assistant_name']} starting...")
    print("输入 exit 退出聊天\n")

    while True:
        emotion = load_emotion()
        user_message = input("You: ")
        if user_message.lower() == "exit":
            print("Exiting chat...")
            break
        emotion = update_emotion(emotion, user_message)
        save_emotion(emotion)
        conversation_history.append(
    {
        "role": "user",
        "content": user_message
    }
)
        save_memory(conversation_history)
        

        reply = chat_with_ai(
            conversation_history,
            config['api_key'],
            config['model'],
            emotion
        )
        conversation_history.append(
    {
        "role": "assistant",
        "content": reply
    }
)
        save_memory(conversation_history)
        print("\nAnime Assistant:")
        print(reply)
        print()

if __name__ == '__main__':
    main()