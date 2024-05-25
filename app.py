import flask
import requests
from bs4 import BeautifulSoup

app = flask.Flask(__name__)

MEDIAWIKI_API_URL = "https://minecraft.wiki/api.php"
MEDIAWIKI_INDEX_URL = "https://minecraft.wiki/"


def get_revision(date, page):
    params = {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "titles": page,
        "rvstart": date,
        "rvdir": "newer",
        "rvlimit": 1,
    }
    response = requests.get(MEDIAWIKI_API_URL, params=params)
    data = response.json()
    page_id = next(iter(data["query"]["pages"]))
    revision_id = data["query"]["pages"][page_id]["revisions"][0]["revid"]
    return revision_id


@app.route("/<path:date>/w/<path:page>")
def get_page(date, page):
    revision_id = get_revision(date, page)
    response = requests.get(f"{MEDIAWIKI_INDEX_URL}/w/{page}?oldid={revision_id}")
    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup.find_all("a"):
        if tag.has_attr("href") and tag["href"].startswith("/w/"):
            tag["href"] = f"/{date}{tag['href']}"
    return str(soup)


@app.route("/w/<path:page>")
def error(page):
    return "Please provide a date", 400


@app.errorhandler(404)
def page_not_found(e):
    # proxy the request to the wiki
    url = f"{MEDIAWIKI_INDEX_URL}{flask.request.full_path}"
    mcw_response = requests.get(url)
    prox_response = flask.Response(mcw_response.content)
    prox_response.headers["content-type"] = mcw_response.headers["content-type"]
    return prox_response


if __name__ == "__main__":
    app.run(debug=True)
