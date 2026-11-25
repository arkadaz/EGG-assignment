import time
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

OWNER = "owner@example.com"
FRIEND = "friend@example.com"
CLIENT_ID = "test-client-id"
GOOGLE_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class SigningKey:
    key: rsa.RSAPublicKey


class FakeGoogleKeys:
    def get_signing_key_from_jwt(self, token: str) -> SigningKey:
        return SigningKey(GOOGLE_PRIVATE_KEY.public_key())


def google_token(private_key=GOOGLE_PRIVATE_KEY, **changes) -> str:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "email": OWNER,
        "email_verified": True,
        "exp": int(time.time()) + 3600,
    }
    claims.update(changes)
    return jwt.encode(claims, private_key, algorithm="RS256")
