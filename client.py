import functools
import time
import httpx

BASE_URL = "https://pokeapi.co/api/v2/pokemon"


def retry(times=3, delay=1.0):
    """Retry a function with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(times):
                try:
                    return func(*args, **kwargs)
                except (httpx.HTTPError, httpx.TimeoutException):
                    if attempt == times - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))
        return wrapper
    return decorator


@retry(times=3, delay=0.5)
def fetch_page(client: httpx.Client, url: str) -> dict:
    """Fetch one page, honouring the API's rate-limit header."""
    response = client.get(url, timeout=10)

    if response.status_code == 429:
        wait = int(response.headers.get("Retry-After", 5))
        time.sleep(wait)
        response = client.get(url, timeout=10)

    response.raise_for_status()
    return response.json()


def iter_pokemon(max_items: int = 40):
    """Yield pokemon dicts one at a time, following the API's `next` link."""
    url = f"{BASE_URL}?limit=20&offset=0"
    seen = 0

    with httpx.Client() as client:
        while url and seen < max_items:
            page = fetch_page(client, url)

            for item in page["results"]:
                yield item
                seen += 1
                if seen >= max_items:
                    return

            url = page.get("next")
