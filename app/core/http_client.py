import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


_RETRYABLE_METHODS = frozenset({"GET"})


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=_RETRYABLE_METHODS,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


session = _build_session()
