"""Anime Assistant main module"""
import threading

from context_manager import ContextManager
from config_loader import load_config
from ai.chat import generate_greeting
from memory_manager import load_memory
from emotion_manager import load_emotion
from profile_manager import load_profile
from relationship_manager import load_relationship
from orchestrator import ConversationOrchestrator
from initiative_engine import InitiativeEngine

# 主动聊天的两个可调参数：
# CHECK_INTERVAL_MINUTES：后台多久检查一次
# IDLE_THRESHOLD_MINUTES：距上次互动超过多久才算"很久没聊"
CHECK_INTERVAL_MINUTES = 5
IDLE_THRESHOLD_MINUTES = 30


def main():
    config = load_config()
    conversation_history = load_memory()
    emotion = load_emotion()
    profile = load_profile()
    relationship = load_relationship()
    context = ContextManager(config, emotion, profile, relationship)

    # orchestrator（主循环）和 initiative_engine（后台线程）共用同一把锁，
    # 保证两边不会同时读写状态文件。
    state_lock = threading.Lock()

    orchestrator = ConversationOrchestrator(
        config, context, conversation_history, emotion, profile, relationship,
        lock=state_lock
    )

    initiative_engine = InitiativeEngine(
        config, context, conversation_history, emotion, profile, relationship,
        lock=state_lock,
        check_interval_minutes=CHECK_INTERVAL_MINUTES,
        idle_threshold_minutes=IDLE_THRESHOLD_MINUTES
    )

    background_thread = threading.Thread(target=initiative_engine.run_loop, daemon=True)
    background_thread.start()

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
        initiative_engine.stop()
        orchestrator.shutdown()


if __name__ == '__main__':
    main()