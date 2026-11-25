import os

from tests.fake_google import CLIENT_ID

os.environ["DATABASE_URL"] = "postgresql://unused"
os.environ["GOOGLE_CLIENT_ID"] = CLIENT_ID
