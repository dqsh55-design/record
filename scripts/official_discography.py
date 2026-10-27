"""Collect official-page candidates; publish only explicitly reviewed candidates."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlsplit
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]


def key(text):
    return re.sub(r'[^\w]', '', text.casefold())


def safe_url(url, host):
    p = urlsplit(url)
    return p.scheme == 'https' and p.netloc == host and not p.username and not p.password


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.href, self.text = [], None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.href, self.text = attrs.get('href'), []
        if tag == 'img' and self.href and attrs.get('alt'):
            self.text.append(attrs['alt'])

    def handle_data(self, data):
        if self.href:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            self.links.append((self.href, ' '.join(' '.join(self.text).split())))
            self.href, self.text = None, []


class WarnerCards(HTMLParser):
    """Read visible album cards, excluding navigation and non-album media."""
    def __init__(self):
        super().__init__()
        self.cards = []
        self.card = None
        self.heading = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.card = {'href': attrs.get('href', ''), 'title': [], 'album': False}
        if tag == 'h3' and self.card:
            self.heading = True

    def handle_data(self, data):
        if self.card:
            if self.heading:
                self.card['title'].append(data)
            if data.strip() == 'ALBUM':
                self.card['album'] = True

    def handle_endtag(self, tag):
        if tag == 'h3':
            self.heading = False
        if tag == 'a' and self.card:
            if self.card['album']:
                title = ' '.join(''.join(self.card['title']).split())
                self.cards.append((self.card['href'], title))
            self.card = None
            self.heading = False


def extract(source, html):
    if source.get('adapter') == 'bluenote-artist':
        from html import unescape
        found = {}
        for block in re.findall(r'<div[^>]*class="[^"]*release-entry[^\"]*"(.*?)</h5>', html, re.S):
            heading = re.search(r'<h5[^>]*class="post-name"[^>]*>(.*?)$', block, re.S)
            if not heading:
                continue
            text = ' '.join(unescape(re.sub(r'<[^>]+>', '', heading[1])).split())
            suffix = ' - ' + source['artistName']
            if not text.endswith(suffix):
                continue
            title = text[:-len(suffix)].strip()
            if ' - ' in title:  # Multi-artist/band headings require a separate source.
                continue
            identity = hashlib.sha256((source['artistId'] + '\n' + key(title)).encode()).hexdigest()[:24]
            if title:
                found[identity] = dict(id=identity, artistId=source['artistId'], title=title, sourceUrl=source['url'], sourceId=source['id'], sourceName=source['name'], label=source['label'], status='pending', scope='work')
        return list(found.values())
    parser = WarnerCards() if source.get('adapter') == 'warner-cards' else Links()
    parser.feed(html)
    found = {}
    links = parser.cards if isinstance(parser, WarnerCards) else parser.links
    for href, title in links:
        url = urljoin(source['url'], href).split('#')[0].split('?')[0]
        if not safe_url(url, source['host']) or not re.fullmatch(source['releasePath'], urlsplit(url).path):
            continue
        if not title or len(title) > 240:
            continue
        identity = hashlib.sha256((source['artistId'] + '\n' + url).encode()).hexdigest()[:24]
        found.setdefault(url, dict(id=identity, artistId=source['artistId'], title=title,
                                  sourceUrl=url, sourceId=source['id'], sourceName=source['name'],
                                  label=source['label'], status='pending', scope='work'))
    return list(found.values())


def download(source):
    # Do not follow off-host redirects, even to another HTTPS domain.
    from urllib.request import HTTPRedirectHandler, build_opener
    class Redirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not safe_url(newurl, source['host']):
                raise ValueError('off-host redirect')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    if not safe_url(source['url'], source['host']):
        raise ValueError('invalid source URL')
    with build_opener(Redirects()).open(Request(source['url'], headers={'User-Agent': 'RECORD-discography/1.0'}), timeout=30) as response:
        if 'html' not in response.headers.get('Content-Type', ''):
            raise ValueError('source is not HTML')
        data = response.read(5_000_001)
        if len(data) > 5_000_000:
            raise ValueError('source exceeds size limit')
        return data.decode('utf-8')


def collect(sources, previous, fetch=download):
    report = {'version': 1, 'collectedAt': datetime.now(timezone.utc).isoformat(), 'sources': [], 'candidates': []}
    # Preserve last observations during outages; never overwrite a review or catalog.
    old = previous.get('candidates', [])
    for source in sources:
        if source.get('enabled') is False:
            report['sources'].append(dict(id=source['id'], status='disabled', reason=source['disabledReason']))
            continue
        try:
            html = fetch(source)
            candidates = extract(source, html)
            if not candidates:
                raise ValueError('no releases extracted; source layout may have changed')
            report['candidates'].extend(candidates)
            report['sources'].append(dict(id=source['id'], status='ok', count=len(candidates), sha256=hashlib.sha256(html.encode()).hexdigest()))
        except Exception as error:
            report['candidates'].extend(c for c in old if c['sourceId'] == source['id'])
            report['sources'].append(dict(id=source['id'], status='error', error=str(error)))
    return report


def publish(catalog, report, reviews, sources):
    # Validate entire batch before modifying the caller's catalog.
    import copy
    result = copy.deepcopy(catalog)
    candidates = {c['id']: c for c in report['candidates']}
    source_map = {s['id']: s for s in sources}
    healthy = {s['id']: s for s in report['sources'] if s['status'] == 'ok'}
    artists = {a['id']: a for a in result['artists']}
    seen = set()
    for review in reviews:
        if review['candidateId'] in seen:
            raise ValueError('duplicate review')
        seen.add(review['candidateId'])
        if review['decision'] == 'reject':
            continue
        if review['decision'] != 'approve':
            raise ValueError('invalid decision')
        c = candidates[review['candidateId']]
        s = source_map[c['sourceId']]
        observation = healthy.get(c['sourceId'], {})
        if s.get('enabled') is False or not observation.get('sha256') or review.get('sourceSha256') != observation['sha256'] or review.get('candidateTitle') != c['title']:
            raise ValueError('review is not bound to the current source observation')
        checked = date.fromisoformat(review['checkedAt'])
        if checked > date.today() or not review['reviewer'].strip() or not review['note'].strip():
            raise ValueError('review evidence required')
        if c['sourceId'] not in healthy or c['artistId'] != s['artistId'] or not safe_url(c['sourceUrl'], s['host']) or not (c['sourceUrl'] == s['url'] if s.get('adapter') == 'bluenote-artist' else re.fullmatch(s['releasePath'], urlsplit(c['sourceUrl']).path)):
            raise ValueError('unhealthy or mismatched source')
        label = review['label'].strip()
        if not label or label.casefold() in {'unknown', 'n/a', 'tbd'}:
            raise ValueError('reviewed label required')
        title = review['title'].strip()
        year = review.get('year')
        if not title or (year is not None and not re.fullmatch(r'\d{4}', year)):
            raise ValueError('invalid reviewed title or year')
        artist = artists[c['artistId']]
        if any(key(a['title']) == key(title) for a in artist['albums']):
            continue
        artist['albums'].append(dict(id='official:'+c['id'], title=title, year=year, label=label, official=True, scope='work', sourceUrl=c['sourceUrl'], sourceName=s['name'], checkedAt=review['checkedAt'], reviewNote=review['note'], reviewer=review['reviewer'], sourceSha256=review['sourceSha256'], candidateTitle=c['title']))
    return result


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['collect', 'publish'])
    parser.add_argument('--report', type=Path, default=ROOT/'data/official-candidates.json')
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--catalog', type=Path, default=ROOT/'data/official-catalog.json')
    parser.add_argument('--sources', type=Path, default=ROOT/'data/official-sources.json')
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text())['sources']
    if args.command == 'collect':
        previous = json.loads(args.report.read_text()) if args.report.exists() else {}
        report = collect(sources, previous)
        write_json(args.report, report)
        if any(s['status'] == 'error' for s in report['sources']):
            raise SystemExit('Some sources failed; see report. Published catalog unchanged.')
    else:
        if not args.reviews:
            parser.error('--reviews is required for publish')
        path = args.catalog
        result = publish(json.loads(path.read_text()), json.loads(args.report.read_text()), json.loads(args.reviews.read_text()), sources)
        write_json(path, result)


if __name__ == '__main__':
    main()
