"""Voice loop: wait for "Hey Janet" -> listen -> transcribe -> LLM -> speak, with a local HUD."""

import queue
import re
import socket
import sys
import threading
import time
import webbrowser

from janet import config
from janet.agents.base import Message
from janet.agents.factory import get_provider
from janet.agents.persona import SYSTEM_PROMPT, extract_emotion
from janet.agents.tool_loop import run_turn
from janet.agents.tools import TOOLS
from janet.stt.recorder import record_utterance
from janet.stt.transcriber import Transcriber
from janet.stt.wakeword import BrowserPushToTalkDetector, PushToTalkDetector, WakeWordDetector
from janet.tts.sounds import (
    play_answer_ready,
    play_listening_done,
    play_listening_started,
    play_wake_detected,
)
from janet.tts.speaker import Speaker
from janet.ui.server import start_ui_server

_STOP_RE = re.compile(r"\bstop\b", re.IGNORECASE)


def _port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _wait_for_port(port: int, timeout_s: float = 5.0) -> bool:
    """Polls until something is accepting connections on 127.0.0.1:port, so
    we don't open the browser before uvicorn has actually bound it."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _port_in_use(port):
            return True
        time.sleep(0.1)
    return False


def _command_listener(
    command_queue: queue.Queue,
    talk_event: threading.Event,
    interrupt_event: threading.Event,
    current_state: dict,
) -> None:
    """Reacts to commands sent from the browser HUD (e.g. the TALK button).
    A "talk" command means "interrupt" while Janet is speaking, otherwise
    it's the push-to-talk trigger."""
    while True:
        command = command_queue.get()
        if command.get("type") == "talk":
            if current_state["value"] == "speaking":
                interrupt_event.set()
            else:
                talk_event.set()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    event_queue: queue.Queue = queue.Queue()
    command_queue: queue.Queue = queue.Queue()
    talk_event = threading.Event()
    interrupt_event = threading.Event()
    current_state = {"value": "idle"}

    def emit(event: dict) -> None:
        event_queue.put(event)

    def set_state(value: str) -> None:
        current_state["value"] = value
        emit({"type": "state", "value": value})

    ui_ready = False
    if config.UI_ENABLED:
        if _port_in_use(config.UI_PORT):
            print(
                f"[warning] Port {config.UI_PORT} is already in use — is another `janet` "
                "instance still running? Close it (or set UI_PORT to a free port in .env) "
                "to use the HUD this run. Continuing voice-only."
            )
        else:
            threading.Thread(
                target=start_ui_server, args=(event_queue, command_queue, config.UI_PORT), daemon=True
            ).start()
            if _wait_for_port(config.UI_PORT):
                ui_ready = True
                webbrowser.open(f"http://127.0.0.1:{config.UI_PORT}")
                threading.Thread(
                    target=_command_listener,
                    args=(command_queue, talk_event, interrupt_event, current_state),
                    daemon=True,
                ).start()
            else:
                print(f"[warning] HUD server didn't come up on port {config.UI_PORT} in time.")

    print("Loading models...")
    transcriber = Transcriber()
    speaker = Speaker()
    llm = get_provider()

    def say(text: str, language: str | None = None, emotion: str | None = None) -> None:
        interrupt_event.clear()
        set_state("speaking")
        if emotion:
            emit({"type": "emotion", "value": emotion})
        speaker.speak(
            text,
            on_start=lambda duration, envelope: emit(
                {"type": "speech", "text": text, "duration": duration, "envelope": envelope}
            ),
            interrupt=interrupt_event,
            language=language,
        )

    if config.WAKE_WORD_MODEL:
        wake_word = WakeWordDetector()
        prompt = "Say 'Hey Janet' to wake her up. Press Ctrl+C to exit anytime."
        greeting = "Hey, I'm Janet, say Hey Janet whenever you need me."
    elif ui_ready:
        wake_word = BrowserPushToTalkDetector(talk_event)
        prompt = "Press TALK in the browser HUD to start talking to Janet. Press Ctrl+C to exit anytime."
        greeting = "Hey, I'm Janet, press talk whenever you need me."
    else:
        print("[info] WAKE_WORD_MODEL not set — falling back to push-to-talk.")
        wake_word = PushToTalkDetector()
        prompt = "Press Enter once to start talking to Janet. Press Ctrl+C to exit anytime."
        greeting = "Hey, I'm Janet, press Enter to get started."
    history: list[Message] = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(prompt)
    set_state("idle")
    say(greeting)
    set_state("idle")
    play_listening_started()
    try:
        wake_word.wait_for_wake_word()
        print("Listening...")
        play_wake_detected()

        while True:
            set_state("listening")
            audio = record_utterance(on_block=lambda level: emit({"type": "amplitude", "level": level}))
            play_listening_done()
            text, language = transcriber.transcribe(audio)
            if not text:
                play_listening_started()
                continue
            print(f"You said: {text}")
            emit({"type": "subtitle", "role": "user", "text": text})

            if _STOP_RE.search(text):
                play_answer_ready()
                say("Goodbye.")
                set_state("idle")
                break

            history.append({"role": "user", "content": text})
            set_state("thinking")
            try:
                reply = run_turn(llm, history, tools=TOOLS)
            except RuntimeError as exc:
                print(f"[error] {exc}")
                play_answer_ready()
                say("Sorry, I ran into a problem answering that.", emotion="confused")
                play_listening_started()
                continue

            reply, emotion = extract_emotion(reply)
            print(f"Janet: {reply}")
            play_answer_ready()
            say(reply, language=language, emotion=emotion)
            play_listening_started()
    except KeyboardInterrupt:
        print("\nInterrupted, exiting.")
    finally:
        wake_word.close()


if __name__ == "__main__":
    main()
