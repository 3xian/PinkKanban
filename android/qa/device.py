"""Small adb helper: all taps use the latest UI hierarchy's text/description bounds."""
import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["dump", "tap", "text", "back", "screenshot"])
parser.add_argument("value", nargs="?")
parser.add_argument("--serial", default="emulator-5554")
parser.add_argument("--adb", default="F:/AndroidSDK/platform-tools/adb.exe")
args = parser.parse_args()
adb = [args.adb, "-s", args.serial]


def run(*values):
    return subprocess.check_output([*adb, *values])


if args.action in ("dump", "tap"):
    run("shell", "uiautomator", "dump", "/sdcard/kanban-ui.xml")
    raw = run("shell", "cat", "/sdcard/kanban-ui.xml")
    nodes = list(ET.fromstring(raw).iter("node"))
    if args.action == "dump":
        for node in nodes:
            value = node.get("text") or node.get("content-desc")
            if value or node.get("class") == "android.widget.EditText":
                print(value, node.get("class"), node.get("bounds"))
    else:
        matches = [node for node in nodes if args.value in (node.get("text"), node.get("content-desc"))
                   and node.get("bounds") != "[0,0][0,0]"]
        if not matches:
            raise SystemExit(f"UI element not found: {args.value}")
        node = next((node for node in matches if node.get("clickable") == "true"), matches[0])
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
        run("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
elif args.action == "text":
    run("shell", "input", "text", args.value)
elif args.action == "back":
    run("shell", "input", "keyevent", "4")
elif args.action == "screenshot":
    Path(args.value).write_bytes(run("exec-out", "screencap", "-p"))
