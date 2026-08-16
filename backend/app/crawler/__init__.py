"""Configurable crawling primitives."""

from app.crawler.dns import (
    DnsResolutionError,
    DohHostResolver,
    PinnedAsyncHTTPTransport,
    PinnedNetworkBackend,
)
from app.crawler.fetcher import (
    Fetcher,
    FetchResponse,
    HttpFetcher,
    RedirectLimitError,
    ResponseTooLargeError,
)
from app.crawler.generic import (
    CrawlColumnResult,
    CrawlDiagnostics,
    CrawledAttachment,
    CrawledDocument,
    CrawlFailure,
    GenericCrawler,
    score_candidate,
)
from app.crawler.providers import (
    CozeCrawlProvider,
    CrawlProvider,
    CrawlProviderConnection,
    CrawlProviderError,
    CrawlProviderResult,
    LocalCrawlProvider,
)
from app.crawler.registry import CrawlerAdapterRegistry
from app.crawler.site_rules import SiteRules, site_rules_from_configs
from app.crawler.urls import UnsafeUrlError, normalize_url, validate_public_url

__all__ = [
    "CozeCrawlProvider",
    "CrawlColumnResult",
    "CrawlDiagnostics",
    "CrawlFailure",
    "CrawlProvider",
    "CrawlProviderConnection",
    "CrawlProviderError",
    "CrawlProviderResult",
    "CrawledAttachment",
    "CrawledDocument",
    "CrawlerAdapterRegistry",
    "DnsResolutionError",
    "DohHostResolver",
    "FetchResponse",
    "Fetcher",
    "GenericCrawler",
    "HttpFetcher",
    "LocalCrawlProvider",
    "PinnedAsyncHTTPTransport",
    "PinnedNetworkBackend",
    "RedirectLimitError",
    "ResponseTooLargeError",
    "SiteRules",
    "UnsafeUrlError",
    "normalize_url",
    "score_candidate",
    "site_rules_from_configs",
    "validate_public_url",
]
