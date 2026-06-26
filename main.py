"""Anime Assistant main module"""
from relationship_behavior import build_relationship_hint
from event_manager import extract_event, save_event
from behavior_engine import build_behavior_profile
from context_manager import ContextManager
from profile_extractor import extract_profile_info
from router import handle_intent
from intent_manager import detect_intent
from config_loader import load_config
from ai.chat import chat_with_ai, generate_greeting
from memory_manager import load_memory, save_memory
from emotion_manager import load_emotion, save_emotion, update_emotion
from profile_manager import load_profile, save_profile, update_profile
import re
import json
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

        reply = chat_with_ai(
            conversation_history,
            context.get_context()
        )
        if not reply:
            reply = ""
        reply = clean_reply(reply)
        event = extract_event(clean_message, reply)
        save_event(event)
        update_relationship(relationship, event)
        save_relationship(relationship)
        conversation_history.append({"role": "assistant", "content": reply})
        save_memory(conversation_history)
        context.update(emotion, profile, relationship)
        print("\nMio:")
        print(reply)
        print()
        save_relationship(relationship)
if __name__ == '__main__':
    main()