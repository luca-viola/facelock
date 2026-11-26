"""Sending a Web Push message to a browser, as RFC 8291 (encryption) and RFC 8292 (VAPID) say.

The browser's push service, Apple's or Google's, delivers it to the phone. Only the phone can
read it, and the VAPID signature shows it came from someone holding the key the phone chose.
"""

import base64
import json
import os
import struct
import time
from urllib.parse import urlsplit

RECORD_SIZE = 4096
VAPID_LIFETIME_S = 12 * 3600


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hkdf(salt, ikm, info, length):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _public_bytes(public_key):
    from cryptography.hazmat.primitives import serialization

    return public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def encrypt(plaintext, p256dh, auth, sender_key=None, salt=None):
    """The message body for the aes128gcm content encoding, in one record."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    receiver_bytes = unb64url(p256dh)
    receiver = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), receiver_bytes)
    sender_key = sender_key or ec.generate_private_key(ec.SECP256R1())
    sender_bytes = _public_bytes(sender_key.public_key())
    salt = salt or os.urandom(16)

    shared = sender_key.exchange(ec.ECDH(), receiver)
    ikm = _hkdf(unb64url(auth), shared, b"WebPush: info\x00" + receiver_bytes + sender_bytes, 32)
    key = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    if len(plaintext) + 17 > RECORD_SIZE:
        raise ValueError("The message is too long for one record")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext + b"\x02", None)
    return salt + struct.pack("!IB", RECORD_SIZE, len(sender_bytes)) + sender_bytes + ciphertext


def vapid_header(endpoint, private_key, subject, now=None):
    """The Authorization header proving the message comes from the holder of the VAPID key."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    parts = urlsplit(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}",
              "exp": int((now or time.time()) + VAPID_LIFETIME_S), "sub": subject}
    signing_input = ".".join(b64url(json.dumps(part, separators=(",", ":")).encode())
                             for part in ({"typ": "JWT", "alg": "ES256"}, claims))
    r, s = decode_dss_signature(private_key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    token = f"{signing_input}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={token}, k={b64url(_public_bytes(private_key.public_key()))}"


def vapid_key_from_jwk(d, x, y):
    """The phone sends its VAPID key as the d, x and y of a JWK."""
    from cryptography.hazmat.primitives.asymmetric import ec

    numbers = ec.EllipticCurvePrivateNumbers(
        int.from_bytes(unb64url(d), "big"),
        ec.EllipticCurvePublicNumbers(int.from_bytes(unb64url(x), "big"),
                                      int.from_bytes(unb64url(y), "big"), ec.SECP256R1()))
    return numbers.private_key()


def send(subscription, payload, private_key, subject, ttl_s=60, urgency="high"):
    """Pushes a JSON payload. Raises requests' HTTPError if the push service refuses it."""
    import requests

    endpoint = subscription["endpoint"]
    body = encrypt(json.dumps(payload, separators=(",", ":")).encode(),
                   subscription["keys"]["p256dh"], subscription["keys"]["auth"])
    response = requests.post(endpoint, data=body, timeout=15, headers={
        "Authorization": vapid_header(endpoint, private_key, subject),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(ttl_s),
        "Urgency": urgency,
    })
    response.raise_for_status()
