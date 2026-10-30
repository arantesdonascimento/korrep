"""Which address the links in emails point to (the SITE_MODE switch).

Plain Python on purpose: settings.py imports it before Django is configured.
"""

LOCAL_SITE_URL = 'http://localhost:8000'
SERVER_SITE_URL = 'https://korrep.pythonanywhere.com'


def resolve_site_url(mode, local_url=LOCAL_SITE_URL, server_url=SERVER_SITE_URL, custom_url=''):
    """local -> your computer, server -> PythonAnywhere, custom -> SITE_URL from .env."""
    mode = (mode or '').strip().lower()
    if mode == 'local':
        url = local_url
    elif mode == 'server':
        url = server_url
    elif mode == 'custom':
        if not (custom_url or '').strip():
            raise ValueError("SITE_MODE=custom needs SITE_URL to be set in .env.")
        url = custom_url
    else:
        raise ValueError(f"SITE_MODE must be 'local', 'server' or 'custom', not {mode!r}.")
    url = url.strip().rstrip('/')
    if not url.startswith(('http://', 'https://')):
        raise ValueError(f'The site address must start with http:// or https://, got {url!r}.')
    return url
