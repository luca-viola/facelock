"""Messages between the phone's page and this computer, through an ntfy server.

A page served over HTTPS can't reach a computer on the local network, so the phone posts to a
topic on an ntfy server (ntfy.sh unless set otherwise) and the computer listens there. Everything
is encrypted with a key that only the phone and this computer have, and bound to the topic, so the
server only sees when messages pass.
"""

import base64
import json
import logging
import os
import threading
import time

log = logging.getLogger("facelock")

DEFAULT_SERVER = "https://ntfy.sh"


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64url(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def seal(key, topic, value):
    """Encrypts a JSON value with AES-256-GCM, bound to the topic."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    iv = os.urandom(12)
    return _b64url(iv + AESGCM(key).encrypt(iv, json.dumps(value).encode(), topic.encode()))


def unseal(key, topic, text):
    """The JSON value, or None if it wasn't sealed with this key for this topic."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        data = _unb64url(text.strip())
        return json.loads(AESGCM(key).decrypt(data[:12], data[12:], topic.encode()))
    except (InvalidTag, ValueError, TypeError):
        return None


def _shut_down(response):
    """Ends a read blocked on the response's socket, from another thread.

    Closing the response doesn't wake a blocked read, but shutting the socket down does. The
    socket object http.client keeps is already marked closed, so this goes through its file
    descriptor.
    """
    import socket

    try:
        fd = response.raw._fp.fp.fileno()
        with socket.socket(fileno=os.dup(fd)) as sock:
            sock.shutdown(socket.SHUT_RDWR)
    except (AttributeError, OSError, ValueError) as error:
        log.info("Couldn't stop the relay connection at once: %s", error)


class Relay:
    def __init__(self, server=DEFAULT_SERVER):
        self.server = server.rstrip("/")

    def publish(self, topic, text, keep=True):
        """keep=False asks the server not to store the message, only pass it to listeners."""
        import requests

        headers = {} if keep else {"Cache": "no"}
        requests.post(f"{self.server}/{topic}", data=text.encode(), headers=headers, timeout=15).raise_for_status()

    def listen(self, topic, timeout_s, on_open=lambda: None):
        """Yields the text of each message that arrives within timeout_s.

        on_open runs once the server is listening, so a reply to something sent from it can't
        be missed.
        """
        import requests

        deadline = time.monotonic() + timeout_s
        # The server only sends a keepalive every 45 seconds or so, so a read can't be relied on
        # to return in time. Shutting the socket down at the deadline ends the read instead.
        # Uncompressed, since a compressed stream is held back until enough has piled up.
        with requests.get(f"{self.server}/{topic}/json", stream=True, timeout=(15, 120),
                          headers={"Accept-Encoding": "identity"}) as response:
            response.raise_for_status()
            timer = threading.Timer(timeout_s, _shut_down, (response,))
            timer.daemon = True
            timer.start()
            try:
                # A byte at a time, so each line is handed over as it arrives. The stream has no
                # chunked encoding, so a bigger read would wait for more, and None for the end.
                for line in response.iter_lines(chunk_size=1):
                    if time.monotonic() >= deadline:
                        return
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if message.get("event") == "open":
                        on_open()
                    elif message.get("event") == "message":
                        yield message.get("message", "")
            except (requests.exceptions.RequestException, AttributeError, ValueError) as error:
                # Closing the connection mid-read surfaces as one of these.
                if time.monotonic() < deadline - 1:
                    raise
                log.info("Stopped listening on the relay: %s", error)
            finally:
                timer.cancel()
