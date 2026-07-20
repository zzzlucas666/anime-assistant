"""Anime Assistant main module"""
import copy
import threading

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from anime_assistant.conversation.context_manager import ContextManager
from anime_assistant.infrastructure.config import load_config
from anime_assistant.ai.chat import generate_greeting
from anime_assistant.memory.memory_manager import load_memory
from anime_assistant.emotion.manager import (
    load_emotion,
    plan_greeting_emotion,
    save_emotion,
    update_emotion,
)
from anime_assistant.character.profile_manager import load_profile
from anime_assistant.character.relationship_manager import load_relationship
from anime_assistant.conversation.orchestrator import ConversationOrchestrator
from anime_assistant.proactive.initiative_engine import InitiativeEngine
from anime_assistant.memory.semantic_memory import warmup_model_async
from anime_assistant.memory.event_manager import schedule_embedding_backfill

def main():
    config = load_config()
    warmup_model_async()
    schedule_embedding_backfill()
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
        check_interval_minutes=config["proactive_check_interval_minutes"],
        idle_threshold_minutes=config["proactive_idle_threshold_minutes"],
        proactive_min_interval_minutes=config["proactive_min_interval_minutes"],
        proactive_max_per_day=config["proactive_max_per_day"],
    )

    background_thread = threading.Thread(target=initiative_engine.run_loop, daemon=True)
    with state_lock:
        emotion_snapshot = copy.deepcopy(emotion)
        relationship_snapshot = copy.deepcopy(relationship)
        context_snapshot = copy.deepcopy(context.get_context())
    context_snapshot["turn_emotion"] = plan_greeting_emotion(
        "",
        emotion_snapshot,
        relationship_snapshot,
    )
    greeting = generate_greeting(context_snapshot)
    greeting_emotion = plan_greeting_emotion(
        greeting,
        emotion_snapshot,
        relationship_snapshot,
    )
    with state_lock:
        emotion = update_emotion(
            emotion,
            interaction=greeting_emotion,
            consume_energy=False,
        )
        save_emotion(emotion)
        context.update(emotion, profile, relationship)

    print("Anime Assistant Started")
    print(f"Anime {config['assistant_name']} starting...")
    print("输入 exit 退出聊天\n")
    print("Anime Assistant:")
    print(greeting)
    print()
    background_thread.start()

    # PromptSession + patch_stdout 是 prompt_toolkit 提供的标准解法：
    # 当用户正在 "You: " 这一行输入时，后台线程（InitiativeEngine）如果
    # 调用了 print()，patch_stdout 会自动把这段输出"插"到输入行上方，
    # 而不会覆盖/弄乱用户已经打了一半的字。
    session = PromptSession()

    try:
        with patch_stdout():
            while True:
                user_message = session.prompt("You: ")
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
        # run_loop 在普通等待状态下会立即被 stop() 唤醒。如果正在等待
        # 主动消息的网络请求，最多等待两秒，之后由 daemon 线程收尾。
        background_thread.join(timeout=2)
        orchestrator.shutdown()


if __name__ == '__main__':
    main()
