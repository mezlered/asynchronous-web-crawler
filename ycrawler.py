import aiofiles
import argparse
import asyncio
import logging
import mimetypes
import os
import re
from collections import namedtuple
from html import unescape

import aiohttp


BASE_URL = 'https://news.ycombinator.com/'
REQUEST_TIMEOUT = 60
DEFAULT_REFRESH_TIME = 360
LIMIT_PER_HOST = 4
DEFAULT_OUTPUT_DIR = './download/'
RE_COMMENT_LINK = re.compile(r'<span class="commtext.+?<a href="(.+?)"')
RE_STORY_LINK = re.compile(
    r"<tr class=\'athing\' id=\'(\d+)\'>\n.+?"
    r'<a href="(.+?)" class="storylink".*?>(.+?)</a>')

ArticleInfo = namedtuple('ArticleInfo', 'title url id')
CommentsInfo = namedtuple('CommentsInfo', 'name url')


def create_dir(directories):
    try:
        os.mkdir(directories)
    except:
        raise OSError(f"Can't create destination directory :{directories}") 
    return directories


async def download(session, url, path, filename):
    """Dowload the page with url to file path/flename"""

    client_timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    try:
        async with session.get(url, timeout=client_timeout) as response:
            content = await response.content.read()
            ext = mimetypes.guess_extension(response.content_type)
            path_file =  os.path.join(path, f"{filename}{ext}")
    except Exception as exc:
        logging.exception(f'error: {exc}')
        return
        
    async with aiofiles.open(path_file, "wb") as fd:
        await fd.write(content)

    logging.debug(
            f"URL: {url} has been successfully downloaded to {path}"
        )


async def download_manager(session, output_dir, article):
    """
    Creates a task to download articles along the path output_dir/article_name/
    If there are links in the comments, create a tasks to load them in 
    output_dir/article_name/comments
    
    Download all URL to file
    """

    article_name = re.sub(r"\W", " ", article.title)
    article_dir = os.path.join(output_dir, article_name)

    if os.path.isdir(article_dir):
        logging.info(f"{article.title} already downloaded")
        return
    
    create_dir(article_dir)
   
    article_url = article.url
    if article.url.startswith("item?"):
        article_url = f"{BASE_URL}{article.url}"
        logging.debug("Convert relative link: {BASE_URL} -> {article_url}")

    tasks = {
        asyncio.create_task(
            download(session, article_url, article_dir, article_name)
        ): article_url
    }

    url_coments = f"{BASE_URL}item?id={article.id}"
    comments_urls = await get_comments_urls(session, url_coments)

    if comments_urls:
        comments_dir = os.path.join(article_dir, 'comments')
        create_dir(comments_dir)

        tasks = {
            asyncio.create_task(
                download(session,
                    comment.url,
                    comments_dir,
                    filename=comment.name)):comment.url
        for comment in comments_urls}

    files_downloaded = 0
    for task in tasks:
        try:
            await task
        except asyncio.TimeoutError:
            logging.warning(f"URL: {tasks[task]} failed by timeout.")
        except aiohttp.ClientError as exc:
            logging.warning(f"URL: {tasks[task]} is unavailable ({exc})")
        except Exception as exp:
            logging.exception(f'Unexpected error: {exc}')
        else:
            files_downloaded += 1

        logging.info(
            f"file url:{tasks[task]} has been downloaded [{files_downloaded} of {len(tasks)}]"
        )


async def fetch(session, url):
    client_timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with session.get(url, timeout=client_timeout) as response:
        logging.debug(f"Got response {response.status} for: {url}")
        html = await response.text(encoding="utf-8")
        return html


async def get_comments_urls(session, url_comments):
    """Parse comments page HTML and return list of CommentsInfo objects."""

    comments_urls = []
    try:
        html = await fetch(session, url_comments)
    except Exception:
        logging.exception(f"Could not fetch {url_comments}")
        return comments_urls

    for url in RE_COMMENT_LINK.findall(html):
        comments_urls.append(CommentsInfo(url=unescape(url), name=re.sub("\W", " ", url)))
    return comments_urls


async def get_article_info(session, url):
    """Parse index page HTML and return list of ArticleInfo objects."""

    articles = []
    try:
        html = await fetch(session, url)
    except Exception:
        logging.exception(f"Could not fetch {url}")
        return articles

    for article_id, url, title in RE_STORY_LINK.findall(html):
        articles.append(ArticleInfo(title, unescape(url), article_id))
    return articles


async def crawler(arguments):
    """Crawl index page - BASE_URL."""

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    connector = aiohttp.TCPConnector(limit_per_host=LIMIT_PER_HOST,
                                     force_close=True)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        articles = await get_article_info(session, BASE_URL)
        tasks = (download_manager(session, arguments.output_dir, article)
                 for article in articles)
        await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("Crawler new tasks")


async def main(arguments):
    if not os.path.exists(arguments.output_dir):
        create_dir(arguments.output_dir)

    while True:
        refresh_time = asyncio.create_task(
            asyncio.sleep(arguments.refresh_time))
        try:
            await asyncio.wait_for(crawler(arguments), timeout=arguments.refresh_time)
        except asyncio.TimeoutError:
            logging.error('Crawling timed out')
        await refresh_time


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument('-r', '--refresh_time', type=int, default=DEFAULT_REFRESH_TIME)
    args.add_argument('-l', '--log', action='store', default=None)
    args.add_argument('-o', '--output_dir', type=str, default=DEFAULT_OUTPUT_DIR)
    args.add_argument('-d', '--debug', action='store_true', default=False)

    arguments = args.parse_args()
    logging.basicConfig(filename=arguments.log,
                        level=logging.DEBUG if arguments.debug else logging.INFO,
                        format='[%(asctime)s] %(levelname).1s %(message)s',
                        datefmt='%Y.%m.%d %H:%M:%S')

    try:
        logging.info('Crawler started')
        asyncio.run(main(arguments))
    except KeyboardInterrupt:
        logging.info('Crawler has stopped')
    except Exception as exc: 
        logging.exception(f'Unexpected error: {exc}')
