import os
from pathlib import Path

ARTICLES_IMG = Path(__file__).parent / "static" / "img" / "articles"

REQUIRED_ENV_VARS = [
    "TWITTER_API_KEY",
    "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN",
    "TWITTER_ACCESS_TOKEN_SECRET",
]


def _site_base_url():
    return os.environ.get("SITE_BASE_URL", "http://localhost:5000").rstrip("/")


def build_tweet_text(article):
    url = f"{_site_base_url()}/article/{article['id']}"
    title = article["title"]
    max_title_len = 260 - len(url)
    if len(title) > max_title_len:
        title = title[:max_title_len - 1].rstrip() + "…"
    return f"{title}\n\n{url}"


def post_tweet_for_article(article):
    """Tweet the published article's title + link + cover image.

    Returns a dict: {"sent": bool, "reason": str | None}.
    Never raises — a Twitter failure must not block publishing the article.
    """
    text = build_tweet_text(article)
    creds = {name: os.environ.get(name) for name in REQUIRED_ENV_VARS}

    if not all(creds.values()):
        print(f"[twitter] modo dry-run (faltan credenciales en el entorno): tuitearía:\n{text}\n", flush=True)
        return {"sent": False, "reason": "missing_credentials"}

    try:
        import tweepy

        auth = tweepy.OAuth1UserHandler(
            creds["TWITTER_API_KEY"], creds["TWITTER_API_SECRET"],
            creds["TWITTER_ACCESS_TOKEN"], creds["TWITTER_ACCESS_TOKEN_SECRET"],
        )
        media_ids = []
        cover = article.get("cover")
        if cover:
            cover_path = ARTICLES_IMG / cover
            if cover_path.exists():
                api_v1 = tweepy.API(auth)
                media = api_v1.media_upload(filename=str(cover_path))
                media_ids.append(media.media_id)

        client = tweepy.Client(
            consumer_key=creds["TWITTER_API_KEY"], consumer_secret=creds["TWITTER_API_SECRET"],
            access_token=creds["TWITTER_ACCESS_TOKEN"], access_token_secret=creds["TWITTER_ACCESS_TOKEN_SECRET"],
        )
        client.create_tweet(text=text, media_ids=media_ids or None)
        return {"sent": True, "reason": None}
    except Exception as e:
        print(f"[twitter] error al publicar el tweet: {e}", flush=True)
        return {"sent": False, "reason": str(e)}
