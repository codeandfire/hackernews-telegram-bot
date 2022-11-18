import sys
import enum
from collections import namedtuple

import requests
from bs4 import BeautifulSoup

CHAT_ID = "<CHAT-ID-HERE>"
SITE_URL = "https://news.ycombinator.com"
API_URL = "https://api.telegram.org/bot{token}/{method_name}"
API_TOKEN = "<API-TOKEN-HERE>"
MSG_CHAR_LIMIT = 1000

News = namedtuple('News', ['name', 'link', 'points', 'discuss_link'])

class Time(enum.Enum):
    SECOND = 1
    MINUTE = 60                 # these numbers are the number of seconds they are equal to
    HOUR = 60 * 60
    DAY = 60 * 60 * 24

def request_bot(token, method_name, **kwargs):
    """Send a request to the Telegram bot."""
    resp = requests.get(API_URL.format(token=token, method_name=method_name), params=kwargs)
    return resp

def check_time(val, text_unit, lim_secs):
    """Check if the time given by value val in a unit written in text text_unit 
    is lesser than the limit of lim_secs number of seconds.
    """
    if text_unit.endswith('s'):
        text_unit = text_unit[:-1]
    for tm in Time:
        if str(tm.name).lower() == text_unit:
            unit = tm.value
            break
    else:           # no break
        return None
    return ((val * unit) < lim_secs)

def render_news(news, shlink_nchars=50):
    """Render a single News namedtuple.
    shlink_chars is the max. number of characters allowed in the shortened version
    of the link.
    """
    line1 = '{} | {} points'.format(news.name, news.points)
    nchars = len(line1)
    shlink = news.link[:shlink_nchars]
    if len(news.link) > shlink_nchars:
        shlink += '...'
    line2 = '<a href="{}">{}</a>'.format(news.link, shlink)
    nchars += len(shlink)
    if news.discuss_link is not None:
        line2 += ' | <a href="{}">discuss</a>'.format(news.discuss_link)
        nchars += len(' | discuss')
    html = line1 + '\n' + line2 + '\n\n'
    nchars += 3             # for the 3 newlines
    return (nchars, html)

def send_message(text):
    """Send a message from the Telegram bot."""
    resp = request_bot(API_TOKEN, 'sendMessage', chat_id=CHAT_ID, text=text, parse_mode='HTML')
    if resp.status_code != 200:
        print(resp.text, file=sys.stderr)
        sys.exit(1)

def scrape(time_limit=Time.DAY.value, cross_tries_num=5):
    """Carry out the scraping.
    time_limit is a limit on how old an article should be.
    cross_tries_num is the number of pages on which scraping should be tried
    after no articles within time_limit were found on the given page.
    """
    url_suffix = ''
    crossed = True                                  # all articles on page cross the time limit
    cross_tries = cross_tries_num                   # number of page tries left
    while True:
        req = requests.get(SITE_URL + '/' + url_suffix)
        html = BeautifulSoup(req.content, 'html.parser')
        html = html.find('table', id='hnmain')
        html = html.find_all('tr', recursive=False)
        assert html[2]['id'] == 'pagespace'         # such assert checks are useful in verifying that the page structure is as expected
        html = html[3]
        html = html.find_all('tr')
        for i in range(len(html) // 3):
            title = html[3*i]
            title = title.find('span', class_='titleline')
            title = title.find('a')
            name, link = title.string, title['href']
            if name.startswith('Ask HN') or name.startswith('Show HN'):
                link = SITE_URL + '/' + link
            subtext = html[3*i + 1].find('td', class_='subtext')
            try:
                score = subtext.find('span', class_='score').string.split(' ')
            except AttributeError:          # no score given
                score = 0
            else:
                assert score[1] == 'points'
                score = score[0]
            time = subtext.find('span', class_='age').string.split(' ')
            assert time[2] == 'ago'
            if check_time(int(time[0]), time[1], time_limit):
                crossed = False
                discuss_link = subtext.find_all('a')
                if not 'comments' in discuss_link[-1].string:
                    discuss_link = None
                else:
                    assert discuss_link[-2].string == 'hide'
                    discuss_link = discuss_link[-1]['href']
                    discuss_link = SITE_URL + '/' + discuss_link
                assert html[3*i + 2]['class'] == ['spacer']
                yield News(name, link, score, discuss_link)
        if crossed:
            if cross_tries == 1:            # this was the last try
                break
            else:
                cross_tries -= 1
        else:
            crossed = True
            cross_tries = cross_tries_num
        try:
            url_suffix = html[-1].find('a', class_='morelink')['href']
        except TypeError:                   # no 'More' link
            break

if __name__ == '__main__':
    nchars = 0
    message = ''
    for news in scrape(6 * Time.HOUR.value):
        nchars_inc, message_inc = render_news(news)
        if nchars + nchars_inc > MSG_CHAR_LIMIT:
            message = message[:-2]          # -2 removes the trailing \n\n
            send_message(message)
            nchars = 0
            message = ''
        nchars += nchars_inc
        message += message_inc
    if nchars > 0:
        message = message[:-2]
        send_message(message)
