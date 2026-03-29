from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Single shared limiter instance — registered in app.state so SlowAPIASGIMiddleware
# and all route decorators use the same backend storage.
limiter = Limiter(key_func=get_remote_address, enabled=not settings.DEBUG)
