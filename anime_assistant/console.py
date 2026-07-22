"""Prompt-toolkit console entry point for Anime Assistant."""

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from anime_assistant.infrastructure.config import load_config
from anime_assistant.runtime.application import ApplicationRuntime


def main():
    config = load_config()
    runtime = ApplicationRuntime(config, enable_speech=False)
    runtime.start()
    greeting_message = runtime.create_greeting()
    greeting = greeting_message.text if greeting_message is not None else ""

    print("Anime Assistant Started")
    print(f"Anime {config['assistant_name']} starting...")
    print("输入 exit 退出聊天\n")
    print("Anime Assistant:")
    print(greeting)
    print()

    session = PromptSession()
    try:
        with patch_stdout():
            while True:
                user_message = session.prompt("You: ")
                if user_message.strip().lower() in ["exit", "quit"]:
                    print("退出聊天。")
                    break

                turn_id = runtime.begin_turn("user")
                prepared = runtime.orchestrator.prepare_turn(
                    user_message,
                    turn_id=turn_id,
                )

                print("\nMio:")
                raw_reply = ""
                for chunk in runtime.orchestrator.stream_reply(prepared):
                    print(chunk, end="", flush=True)
                    raw_reply += chunk
                print("\n")
                runtime.orchestrator.finalize_turn(prepared, raw_reply)
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    main()
