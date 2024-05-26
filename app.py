import json
import flask
import requests
from bs4 import BeautifulSoup
import datetime
import urllib.parse

app = flask.Flask(__name__)

MEDIAWIKI_API_URL = "https://minecraft.wiki/api.php"
MEDIAWIKI_INDEX_URL = "https://minecraft.wiki/"


def check_for_page_move(page):
    # moved page File:Bunch of birch trees.png to File:Bunch of pine trees.png Tag: move
    response = requests.get(
        f"{MEDIAWIKI_INDEX_URL}/w/{page}", cookies=flask.request.cookies
    )
    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup.find_all("li", {"class": "mw-tag-move"}):
        # find the last A tag in the LI tag but not anything nested
        a = tag.find_all("a", recursive=False)[-1]
        # get the href attribute and remove the /w/ part
        new_page = a["href"].split("/w/")[-1]
        return new_page
    return page


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
    page = check_for_page_move(page)
    revision_id = get_revision(date, page)
    response = requests.get(
        f"{MEDIAWIKI_INDEX_URL}/w/{page}?oldid={revision_id}",
        cookies=flask.request.cookies,
    )
    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup.find_all("a"):
        if tag.has_attr("href") and tag["href"].startswith("/w/"):
            tag["href"] = f"/{date}{tag['href']}"

    for img in soup.find_all("img"):
        if img.has_attr("src") and img["src"].startswith("/"):
            img["src"] = f"/{date}{img['src']}"
            del img["width"]
        if img.has_attr("srcset") and img["srcset"].startswith("/"):
            img["srcset"] = f"/{date}{img['srcset']}"
            del img["width"]

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

    for tag in soup.find_all(
        "nav",
        {
            "id": [
                "p-navigation",
                "p-Wiki_community",
                "p-Games",
                "p-Recent_versions",
                "p-tb",
                "p-lang",
            ]
        },
    ):
        tag.decompose()

    for tag in soup.find_all("a", {"class": "new"}):
        # <a class="new" href="/2013-01-01T12:00:00/w/Special:Upload?wpDestFile=Screentree2.PNG" title="File:Screentree2.PNG">
        #   <span class="mw-file-element mw-broken-media" data-width="180">File:Screentree2.PNG</span>
        # </a>
        # change to
        # <a class="mw-file-description" href="/2013-01-01T12:00:00/w/File:Screentree2.PNG">
        #   <img class="mw-file-element" decoding="async" width="180" loading="lazy" src="/2013-01-01T12:00:00/images/Screentree2.PNG" srcset="/2013-01-01T12:00:00/images/Screentree2.PNG">
        # </a>
        if tag.find("span", {"class": "mw-file-element mw-broken-media"}) is None:
            continue

        new_a = soup.new_tag("a")
        new_a["class"] = "mw-file-description"
        new_a["href"] = (
            f"/{date}/w/File:{tag['href'].split('Special:Upload?wpDestFile=')[-1]}"
        )
        old_url = "/" + date + "/images/" + tag.find("span").string.split(":")[-1]
        # old_url = "old_url"
        # print(old_url)
        img = soup.new_tag("img")
        img["class"] = "mw-file-element"
        img["decoding"] = "async"
        if tag.find("span").has_attr("data-width"):
            img["width"] = tag.find("span")["data-width"]
        img["loading"] = "lazy"
        img["src"] = old_url
        img["srcset"] = old_url
        new_a.append(img)
        tag.replace_with(new_a)

    # append a new div after mw-revision-nav a link to the page on https://minecraft.wiki
    div = soup.new_tag("div")
    div["id"] = "minecraft-wiki-link"
    a = soup.new_tag("a")
    a["href"] = f"https://minecraft.wiki/w/{page}?oldid={revision_id}"
    a.string = "View this page on https://minecraft.wiki"
    div.append(a)
    soup.find("div", {"id": "mw-revision-nav"}).insert_after(div)

    return str(soup)


def get_image_revision(date, image, offset=0, oldest_url=None, oldest_date=None):
    response = requests.get(
        f"{MEDIAWIKI_INDEX_URL}/w/File:{image}?limit=500&offset={offset}",
        cookies=flask.request.cookies,
    )

    img_found = False

    soup = BeautifulSoup(response.content, "html.parser")
    for img in soup.find_all("img"):
        # <img alt="Thumbnail for version as of 02:40, 12 May 2022" src="/images/thumb/archive/20230605172542%21Block_overview.png/64px-Block_overview.png?c3e08" decoding="async" loading="lazy" width="64" height="120" data-file-width="1575" data-file-height="2934">
        if img.has_attr("alt") and img["alt"].startswith("Thumbnail for version as of"):
            img_date_str = img["alt"].split(" ")[-4:]
            img_date = datetime.datetime.strptime(
                " ".join(img_date_str), "%H:%M, %d %B %Y"
            )
            if img_date <= datetime.datetime.fromisoformat(date):
                return img.parent["href"]
            if oldest_date is None or img_date < oldest_date:
                oldest_date = img_date
                oldest_url = img.parent["href"]
            img_found = True
    if img_found:
        return get_image_revision(date, image, offset + 500, oldest_url, oldest_date)

    return oldest_url


def check_for_image_move(image):
    return check_for_page_move(f"File:{image}").split("File:")[-1]


@app.route("/<path:date>/images/thumb/<path:image>/<path:thumb>")
def get_image_thumbnail(date, image, thumb):
    image = check_for_image_move(image)
    return flask.redirect(get_image_revision(date, f"{image}"), code=302)


@app.route("/<path:date>/images/<path:image>")
def get_image(date, image):
    image = check_for_image_move(image)
    return flask.redirect(get_image_revision(date, f"{image}"), code=302)


@app.route("/w/<path:page>")
def error(page):
    return "Please provide a date", 400


@app.route("/api.php")
def api():
    params = flask.request.args.to_dict()

    mcw_response = requests.get(MEDIAWIKI_API_URL, params=params)
    response_content = mcw_response.content

    request_page = flask.request.headers.get("Referer")
    request_date = urllib.parse.urlparse(request_page).path.split("/")[1]

    if params.get("page") == "MediaWiki:Sidebar-versions":
        data = json.loads(response_content)

        parse_text_soup = BeautifulSoup(data["parse"]["text"], "html.parser")
        for tag in parse_text_soup.find_all("a"):
            if tag.has_attr("href") and tag["href"].startswith("/w/"):
                tag["href"] = f"/{request_date}{tag['href']}"
        data["parse"]["text"] = str(parse_text_soup)

        response_content = json.dumps(data)

    if params.get("prop") == "imageinfo":
        data = json.loads(response_content)
        if "query" in data and "pages" in data["query"]:
            for page in data["query"]["pages"]:
                if "imageinfo" in page:
                    for info in page["imageinfo"]:
                        if "url" in info:
                            info["url"] = f"/{request_date}{info['url']}"
                        if "descriptionurl" in info:
                            info["descriptionurl"] = (
                                f"/{request_date}{info['descriptionurl']}"
                            )
                        if "descriptionshorturl" in info:
                            info["descriptionshorturl"] = (
                                f"/{request_date}{info['descriptionshorturl']}"
                            )
        response_content = json.dumps(data)

    if params.get("modules") == "startup" and params.get("only") == "scripts":
        return "", 404

    prox_response = flask.Response(response_content)
    prox_response.headers["content-type"] = mcw_response.headers["content-type"]
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
