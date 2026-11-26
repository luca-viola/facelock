"""Pairing a phone, and asking it to approve an unlock with its passkey.

The phone runs a web page (web/ in this repository, published on GitHub Pages). Pairing:
this computer shows a one-time code; the page derives a topic and a key from it, creates a
passkey, subscribes to Web Push, and sends all that back on the topic, sealed with the key.

Unlocking: this computer pushes a challenge to the phone. You approve on the phone, which signs
the challenge with the passkey, and the page posts the signature back through the relay. Only
the signature over this computer's own single-use challenge is accepted.
"""

import hashlib
import json
import logging
import os
import re
import secrets
import socket
import time

from errors import GuardError
from files import private_dir, write_private
from paths import APP_DIR, data_home, runtime_home
from relay import DEFAULT_SERVER, Relay, unseal
from webpush import b64url, unb64url

log = logging.getLogger("facelock")

PAGE_URL = "https://luca-viola.github.io/facelock/"
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0, 1, I or O, which look alike
CODE_LENGTH = 12  # 60 bits
PAIR_TIMEOUT_S = 600
APPROVE_TIMEOUT_S = 60


def phone_path():
    return os.path.join(data_home(), APP_DIR, "phone.json")


def page_origin(page_url):
    """The page's origin. Passkeys need https, except on localhost, for testing."""
    match = re.match(r"^(https://[^/:]+(?::\d+)?|http://localhost(?::\d+)?)(?:/|$)", page_url)
    if not match:
        raise GuardError("phone", f"The phone page must be on https: {page_url}", retryable=False)
    return match.group(1)


def rp_id(page_url):
    """The passkey's relying party: the page's host name."""
    return re.sub(r"^https?://", "", page_origin(page_url)).split(":")[0]


def computer_name():
    return socket.gethostname().split(".")[0] or "this computer"


# --- Pairing --- #

def new_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def show_code(code):
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def derive_pairing(code):
    """The topic and key both sides work out from the code. web/app.js does the same."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    normalized = re.sub(r"[^A-Z0-9]", "", code.upper()).encode()

    def derive(info, length):
        return HKDF(algorithm=hashes.SHA256(), length=length, salt=b"facelock pairing",
                    info=info).derive(normalized)

    return "facelock-" + derive(b"topic", 16).hex(), derive(b"key", 32)


def check_pairing_reply(reply):
    """Raises ValueError unless the phone sent everything needed, in usable form."""
    from cryptography.hazmat.primitives.serialization import load_der_public_key

    from webpush import vapid_key_from_jwk

    for field in ("credential", "public_key", "subscription", "vapid", "topic", "key"):
        if not reply.get(field):
            raise ValueError(f"no {field}")
    load_der_public_key(unb64url(reply["public_key"]))
    vapid_key_from_jwk(**{k: reply["vapid"][k] for k in ("d", "x", "y")})
    if len(unb64url(reply["key"])) != 32 or not re.fullmatch(r"[-_A-Za-z0-9]{16,64}", reply["topic"]):
        raise ValueError("bad relay topic or key")
    subscription = reply["subscription"]
    if not subscription.get("endpoint", "").startswith("https://") or not subscription.get("keys"):
        raise ValueError("bad push subscription")


def pair(relay_server, page_url, emit, timeout_s=PAIR_TIMEOUT_S):
    """Shows a code, then waits for a phone to pair with it and saves what it sent."""
    import segno

    code = new_code()
    topic, key = derive_pairing(code)
    name = computer_name()
    url = f"{page_url}#pair={code}&name={name}"
    if relay_server.rstrip("/") != DEFAULT_SERVER:
        url += f"&relay={relay_server.rstrip('/')}"
    qr_path = os.path.join(private_dir(os.path.join(runtime_home(), APP_DIR)), "pair.png")
    segno.make(url, error="m").save(qr_path, kind="png", scale=8, border=2)
    emit("pair_code", code=show_code(code), url=url, qr=qr_path)

    relay = Relay(relay_server)
    try:
        for text in relay.listen(topic, timeout_s):
            reply = unseal(key, topic, text)
            if reply is None:
                continue
            try:
                check_pairing_reply(reply)
            except (ValueError, KeyError, TypeError) as error:
                log.warning("Ignoring an unusable pairing reply: %s", error)
                continue
            phone = {
                "page_url": page_url,
                "relay": relay_server.rstrip("/"),
                "credential": reply["credential"],
                "public_key": reply["public_key"],
                "subscription": reply["subscription"],
                "vapid": {k: reply["vapid"][k] for k in ("d", "x", "y")},
                "topic": reply["topic"],
                "key": reply["key"],
                "device": str(reply.get("device", ""))[:80],
                "paired_at": int(time.time()),
            }
            private_dir(os.path.dirname(phone_path()))
            write_private(phone_path(), json.dumps(phone, indent=2).encode())
            push(phone, {"v": 1, "type": "paired", "name": name})
            emit("paired", device=phone["device"])
            return
    finally:
        try:
            os.remove(qr_path)
        except OSError:
            pass
    raise GuardError("pair_timeout", "No phone answered. Start pairing again.", retryable=False)


def load_phone():
    try:
        with open(phone_path()) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise GuardError("phone", f"Can't read the phone pairing: {error}. Pair the phone again.",
                         retryable=False) from error


def push(phone, payload):
    import requests

    import webpush

    vapid = webpush.vapid_key_from_jwk(**phone["vapid"])
    try:
        webpush.send(phone["subscription"], payload, vapid, phone["page_url"])
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else None
        if status in (404, 410):
            raise GuardError("phone", "The phone no longer accepts notifications. Pair it again.",
                             retryable=False) from error
        raise GuardError("phone", f"The push service refused the notification ({status})",
                         retryable=True) from error
    except requests.RequestException as error:
        raise GuardError("phone", "Couldn't reach the push service. Check the connection.",
                         retryable=True) from error


# --- Approving an unlock --- #

def number_choices(rng=secrets.SystemRandom()):
    """The number to show, and it among two others in random order, for the phone."""
    numbers = rng.sample(range(10, 100), 3)
    shown = numbers[0]
    rng.shuffle(numbers)
    return shown, numbers


def challenge_for(nonce, pick):
    """What the passkey signs: the nonce bound to the number picked, so a wrong pick can't pass."""
    return hashlib.sha256(nonce + str(pick or "").encode()).digest()


def verify_assertion(phone, answer, challenge):
    """Whether answer is the paired passkey's signature over challenge, made on the page."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import load_der_public_key

    try:
        if answer.get("credential") != phone["credential"]:
            return False
        client_data_bytes = unb64url(answer["client_data"])
        auth_data = unb64url(answer["authenticator_data"])
        signature = unb64url(answer["signature"])
        client_data = json.loads(client_data_bytes)
    except (KeyError, ValueError, TypeError, AttributeError):
        return False

    origin = page_origin(phone["page_url"])
    if client_data.get("type") != "webauthn.get" or client_data.get("origin") != origin \
            or client_data.get("crossOrigin") or client_data.get("challenge") != b64url(challenge):
        return False
    if len(auth_data) < 37 or auth_data[:32] != hashlib.sha256(rp_id(phone["page_url"]).encode()).digest():
        return False
    flags = auth_data[32]
    if not flags & 0x01 or not flags & 0x04:  # user present, and verified with Face ID or similar
        return False
    try:
        public_key = load_der_public_key(unb64url(phone["public_key"]))
        public_key.verify(signature, auth_data + hashlib.sha256(client_data_bytes).digest(),
                          ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def approve(phone, number_match, emit, timeout_s=APPROVE_TIMEOUT_S):
    """Asks the phone to approve. Returns None if it did, or why not as a short sentence."""
    nonce = os.urandom(32)
    shown, numbers = number_choices() if number_match else (None, None)
    challenge = challenge_for(nonce, shown)
    payload = {"v": 1, "type": "unlock", "topic": phone["topic"], "nonce": b64url(nonce),
               "numbers": numbers, "name": computer_name(), "expires": int(time.time() + timeout_s)}
    key = unb64url(phone["key"])
    relay = Relay(phone.get("relay", DEFAULT_SERVER))

    def ask():
        push(phone, payload)
        emit("unlock_step", step="phone", number=shown)

    try:
        for text in relay.listen(phone["topic"], timeout_s, on_open=ask):
            answer = unseal(key, phone["topic"], text)
            if not answer or answer.get("nonce") != payload["nonce"]:
                continue  # not for this request, or not from the phone
            if answer.get("deny"):
                return "Declined on the phone"
            if number_match and answer.get("pick") != shown:
                return "That wasn't the number on the screen"
            if verify_assertion(phone, answer, challenge):
                return None
            return "The phone's answer didn't check out"
    except GuardError as error:
        return str(error)
    except Exception as error:  # the relay, mostly
        log.warning("Phone approval failed: %s", error)
        return "Couldn't reach the relay"
    return "The phone didn't answer"
