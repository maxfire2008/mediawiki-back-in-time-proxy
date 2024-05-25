import json
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
    response = requests.get(
        f"{MEDIAWIKI_INDEX_URL}/w/{page}?oldid={revision_id}",
        cookies=flask.request.cookies,
    )
    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup.find_all("a"):
        if tag.has_attr("href") and tag["href"].startswith("/w/"):
            tag["href"] = f"/{date}{tag['href']}"

    soup.find("div", {"id": "right-navigation"}).decompose()
    for tag in soup.find_all(
        "li",
        {
            "id": [
                "pt-anonuserpage",
                "pt-anontalk",
                "pt-anoncontribs",
                "pt-createaccount",
                "pt-login",
            ]
        },
    ):
        tag.decompose()
    # append a new div after mw-revision-nav a link to the page on https://minecraft.wiki
    div = soup.new_tag("div")
    div["id"] = "minecraft-wiki-link"
    a = soup.new_tag("a")
    a["href"] = f"https://minecraft.wiki/w/{page}?oldid={revision_id}"
    a.string = "View this page on https://minecraft.wiki"
    div.append(a)
    soup.find("div", {"id": "mw-revision-nav"}).insert_after(div)

    return str(soup)


@app.route("/w/<path:page>")
def error(page):
    return "Please provide a date", 400


@app.route("/api.php")
def api_php():
    params = flask.request.args.to_dict()
    response = requests.get(f"{MEDIAWIKI_INDEX_URL}/api.php", params=params)
    response_content = response.content.decode("utf-8")
    if "page" in params and params["page"] == "MediaWiki:Sidebar-versions":
        print("Modifying sidebar")
        data = json.loads(response_content)
        data_text_soup = BeautifulSoup(data["text"], "html.parser")
        data_parse_text_soup = BeautifulSoup(data["parse"]["text"], "html.parser")
        for tag in data_text_soup.find_all("a"):
            if tag.has_attr("href") and tag["href"].startswith("/w/"):
                tag["href"] = f"/{flask.request.args['date']}{tag['href']}"
        for tag in data_parse_text_soup.find_all("a"):
            if tag.has_attr("href") and tag["href"].startswith("/w/"):
                tag["href"] = f"/{flask.request.args['date']}{tag['href']}"

        data["text"] = str(data_text_soup)
        data["parse"]["text"] = str(data_parse_text_soup)
        response_content = json.dumps(data)
    prox_response = flask.Response(response_content)
    prox_response.headers["content-type"] = response.headers["content-type"]
    return prox_response


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
