"""Stable source identity used by verification views and quality metrics."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical_source(url):
    parsed = urlsplit(url)
    tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
    query = [
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in tracking
    ]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, urlencode(query), parsed.fragment))
