"""A passkey made of software, for tests.

It does what Face ID / Touch ID hardware does: creates a key pair when registering and signs
challenges when signing in. This lets the tests run the server's real verification code.
"""
import base64
import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class SoftPasskey:
    def __init__(self, origin: str, rp_id: str):
        self.origin, self.rp_id = origin, rp_id
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.counter = 0
        self.user_handle = None

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin,
                           "crossOrigin": False}).encode()

    def _auth_data(self, with_key: bool) -> bytes:
        self.counter += 1
        flags = 0x01 | 0x04 | (0x40 if with_key else 0)  # user present, user verified, key attached
        data = hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", self.counter)
        if with_key:
            numbers = self.key.public_key().public_numbers()
            cose = {1: 2, 3: -7, -1: 1,
                    -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")}
            data += b"\x00" * 16 + struct.pack(">H", len(self.credential_id)) + self.credential_id
            data += cbor2.dumps(cose)
        return data

    def register(self, public_key_options: dict) -> dict:
        self.user_handle = public_key_options["user"]["id"]
        client_data = self._client_data("webauthn.create", public_key_options["challenge"])
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": self._auth_data(True)})
        return {
            "id": b64u(self.credential_id), "rawId": b64u(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64u(client_data), "attestationObject": b64u(attestation),
                         "transports": ["internal"]},
        }

    def sign_in(self, public_key_options: dict) -> dict:
        client_data = self._client_data("webauthn.get", public_key_options["challenge"])
        auth_data = self._auth_data(False)
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64u(self.credential_id), "rawId": b64u(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64u(client_data), "authenticatorData": b64u(auth_data),
                         "signature": b64u(signature), "userHandle": self.user_handle},
        }
