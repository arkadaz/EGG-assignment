import os

from tests.fake_google import CLIENT_ID, OWNER

os.environ["DATABASE_URL"] = "postgresql://unused"
os.environ["ALLOWED_EMAIL"] = OWNER
os.environ["GOOGLE_CLIENT_ID"] = CLIENT_ID
