#!/usr/bin/env python3
"""Rewrite `git -C /path subcmd` → `cd /path && git subcmd` before permission check."""

import json
import re
import sys

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")

m = re.match(r"git -C (\S+) (.*)", cmd, re.DOTALL)
if m:
    # TODO see if i need a to filter out only on cwd
    new_cmd = f"git {m.group(2)}"
    print(
        json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {"command": new_cmd},
            }
        })
    )
