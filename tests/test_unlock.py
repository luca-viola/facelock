"""Tests for unlocking: liveness, the face check, pairing, Web Push and the passkey check.

No camera, models, network or phone needed. Run with: python -m unittest discover -s tests
"""

import base64
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "extension", "daemon"))

import numpy as np
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import phone
import relay
import unlock
import webpush
from backends import DetectedFace
from liveness import HeadTurn, nose_offset

OWNER = np.array([1.0, 0.0])
STRANGER = np.array([0.0, 1.0])


def landmarks(offset):
    """Eyes 100 pixels apart, with the nose offset by that many eye spacings."""
    return (200.0, 200.0), (300.0, 200.0), (250.0 + 100 * offset, 250.0)


def face(vector, offset=0.0, size=120, with_landmarks=True):
    return DetectedFace(box=(0, 0, size, size), embedding=vector,
                        landmarks=landmarks(offset) if with_landmarks else None)


class LivenessTest(unittest.TestCase):
    def test_offset_is_in_eye_spacings(self):
        self.assertAlmostEqual(nose_offset(landmarks(0.0)), 0.0)
        self.assertAlmostEqual(nose_offset(landmarks(0.4)), 0.4)
        self.assertAlmostEqual(nose_offset(landmarks(-0.4)), -0.4)

    def test_a_flat_photo_keeps_its_offset_when_turned(self):
        # Turning a photo squeezes it sideways, which scales both distances alike.
        (lx, ly), (rx, ry), (nx, ny) = landmarks(0.05)
        squeezed = ((lx * 0.6, ly), (rx * 0.6, ry), (nx * 0.6, ny))
        self.assertAlmostEqual(nose_offset(squeezed), 0.05)

    def test_passes_after_ahead_turned_and_back(self):
        turn = HeadTurn()
        for offset in (0.0, 0.2, 0.35):
            self.assertFalse(turn.observe(landmarks(offset)))
        self.assertTrue(turn.observe(landmarks(0.1)))

    def test_either_side_counts(self):
        turn = HeadTurn()
        for offset in (0.0, -0.4, 0.0):
            turn.observe(landmarks(offset))
        self.assertTrue(turn.passed)

    def test_a_still_face_never_passes(self):
        turn = HeadTurn()
        for _ in range(50):
            turn.observe(landmarks(0.03))
        self.assertFalse(turn.passed)

    def test_starting_turned_needs_to_look_ahead_first(self):
        turn = HeadTurn()
        for offset in (0.4, 0.0):
            turn.observe(landmarks(offset))
        self.assertFalse(turn.passed)


class FakeCamera:
    def read(self):
        return np.zeros((10, 10, 3), np.uint8)


class FakeBackend:
    def __init__(self, frames):
        self._frames = list(frames)

    def faces(self, _image):
        return self._frames.pop(0) if self._frames else []

    def similarity(self, a, b):
        return float(a.dot(b))


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 0.1
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def run_check(frames, liveness=False, threshold=0.4):
    clock = FakeClock()
    events = []
    settings = unlock.UnlockSettings(match_threshold=threshold, min_face_px=40, liveness=liveness, timeout_s=10)
    reason = unlock.check_face(FakeCamera(), FakeBackend(frames), OWNER, settings,
                               lambda event, **fields: events.append((event, fields)),
                               clock=clock, sleep=clock.sleep)
    return reason, [fields["step"] for event, fields in events if event == "unlock_step"]


class CheckFaceTest(unittest.TestCase):
    def test_unlocks_after_three_close_matches(self):
        reason, _ = run_check([[face(OWNER)]] * 3)
        self.assertIsNone(reason)

    def test_a_loose_match_is_not_enough(self):
        # Matches for watching (0.4), but not for unlocking (0.5).
        loose = np.array([0.45, (1 - 0.45 ** 2) ** 0.5])
        reason, _ = run_check([[face(loose)]] * 30)
        self.assertEqual(reason, "Your face wasn't recognized")

    def test_a_stranger_never_unlocks(self):
        reason, _ = run_check([[face(STRANGER)]] * 30)
        self.assertEqual(reason, "Your face wasn't recognized")

    def test_someone_else_in_view_starts_over(self):
        frames = [[face(OWNER)], [face(OWNER)], [face(OWNER), face(STRANGER)], [face(OWNER)], [face(OWNER)]]
        reason, steps = run_check(frames)
        self.assertIsNotNone(reason)
        self.assertIn("alone", steps)

    def test_small_faces_far_away_are_ignored(self):
        frames = [[face(OWNER), face(STRANGER, size=20)]] * 3
        self.assertIsNone(run_check(frames)[0])

    def test_liveness_needs_the_head_to_turn(self):
        reason, _ = run_check([[face(OWNER)]] * 30, liveness=True)
        self.assertEqual(reason, "Your head didn't turn")

    def test_liveness_passes_with_a_turn(self):
        offsets = [0.0, 0.0, 0.2, 0.4, 0.2, 0.0, 0.0]
        reason, steps = run_check([[face(OWNER, offset)] for offset in offsets], liveness=True)
        self.assertIsNone(reason)
        self.assertIn("turn", steps)

    def test_a_stranger_turning_does_not_count(self):
        frames = [[face(OWNER, 0.0)], [face(STRANGER, 0.4)], [face(OWNER, 0.0)], [face(OWNER, 0.0)]]
        reason, _ = run_check(frames, liveness=True)
        self.assertIsNotNone(reason)

    def test_liveness_without_landmarks_says_so(self):
        reason, _ = run_check([[face(OWNER, with_landmarks=False)]] * 3, liveness=True)
        self.assertIn("points liveness needs", reason)


def decrypt_push(body, receiver, auth):
    """The browser's side of RFC 8291, to check what webpush.encrypt() makes."""
    salt, record_size, id_length = body[:16], *struct.unpack("!IB", body[16:21])
    sender_bytes = body[21:21 + id_length]
    ciphertext = body[21 + id_length:]
    receiver_bytes = receiver.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    sender = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sender_bytes)
    shared = receiver.exchange(ec.ECDH(), sender)

    def hkdf(salt_, ikm, info, length):
        return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt_, info=info).derive(ikm)

    ikm = hkdf(auth, shared, b"WebPush: info\x00" + receiver_bytes + sender_bytes, 32)
    key = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(key).decrypt(nonce, ciphertext, None)
    assert plain.endswith(b"\x02") and record_size == 4096
    return plain[:-1]


class WebPushTest(unittest.TestCase):
    def test_the_browser_can_decrypt_it(self):
        receiver = ec.generate_private_key(ec.SECP256R1())
        public = receiver.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        auth = os.urandom(16)
        body = webpush.encrypt(b'{"type":"unlock"}', webpush.b64url(public), webpush.b64url(auth))
        self.assertEqual(decrypt_push(body, receiver, auth), b'{"type":"unlock"}')

    def test_vapid_token_is_signed_for_the_push_service(self):
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

        key = ec.generate_private_key(ec.SECP256R1())
        header = webpush.vapid_header("https://web.push.apple.com/abc", key, "https://example.org/", now=1000)
        token = header.split("t=")[1].split(",")[0]
        signing_input, signature = token.rsplit(".", 1)
        raw = webpush.unb64url(signature)
        key.public_key().verify(
            encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
            signing_input.encode(), ec.ECDSA(hashes.SHA256()))
        claims = json.loads(webpush.unb64url(signing_input.split(".")[1]))
        self.assertEqual(claims["aud"], "https://web.push.apple.com")
        self.assertEqual(claims["exp"], 1000 + webpush.VAPID_LIFETIME_S)

    def test_vapid_key_round_trips_through_a_jwk(self):
        key = ec.generate_private_key(ec.SECP256R1())
        numbers = key.private_numbers()
        jwk = {"d": webpush.b64url(numbers.private_value.to_bytes(32, "big")),
               "x": webpush.b64url(numbers.public_numbers.x.to_bytes(32, "big")),
               "y": webpush.b64url(numbers.public_numbers.y.to_bytes(32, "big"))}
        self.assertEqual(webpush.vapid_key_from_jwk(**jwk).private_numbers(), numbers)


class SealTest(unittest.TestCase):
    def test_round_trip(self):
        key = os.urandom(32)
        self.assertEqual(relay.unseal(key, "topic-a", relay.seal(key, "topic-a", {"n": 1})), {"n": 1})

    def test_bound_to_the_topic_and_key(self):
        key = os.urandom(32)
        sealed = relay.seal(key, "topic-a", {"n": 1})
        self.assertIsNone(relay.unseal(key, "topic-b", sealed))
        self.assertIsNone(relay.unseal(os.urandom(32), "topic-a", sealed))
        self.assertIsNone(relay.unseal(key, "topic-a", "not base64 !"))


class Authenticator:
    """Signs like a phone's passkey would, for the page at page_url."""

    def __init__(self, page_url="https://luca-viola.github.io/facelock/"):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential = webpush.b64url(os.urandom(16))
        self.page_url = page_url

    def phone(self):
        spki = self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return {"credential": self.credential, "public_key": webpush.b64url(spki), "page_url": self.page_url}

    def sign(self, challenge, flags=0x05, origin=None, rp_id=None, kind="webauthn.get"):
        client_data = json.dumps({"type": kind, "challenge": webpush.b64url(challenge),
                                  "origin": origin or phone.page_origin(self.page_url)}).encode()
        auth_data = hashlib.sha256((rp_id or phone.rp_id(self.page_url)).encode()).digest() \
            + bytes([flags]) + b"\x00\x00\x00\x00"
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {"credential": self.credential, "client_data": webpush.b64url(client_data),
                "authenticator_data": webpush.b64url(auth_data), "signature": webpush.b64url(signature)}


class VerifyAssertionTest(unittest.TestCase):
    def setUp(self):
        self.authenticator = Authenticator()
        self.phone = self.authenticator.phone()
        self.challenge = phone.challenge_for(b"nonce", 42)

    def test_accepts_the_passkey_signing_the_challenge(self):
        self.assertTrue(phone.verify_assertion(self.phone, self.authenticator.sign(self.challenge), self.challenge))

    def test_rejects_another_challenge(self):
        answer = self.authenticator.sign(phone.challenge_for(b"nonce", 43))
        self.assertFalse(phone.verify_assertion(self.phone, answer, self.challenge))

    def test_rejects_without_user_verification(self):
        answer = self.authenticator.sign(self.challenge, flags=0x01)
        self.assertFalse(phone.verify_assertion(self.phone, answer, self.challenge))

    def test_rejects_another_site(self):
        for answer in (self.authenticator.sign(self.challenge, origin="https://evil.example"),
                       self.authenticator.sign(self.challenge, rp_id="evil.example"),
                       self.authenticator.sign(self.challenge, kind="webauthn.create")):
            self.assertFalse(phone.verify_assertion(self.phone, answer, self.challenge))

    def test_rejects_another_passkey(self):
        other = Authenticator()
        answer = other.sign(self.challenge)
        answer["credential"] = self.authenticator.credential
        self.assertFalse(phone.verify_assertion(self.phone, answer, self.challenge))

    def test_rejects_garbage(self):
        self.assertFalse(phone.verify_assertion(self.phone, {"credential": self.authenticator.credential},
                                                self.challenge))
        self.assertFalse(phone.verify_assertion(self.phone, {}, self.challenge))

    def test_localhost_is_allowed_for_testing_but_not_plain_http(self):
        self.assertEqual(phone.rp_id("http://localhost:8765/"), "localhost")
        with self.assertRaises(Exception):
            phone.page_origin("http://example.org/")


class DeviceKey:
    """Signs like the page's own key does on a phone without passkeys."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential = webpush.b64url(os.urandom(16))

    def phone(self):
        spki = self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return {"kind": phone.DEVICE_KEY, "credential": self.credential, "public_key": webpush.b64url(spki),
                "page_url": phone.PAGE_URL}

    def sign(self, challenge, context=None):
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

        context = phone.DEVICE_KEY_CONTEXT if context is None else context
        r, s = decode_dss_signature(self.key.sign(context + challenge, ec.ECDSA(hashes.SHA256())))
        return {"credential": self.credential, "signature": webpush.b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}


class DeviceKeyTest(unittest.TestCase):
    def setUp(self):
        self.device = DeviceKey()
        self.phone = self.device.phone()
        self.challenge = phone.challenge_for(b"nonce", 42)

    def test_accepts_the_device_key_signing_the_challenge(self):
        self.assertTrue(phone.verify_answer(self.phone, self.device.sign(self.challenge), self.challenge))

    def test_rejects_another_challenge_or_context(self):
        self.assertFalse(phone.verify_answer(self.phone, self.device.sign(phone.challenge_for(b"nonce", 43)),
                                             self.challenge))
        self.assertFalse(phone.verify_answer(self.phone, self.device.sign(self.challenge, context=b""),
                                             self.challenge))

    def test_rejects_another_key(self):
        answer = DeviceKey().sign(self.challenge)
        answer["credential"] = self.device.credential
        self.assertFalse(phone.verify_answer(self.phone, answer, self.challenge))

    def test_a_passkey_pairing_does_not_take_a_device_signature(self):
        passkey_phone = {**self.phone, "kind": phone.PASSKEY}
        self.assertFalse(phone.verify_answer(passkey_phone, self.device.sign(self.challenge), self.challenge))

    def test_matches_the_page(self):
        # web/app.js signed this in Chrome, with the key below, for challenge_for(AAECAw, 42).
        page = json.loads(PAGE_DEVICE_SIGNATURE)
        device_phone = {"kind": phone.DEVICE_KEY, "credential": "c", "public_key": page["public_key"],
                        "page_url": phone.PAGE_URL}
        challenge = phone.challenge_for(webpush.unb64url("AAECAw"), 42)
        self.assertTrue(phone.verify_answer(device_phone, {"credential": "c", "signature": page["signature"]},
                                            challenge))


PAGE_DEVICE_SIGNATURE = '{"public_key": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEw_ucSkxXj7OlK8599pPP0d0NCRDZkSziZqVygsqjyj5ipew18NocD8l0oGdtBYZoReCXJ_m41cx4PyGTbmzTGA", "signature": "C95kppz3oDmvbxX191bg0-XHqXM4z_EhalsRevqO3bBbtkMpKKav3dGtqDcFFmsixlXllYwusTNVHH9kfS45IQ"}'


class PairingCodeTest(unittest.TestCase):
    def test_code_is_twelve_unambiguous_characters(self):
        code = phone.new_code()
        self.assertEqual(len(code), 12)
        self.assertFalse(set(code) & set("01IO"))
        self.assertRegex(phone.show_code(code), r"^\w{4}-\w{4}-\w{4}$")

    def test_spacing_and_case_do_not_matter(self):
        self.assertEqual(phone.derive_pairing("ABCD-EFGH-JKLM"), phone.derive_pairing("abcd efgh jklm"))

    def test_matches_the_page(self):
        # The page (web/crypto.js) worked these out for the same code in Chrome.
        topic, key = phone.derive_pairing("ABCD-EFGH-JKLM")
        self.assertEqual(topic, "facelock-3486655d85ca19d61b1add2f6e95d3fb")
        self.assertEqual(webpush.b64url(key), "oUNL5kzYf0NlfQk6zMb2pwJ45ZATM9UyyHnjGUWnjWU")
        self.assertEqual(webpush.b64url(phone.challenge_for(webpush.unb64url("AAECAw"), 42)),
                         "a7aOE-6rfEHbxWD_bD-dqI8iRHWhGYEkOezG1fxCCeA")

    def test_number_choices_include_the_shown_one(self):
        for _ in range(20):
            shown, numbers = phone.number_choices()
            self.assertIn(shown, numbers)
            self.assertEqual(len(set(numbers)), 3)
            self.assertTrue(all(10 <= n <= 99 for n in numbers))


def pairing_reply(authenticator):
    vapid = ec.generate_private_key(ec.SECP256R1()).private_numbers()
    receiver = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {
        "credential": authenticator.credential,
        "public_key": authenticator.phone()["public_key"],
        "subscription": {"endpoint": "https://web.push.apple.com/xyz",
                         "keys": {"p256dh": webpush.b64url(receiver), "auth": webpush.b64url(os.urandom(16))}},
        "vapid": {"d": webpush.b64url(vapid.private_value.to_bytes(32, "big")),
                  "x": webpush.b64url(vapid.public_numbers.x.to_bytes(32, "big")),
                  "y": webpush.b64url(vapid.public_numbers.y.to_bytes(32, "big"))},
        "topic": "facelock-" + os.urandom(16).hex(),
        "key": webpush.b64url(os.urandom(32)),
        "device": "iPhone",
    }


class FakeRelay:
    """Delivers the messages that answer() makes once the listener is open."""

    def __init__(self, answer):
        self.answer = answer
        self.published = []

    def publish(self, topic, text, keep=True):
        self.published.append((topic, text, keep))

    def listen(self, topic, timeout_s, on_open=lambda: None):
        on_open()
        yield from self.answer(topic)


class PairTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        patcher = mock.patch.dict(os.environ, {"XDG_DATA_HOME": self.home.name, "XDG_RUNTIME_DIR": self.home.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_saves_the_phone_that_answers_with_the_code(self):
        events = []
        reply = pairing_reply(Authenticator())

        def answers(topic):
            code = next(fields["code"] for event, fields in events if event == "pair_code")
            pair_topic, key = phone.derive_pairing(code)
            self.assertEqual(topic, pair_topic)
            yield "junk from someone else"
            yield relay.seal(os.urandom(32), topic, reply)  # wrong key
            yield relay.seal(key, topic, reply)

        with mock.patch.object(phone, "Relay", lambda _server: FakeRelay(answers)), \
                mock.patch.object(phone, "push") as push:
            phone.pair("https://ntfy.sh", phone.PAGE_URL, lambda event, **fields: events.append((event, fields)))
        self.assertEqual(events[-1], ("paired", {"device": "iPhone", "kind": "passkey"}))
        saved = phone.load_phone()
        self.assertEqual(saved["credential"], reply["credential"])
        self.assertEqual(saved["topic"], reply["topic"])
        self.assertEqual(os.stat(phone.phone_path()).st_mode & 0o777, 0o600)
        push.assert_called_once()
        code_event = events[0][1]
        self.assertTrue(code_event["url"].startswith(phone.PAGE_URL + "#pair="))
        self.assertFalse(os.path.exists(code_event["qr"]))  # removed once paired

    def test_ignores_an_incomplete_reply(self):
        events = []
        reply = pairing_reply(Authenticator())
        del reply["subscription"]

        def answers(topic):
            code = next(fields["code"] for event, fields in events if event == "pair_code")
            yield relay.seal(phone.derive_pairing(code)[1], topic, reply)

        with mock.patch.object(phone, "Relay", lambda _server: FakeRelay(answers)):
            with self.assertRaises(phone.GuardError):
                phone.pair("https://ntfy.sh", phone.PAGE_URL, lambda event, **fields: events.append((event, fields)))
        self.assertIsNone(phone.load_phone())


class ApproveTest(unittest.TestCase):
    def setUp(self):
        self.authenticator = Authenticator()
        reply = pairing_reply(self.authenticator)
        self.phone = {**self.authenticator.phone(), "subscription": reply["subscription"], "vapid": reply["vapid"],
                      "topic": reply["topic"], "key": reply["key"], "relay": "https://ntfy.sh"}
        self.pushed = []
        patcher = mock.patch.object(phone, "push", lambda _phone, payload: self.pushed.append(payload))
        patcher.start()
        self.addCleanup(patcher.stop)

    def approve(self, respond, number_match=True):
        """respond(request, shown number) gives the page's answer, or None to stay silent."""
        events = []

        def answers(topic):
            request = self.pushed[-1]
            shown = next(fields["number"] for event, fields in events if event == "unlock_step")
            answer = respond(request, shown)
            if answer is not None:
                yield relay.seal(webpush.unb64url(self.phone["key"]), topic, answer)

        with mock.patch.object(phone, "Relay", lambda _server: FakeRelay(answers)):
            return phone.approve(self.phone, number_match, lambda event, **fields: events.append((event, fields)))

    def signed(self, request, pick):
        challenge = phone.challenge_for(webpush.unb64url(request["nonce"]), pick)
        return {"nonce": request["nonce"], "pick": pick, **self.authenticator.sign(challenge)}

    def test_unlocks_when_the_right_number_is_signed(self):
        self.assertIsNone(self.approve(lambda request, shown: self.signed(request, shown)))
        self.assertEqual(len(self.pushed[0]["numbers"]), 3)

    def test_a_wrong_number_does_not_unlock(self):
        def wrong(request, shown):
            return self.signed(request, next(n for n in request["numbers"] if n != shown))
        self.assertEqual(self.approve(wrong), "That wasn't the number on the screen")

    def test_a_wrong_number_claimed_as_right_does_not_unlock(self):
        def lying(request, shown):
            answer = self.signed(request, next(n for n in request["numbers"] if n != shown))
            answer["pick"] = shown
            return answer
        self.assertEqual(self.approve(lying), "The phone's answer didn't check out")

    def test_the_request_also_goes_to_an_open_page(self):
        relays = []

        def make(_server):
            relays.append(FakeRelay(lambda topic: iter([])))
            return relays[-1]

        with mock.patch.object(phone, "Relay", make):
            phone.approve(self.phone, True, lambda event, **fields: None, timeout_s=1)
        (topic, text, keep), = relays[0].published
        self.assertEqual(topic, self.phone["topic"] + "-ask")
        self.assertFalse(keep)
        request = relay.unseal(webpush.unb64url(self.phone["key"]), topic, text)
        self.assertEqual(request, self.pushed[0])

    def test_without_number_matching(self):
        self.assertIsNone(self.approve(lambda request, _shown: self.signed(request, None), number_match=False))
        self.assertIsNone(self.pushed[0]["numbers"])

    def test_declining(self):
        self.assertEqual(self.approve(lambda request, _shown: {"nonce": request["nonce"], "deny": True}),
                         "Declined on the phone")

    def test_an_answer_to_an_old_request_is_ignored(self):
        def stale(request, shown):
            return {**self.signed(request, shown), "nonce": webpush.b64url(b"old")}
        self.assertEqual(self.approve(stale), "The phone didn't answer")

    def test_silence(self):
        self.assertEqual(self.approve(lambda _request, _shown: None), "The phone didn't answer")


if __name__ == "__main__":
    unittest.main()
