"""JSON lines to the extension on stdout, and commands from it on stdin."""

import json
import os
import sys
import threading


def open_protocol_stream():
    """Claims the real stdout for JSON and points fd 1 at stderr.

    Libraries print progress to stdout, which would corrupt the protocol.
    """
    stream = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)

    def emit(event, **fields):
        stream.write(json.dumps({"event": event, **fields}) + "\n")

    return emit


def watch_stdin(on_line=None, on_close=lambda: os._exit(0)):
    """Calls on_close at stdin EOF, which is how a dead parent shows up."""
    def watch():
        for line in sys.stdin:
            if on_line:
                on_line(line.strip())
        on_close()

    threading.Thread(target=watch, daemon=True).start()
