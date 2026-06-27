"""Anime Assistant main module"""
from event_manager import extract_event, save_event
from context_manager import ContextManager
from profile_extractor import extract_profile_info
from router import handle_intent  # 精确查表类回复：get_profile / emotion_query
from intent_manager import detect_intent
from config_loader import load_config
from ai.chat import chat_with_ai_stream, generate_greeting
from memory_manager import load_memory, save_memory
from emotion_manager import load_emotion, save_emotion, update_emotion
from profile_manager import load_profile, save_profile
import re
from relationship_manager import load_relationship, save_relationship, update_relationship
def clean_reply(reply):
    reply = re.sub(r'（.*?）', '', reply)
    return reply.strip()
def main():
    config = load_config()
    conversation_history = load_memory()
    emotion = load_emotion()
    profile = load_profile()
    relationship = load_relationship()
    context = ContextManager(config, emotion, profile, relationship)
    greeting = generate_greeting(context.get_context())
    print("Anime Assistant Started")
    print(f"Anime {config['assistant_name']} starting...")
    print("输入 exit 退出聊天\n")
    print("Anime Assistant:")
    print(greeting)
    print()
    while True:
        user_message = input("You: ")
        if user_message.strip().lower() in ["exit", "quit"]:
            print("退出聊天。")
            break

        clean_message = (
            user_message
            .replace("？", "")
            .replace("?", "")
            .strip()
        )
        intent_result = detect_intent(
            config['api_key'],
            config['model'],
            clean_message,
            emotion,
            profile
        )
        profile_info = extract_profile_info(
        config['api_key'],
        config['model'],
        clean_message
        )
        intent = intent_result.get("intent", "")
        confidence = intent_result.get("confidence", 0)
        action = profile_info.get("action")
        value = profile_info.get("value")

        if intent == "set_profile" and confidence > 0.5:
            if action == "add_like":
                if value and value not in profile["likes"]:
                    profile["likes"].append(value)

            elif action == "add_dislike":
                if value and value not in profile["dislikes"]:
                    profile["dislikes"].append(value)

            elif action == "set_name":
                if value:
                    profile["name"] = value

            elif action == "set_nickname":
                if value:
                    profile["nickname"] = value

            save_profile(profile)

        # record user message
        conversation_history.append({"role": "user", "content": clean_message})
        save_memory(conversation_history)

        # 精确查表类回复（询问喜好/昵称/情绪状态等），优先查表，查不到再退回 AI
        router_reply = None
        if intent in ("get_profile", "emotion_query") and confidence > 0.5:
            router_reply = handle_intent(intent, clean_message, profile, emotion)

        if router_reply:
            reply = router_reply
            print("\nMio:")
            print(reply)
            print()
        else:
            print("\nMio:")
            raw_reply = ""
            for chunk in chat_with_ai_stream(
                conversation_history,
                context.get_context()
            ):
                print(chunk, end="", flush=True)
                raw_reply += chunk
            print()
            print()
            reply = clean_reply(raw_reply) if raw_reply else ""

        # 更新情绪状态
        emotion = update_emotion(emotion, clean_message)
        save_emotion(emotion)

        # 提取事件并更新关系状态
        event = extract_event(
            config['api_key'],
            config['model'],
            clean_message,
            reply
        )
        save_event(event)
        relationship = update_relationship(relationship, event)
        save_relationship(relationship)

        conversation_history.append({"role": "assistant", "content": reply})
        save_memory(conversation_history)

        context.update(emotion, profile, relationship)
if __name__ == '__main__':
    main()