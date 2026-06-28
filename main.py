"""Anime Assistant main module"""
from context_manager import ContextManager
from config_loader import load_config
from ai.chat import generate_greeting
from memory_manager import load_memory
from emotion_manager import load_emotion
from profile_manager import load_profile
from relationship_manager import load_relationship
from orchestrator import ConversationOrchestrator


def main():
    config = load_config()
    conversation_history = load_memory()
    emotion = load_emotion()
    profile = load_profile()
    relationship = load_relationship()
    context = ContextManager(config, emotion, profile, relationship)

    orchestrator = ConversationOrchestrator(
        config, context, conversation_history, emotion, profile, relationship
    )

    greeting = generate_greeting(context.get_context())
    print("Anime Assistant Started")
    print(f"Anime {config['assistant_name']} starting...")
    print("输入 exit 退出聊天\n")
    print("Anime Assistant:")
    print(greeting)
    print()

    try:
        while True:
            user_message = input("You: ")
            if user_message.strip().lower() in ["exit", "quit"]:
                print("退出聊天。")
                break

            prepared = orchestrator.prepare_turn(user_message)

            print("\nMio:")
            raw_reply = ""
            for chunk in orchestrator.stream_reply(prepared):
                print(chunk, end="", flush=True)
                raw_reply += chunk
            print()
            print()

            orchestrator.finalize_turn(prepared, raw_reply)
    finally:
        orchestrator.shutdown()


if __name__ == '__main__':
    main()