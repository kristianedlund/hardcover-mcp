"""Tools: search_books, get_book."""

import json

from mcp.types import TextContent

from hardcover_mcp.client import execute

SEARCH_BOOKS_QUERY = """
query SearchBooks($query: String!, $per_page: Int!, $page: Int!) {
    search(query: $query, query_type: "Book", per_page: $per_page, page: $page) {
        results
    }
}
"""

GET_BOOK_BY_ID_QUERY = """
query GetBookById($id: Int!) {
    books(where: {id: {_eq: $id}}, limit: 1) {
        id
        title
        slug
        subtitle
        description
        release_year
        pages
        rating
        ratings_count
        contributions {
            author {
                name
                slug
            }
        }
    }
}
"""

GET_BOOK_BY_SLUG_QUERY = """
query GetBookBySlug($slug: String!) {
    books(where: {slug: {_eq: $slug}}, limit: 1) {
        id
        title
        slug
        subtitle
        description
        release_year
        pages
        rating
        ratings_count
        contributions {
            author {
                name
                slug
            }
        }
    }
}
"""


def _format_search_hit(hit: dict) -> dict:
    """Extract the useful fields from a search hit."""
    doc = hit.get("document", {})
    authors = doc.get("author_names", [])
    return {
        "id": doc.get("id"),
        "title": doc.get("title"),
        "slug": doc.get("slug"),
        "authors": authors,
        "release_year": doc.get("release_year"),
        "rating": doc.get("rating"),
        "pages": doc.get("pages"),
        "series": doc.get("featured_series"),
    }


async def handle_search_books(arguments: dict) -> list[TextContent]:
    query = arguments.get("query", "").strip()
    if not query:
        return [TextContent(type="text", text="Error: 'query' is required.")]

    per_page = min(arguments.get("per_page", 10), 25)
    page = arguments.get("page", 1)

    result = await execute(SEARCH_BOOKS_QUERY, {
        "query": query,
        "per_page": per_page,
        "page": page,
    })

    raw_results = result["data"]["search"]["results"]
    hits = raw_results.get("hits", [])
    found = raw_results.get("found", 0)

    books = [_format_search_hit(h) for h in hits]
    output = {"found": found, "page": page, "books": books}
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def handle_get_book(arguments: dict) -> list[TextContent]:
    book_id = arguments.get("id")
    slug = arguments.get("slug")

    if not book_id and not slug:
        return [TextContent(type="text", text="Error: provide either 'id' or 'slug'.")]

    if book_id:
        result = await execute(GET_BOOK_BY_ID_QUERY, {"id": int(book_id)})
    else:
        result = await execute(GET_BOOK_BY_SLUG_QUERY, {"slug": slug})

    books = result["data"]["books"]
    if not books:
        return [TextContent(type="text", text="No book found.")]

    book = books[0]
    # Flatten authors for readability
    book["authors"] = [c["author"]["name"] for c in book.get("contributions", [])]
    del book["contributions"]

    return [TextContent(type="text", text=json.dumps(book, indent=2))]
