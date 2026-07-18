from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

MIN_TEXT_LENGTH = 200
USER_AGENT = "Mozilla/5.0 (compatible; mini-researcher/0.1; +https://github.com/shaokiat/agentic-cookbook)"


@dataclass
class ScrapedDoc:
    url: str
    title: str
    text: str


def scrape(url: str, timeout: int = 8) -> ScrapedDoc | None:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    except requests.exceptions.RequestException:
        return None

    if resp.status_code >= 400:
        return None
    if "text/html" not in resp.headers.get("content-type", ""):
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else url

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text = "\n\n".join(p for p in paragraphs if p)

    if len(text) < MIN_TEXT_LENGTH:
        return None

    return ScrapedDoc(url=url, title=title, text=text)
