#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
COMMANDS_FILE = ROOT_DIR / "docs" / "BOTFATHER_COMMANDS.txt"

SCOPES = [
    ("Default", {"type": "default"}),
    ("AllPrivateChats", {"type": "all_private_chats"}),
    ("AllGroupChats", {"type": "all_group_chats"}),
    ("AllChatAdministrators", {"type": "all_chat_administrators"}),
]


def load_commands(path: Path) -> list[dict[str, str]]:
    commands = []
    seen = set()

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if " - " not in line:
            raise ValueError(f"Dòng {line_number} sai định dạng: {raw_line}")

        command, description = line.split(" - ", 1)
        command = command.strip().lstrip("/")
        description = description.strip()

        if not command:
            raise ValueError(f"Dòng {line_number} thiếu command.")
        if not description:
            raise ValueError(f"Dòng {line_number} thiếu mô tả.")
        if command in seen:
            raise ValueError(f"Command bị trùng: {command}")

        seen.add(command)
        commands.append({"command": command, "description": description})

    return commands


def set_my_commands(token: str, commands: list[dict[str, str]], scope: dict[str, str]) -> dict:
    url = f"https://api.telegram.org/bot{token}/setMyCommands"
    payload = json.dumps(
        {
            "commands": commands,
            "scope": scope,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def get_my_commands(token: str, scope: dict[str, str]) -> dict:
    url = f"https://api.telegram.org/bot{token}/getMyCommands"
    payload = json.dumps(
        {
            "scope": scope,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def command_count(result: dict) -> int:
    if not result.get("ok"):
        raise RuntimeError(result)
    commands = result.get("result", [])
    if not isinstance(commands, list):
        raise RuntimeError(f"Phản hồi getMyCommands không hợp lệ: {result}")
    return len(commands)


def main() -> int:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("ERROR: Thiếu biến môi trường BOT_TOKEN.", file=sys.stderr)
        return 1

    if not COMMANDS_FILE.exists():
        print(f"ERROR: Không tìm thấy file {COMMANDS_FILE}", file=sys.stderr)
        return 1

    try:
        commands = load_commands(COMMANDS_FILE)
    except Exception as exc:
        print(f"ERROR: Không đọc được command list: {exc}", file=sys.stderr)
        return 1

    expected_count = len(commands)
    print(f"Tổng số command đã đọc: {expected_count}")

    success = []
    errors = []

    for scope_name, scope in SCOPES:
        try:
            before = command_count(get_my_commands(token, scope))
            print("")
            print(f"Scope: {scope_name}")
            print(f"Current commands: {before}")

            set_result = set_my_commands(token, commands, scope)
            if not set_result.get("ok"):
                raise RuntimeError(set_result)

            after = command_count(get_my_commands(token, scope))
            print(f"Before: {before}")
            print(f"After: {after}")

            if after != expected_count:
                raise RuntimeError(f"After {after} != số command trong docs {expected_count}")

            success.append(scope_name)
            print(f"OK: {scope_name}")
        except Exception as exc:
            errors.append((scope_name, str(exc)))
            print(f"ERROR: {scope_name}: {exc}")

    print("")
    print("Scope sync thành công:", ", ".join(success) if success else "Không có")
    if errors:
        print("Scope lỗi:")
        for scope_name, error in errors:
            print(f"- {scope_name}: {error}")
        return 1

    print("Scope lỗi: Không có")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
