# Crawler Pytoh 3.7+

Asynchronous crawler for a news site [Hacker News](https://news.ycombinator.com/news)

Script searches for the first 30 news from the site page [Hacker News](https://news.ycombinator.com/news). For each news, it analyzes comments, if there are links, loads them into the directory of the downloaded article. Crawler periodically checks the main page for new news and loads them.

## Installation

```bash
pip install -r requirements.txt
```
## Run

```bash
python -m ycrwler.py
```