from .sync_client import SyncClient
from .async_client import AsyncClient
from .exceptions import TwoCaptchaError

TwoCaptcha = SyncClient
SyncTwoCaptcha = SyncClient
AsyncTwoCaptcha = AsyncClient
