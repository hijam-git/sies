"""Pagination for every list endpoint (CLAUDE.md §5)."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Page-number pagination, 25 per page.

    25 rather than DRF's unset default because the SPA's table shows that many
    without scrolling, and because an unpaginated list of a year's payments is a
    query nobody meant to run.

    `page_size` is client-settable up to a ceiling: the CSV export screens fetch
    in large pages, and without a cap "give me everything" is one query string
    away.
    """

    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200
