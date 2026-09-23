# Tools/wiki_scrape.py
# name: wiki_scrape
# arguments: query
# description: Scrape the summary/intro of a Wikipedia article by title or search query
# example: wiki_scrape(Python programming language)
# returns: Article title, URL, and summary text

import sys
import urllib.parse
import urllib.request
import json
API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "WikiScrapeTool/1.0 (https://example.com; contact@example.com)"

def fetch_json(params):
    """Fetch JSON from the Wikipedia API."""
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def search_title(query):
    """Find the best matching Wikipedia page title for a query."""
    data = fetch_json({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 1,
    })
    hits = data.get("query", {}).get("search", [])
    if not hits:
        return None
    return hits[0]["title"]

def get_summary(title):
    """Fetch the intro extract and URL for a page title."""
    data = fetch_json({
        "action": "query",
        "prop": "extracts|info",
        "inprop": "url",
        "exintro": 1,
        "explaintext": 1,
        "redirects": 1,
        "titles": title,
        "format": "json",
    })
    pages = data.get("query", {}).get("pages", {})
    for _, page in pages.items():
        if "missing" in page:
            return None
        return {
            "title": page.get("title"),
            "url": page.get("fullurl"),
            "summary": page.get("extract", "").strip(),
        }
    return None

def main(query):
    """Scrape a Wikipedia article summary."""
    try:
        title = search_title(query)
        if not title:
            print(f"Error: No Wikipedia article found for '{query}'")
            return

        info = get_summary(title)
        if not info:
            print(f"Error: Could not retrieve article '{title}'")
            return

        print(f"Title: {info['title']}")
        print(f"URL: {info['url']}")
        print(f"Summary:\n{info['summary']}")

    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        main(" ".join(sys.argv[1:]))
    else:
        print("Error: No query provided")