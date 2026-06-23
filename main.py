from config_loader import load_config
from ai.chat import chat_with_ai,generate_greeting
from memory_manager import load_memory, save_memory
from emotion_manager import load_emotion, save_emotion, update_emotion
from profile_manager import load_profile, save_profile, update_profile
def main():
    config = load_config()
    conversation_history = load_memory()
    emotion = load_emotion()
    profile = load_profile()
    greeting = generate_greeting(
        config['api_key'],
        config['model'],
        emotion,
        profile
    )
    print("Anime Assistant Started")
    print(f"Anime {config['assistant_name']} starting...")
    print("输入 exit 退出聊天\n")
    print("Anime Assistant:")
    print(greeting)
    print()
    while True:
        user_message = input("You: ")
        profile = update_profile(profile, user_message)
        save_profile(profile)
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
            emotion,
            profile
        )
        conversation_history.append(
    {
        "role": "assistant",
        "content": reply
    }
)
        save_memory(conversation_history)
        print("\nMio:")
        print(reply)
        print()

if __name__ == '__main__':
    main()