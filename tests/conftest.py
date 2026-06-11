import os

# Disable auth gate during pytest so existing API tests keep working.
os.environ.setdefault("AUTH_ENABLED", "false")
