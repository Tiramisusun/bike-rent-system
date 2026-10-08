"""Flask extensions shared between app.py and the blueprints."""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Per-client-IP limits. In-memory storage is per process, which is why the
# web container runs a single gunicorn worker (with threads).
limiter = Limiter(
    get_remote_address,
    default_limits=["300 per minute"],
    storage_uri="memory://",
)
