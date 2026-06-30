#!/usr/bin/env python3
"""本地 CLI：模拟多轮对话（规则 NLU，无需 LLM API）。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anchor.dialogue_handler import handle_user_message
from anchor.state_machine import Session


def main() -> None:
    session = Session()
    print("锚点 Anchor · 对话调试（输入 quit 退出）\n")

    while True:
        try:
            message = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见")
            break

        if not message:
            continue
        if message.lower() in ("quit", "exit", "q"):
            break

        turn = handle_user_message(session, message, llm=None)
        session = turn.session
        print(f"\n[{session.current_state.value}] 锚点: {turn.reply}\n")
        print(json.dumps(turn.meta, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()
