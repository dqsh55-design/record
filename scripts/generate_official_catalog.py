"""Generate an additive catalog from approved official-source policies, without MB."""
import argparse
import copy
from datetime import date, datetime, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urljoin, urlsplit

from official_discography import download, safe_url, write_json

ROOT = Path(__file__).resolve().parents[1]
RULE_VERSION = 'official-source-rule-v1'


def norm(value):
    return re.sub(r'[^\w]', '', unicodedata.normalize('NFKC', value).casefold())


def work_title(value):
    # Edition descriptors are not new works; do not infer a first release year.
    return re.sub(r'[<＜][^>＞]*[>＞]', '', value).strip()


def text(value):
    return ' '.join(unescape(re.sub(r'<[^>]*>', '', value)).split())


def good_label(value):
    return isinstance(value, str) and bool(value.strip()) and norm(value) not in {'unknown', 'na', 'tbd'}


def names(source):
    artist = source['artist']
    return {norm(v) for v in [artist['name'], *artist.get('aliases', [])]}


def past_date(value, today):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return False
    try:
        return date.fromisoformat(value) <= today
    except (ValueError, TypeError):
        return False


def bluenote(source, html, today):
    headings = re.findall(r'<h1\b[^>]*>(.*?)</h1>', html, re.S | re.I)
    if len(headings) != 1 or norm(text(headings[0])) not in names(source):
        raise ValueError('artist heading mismatch')
    accepted, held = [], 0
    for attrs, body in re.findall(r'<div\b([^>]*class="[^"]*\brelease-entry\b[^"]*"[^>]*)>(.*?)</h5>', html, re.S):
        heading = re.search(r'<h5\b[^>]*class="post-name"[^>]*>(.*?)$', body, re.S)
        year = re.search(r'data-released-year="(\d{4})"', attrs)
        if not heading:
            continue
        # One artist link, to the registered artist page, not a guest or a band.
        links = re.findall(r'<a\b[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', heading[1], re.S)
        if len(links) != 1 or norm(text(links[0][1])) not in names(source):
            held += 1
            continue
        if urljoin(source['url'], links[0][0]).rstrip('/') != source['url'].rstrip('/'):
            held += 1
            continue
        artist_suffix = ' - ' + text(links[0][1])
        title = text(heading[1])
        if not title.endswith(artist_suffix) or ' - ' in title[:-len(artist_suffix)]:
            held += 1
            continue
        # Year-only current/future releases cannot prove that release day has passed.
        if not year or int(year[1]) < 1900 or int(year[1]) >= today.year:
            held += 1
            continue
        accepted.append(dict(title=title[:-len(artist_suffix)], url=source['url'], listedReleaseYear=year[1]))
    return accepted, held


class WarnerAlbums(HTMLParser):
    def __init__(self):
        super().__init__()
        self.card = None
        self.field = None
        self.cards = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.card = dict(href=attrs.get('href', ''), title=[], release=[], album=False)
        if self.card:
            if tag == 'h3':
                self.field = 'title'
            elif tag == 'p' and 'releaseInfo' in attrs.get('class', ''):
                self.field = 'release'

    def handle_data(self, data):
        if self.card:
            if self.field:
                self.card[self.field].append(data)
            if data.strip() == 'ALBUM':
                self.card['album'] = True

    def handle_endtag(self, tag):
        if tag in {'h3', 'p'}:
            self.field = None
        if tag == 'a' and self.card:
            self.cards.append(self.card)
            self.card, self.field = None, None


def warner(source, html, today):
    headings = re.findall(r'<p\b[^>]*class="[^"]*artistName[^"]*"[^>]*>(.*?)</p>', html, re.S)
    if not headings or any(norm(text(h)) not in names(source) for h in headings):
        raise ValueError('artist heading mismatch')
    parser = WarnerAlbums()
    parser.feed(html)
    accepted, held = [], 0
    for card in parser.cards:
        if not card['album']:
            continue
        title = ' '.join(''.join(card['title']).split())
        released = re.search(r'(\d{4})\.(\d{2})\.(\d{2})\s*発売', ''.join(card['release']))
        url = urljoin(source['url'], card['href'])
        if not title or not released or not past_date('-'.join(released.groups()), today):
            held += 1
            continue
        if not safe_url(url, source['host']) or not re.fullmatch(source['releasePath'], urlsplit(url).path):
            held += 1
            continue
        accepted.append(dict(title=title, url=url, listedReleaseDate='-'.join(released.groups())))
    return accepted, held


class JsonScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buffer = None
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type', '').casefold() == 'application/ld+json':
            self.buffer = []

    def handle_data(self, data):
        if self.buffer is not None:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.buffer is not None:
            try:
                self.documents.append(json.loads(''.join(self.buffer)))
            except ValueError:
                pass
            self.buffer = None


def typed(node, expected):
    types = node.get('@type', [])
    return any(t.split('/')[-1] == expected for t in (types if isinstance(types, list) else [types]) if isinstance(t, str))


def nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from nodes(item)
    elif isinstance(value, dict):
        yield value
        yield from nodes(value.get('@graph', []))
        for item in value.get('itemListElement', []):
            if isinstance(item, dict):
                yield from nodes(item.get('item', item))


def jsonld(source, html, today):
    parser = JsonScripts()
    parser.feed(html)
    accepted, held = [], 0
    for document in parser.documents:
        for album in nodes(document):
            if not typed(album, 'MusicAlbum'):
                continue
            artist, release = album.get('byArtist'), album.get('albumRelease')
            if isinstance(release, list) and len(release) == 1:
                release = release[0]
            if not isinstance(artist, dict) or norm(str(artist.get('name', ''))) not in names(source) or not isinstance(release, dict) or not typed(release, 'MusicRelease'):
                held += 1
                continue
            label = release.get('recordLabel', {})
            label = label.get('name') if isinstance(label, dict) else None
            title = album.get('name')
            url = release.get('url', album.get('url', source['url']))
            kind = album.get('albumReleaseType', '')
            released = release.get('datePublished')
            if not isinstance(title, str) or not title.strip() or not isinstance(kind, str) or kind.split('/')[-1] != 'AlbumRelease' or not good_label(label) or not past_date(released, today) or not isinstance(url, str) or not safe_url(url, source['host']) or not re.fullmatch(source['releasePath'], urlsplit(url).path):
                held += 1
                continue
            accepted.append(dict(title=title.strip(), url=url, label=label, listedReleaseDate=released))
    return accepted, held


ADAPTERS = {'bluenote-artist-v1': bluenote, 'warner-albums-v1': warner, 'music-album-jsonld-v1': jsonld}


def discover_sources(config, catalog, fetch, report):
    """Discover artists from an approved label index; album proof is still required."""
    sources = copy.deepcopy(config['sources'])
    configured_urls = {s['url'].rstrip('/') for s in sources}
    artists = {norm(a['name']): a for a in catalog['artists']}
    for index in config.get('discovery', []):
        item = dict(id=index['id'], addedSources=0)
        try:
            provider = config['providers'][index['provider']]
            if provider['adapter'] != 'bluenote-artist-v1' or index['host'] not in provider['hosts'] or not safe_url(index['url'], index['host']):
                raise ValueError('unapproved artist index')
            html = fetch(index)
            digest = hashlib.sha256(html.encode()).hexdigest()
            maximum = index['maxNewArtistsPerRun']
            if not isinstance(maximum, int) or not 1 <= maximum <= 10:
                raise ValueError('artist discovery limit must be 1..10')
            found, new_count = set(), 0
            for heading in re.findall(r'<h5\b[^>]*class="post-name"[^>]*>(.*?)</h5>', html, re.S):
                links = re.findall(r'<a\b[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', heading, re.S)
                if len(links) != 1:
                    continue
                url = urljoin(index['url'], links[0][0])
                name = text(links[0][1])
                if not name or len(name) > 160 or not safe_url(url, index['host']) or not re.fullmatch(index['artistPath'], urlsplit(url).path):
                    continue
                if url.rstrip('/') in configured_urls or url in found:
                    continue
                found.add(url)
                existing = artists.get(norm(name))
                if existing and not existing.get('officialDiscovery'):
                    # Existing hand-reviewed artists retain their explicitly configured sources.
                    continue
                if not existing and new_count >= maximum:
                    continue
                identity = {k: existing[k] for k in ['id', 'name', 'aliases']} if existing else dict(id='record:'+index['provider']+':'+urlsplit(url).path.strip('/').split('/')[-1], name=name, aliases=[])
                source = dict(id='discovered:'+index['provider']+':'+urlsplit(url).path.strip('/').split('/')[-1], provider=index['provider'], artist=identity, host=index['host'], url=url, releasePath=re.escape(urlsplit(url).path.rstrip('/'))+'/?', discoveredFrom=dict(url=index['url'], sourceSha256=digest))
                sources.append(source)
                configured_urls.add(url.rstrip('/'))
                item['addedSources'] += 1
                if not existing:
                    new_count += 1
            if not found:
                raise ValueError('no artist links extracted from approved index')
            item.update(status='ok', sourceSha256=digest, newArtistPages=new_count)
        except Exception as error:
            item.update(status='error', error=str(error))
            report['errorCount'] += 1
        report['discovery'].append(item)
    return sources


def generate(catalog, config, fetch=download, today=None):
    today = today or date.today()
    if config.get('version') != 1 or catalog.get('version') != 1:
        raise ValueError('unsupported configuration/catalog version')
    result = copy.deepcopy(catalog)
    report = dict(version=1, generatedAt=datetime.now(timezone.utc).isoformat(), sources=[], discovery=[], added=0, errorCount=0)
    artists = {a['id']: a for a in result['artists']}
    sources = discover_sources(config, result, fetch, report)
    source_ids = [s['id'] for s in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('duplicate source ID')
    for source in sources:
        observation = dict(id=source['id'], added=0)
        if source.get('enabled') is False:
            observation.update(status='disabled', reason=source['disabledReason'])
            report['sources'].append(observation)
            continue
        try:
            provider = config['providers'][source['provider']]
            if source['host'] not in provider['hosts'] or not safe_url(source['url'], source['host']):
                raise ValueError('unapproved source origin')
            rule = provider['adapter']
            adapter = ADAPTERS[rule]
            identity = source['artist']
            if not isinstance(identity.get('id'), str) or not identity['id'].strip() or not isinstance(identity.get('name'), str) or not identity['name'].strip() or not source.get('releasePath'):
                raise ValueError('artist binding required')
            existing = artists.get(identity['id'])
            if not existing and any(norm(a['name']) == norm(identity['name']) for a in artists.values()):
                raise ValueError('artist already registered under another ID')
            if existing and norm(existing['name']) != norm(identity['name']):
                raise ValueError('existing artist identity mismatch')
            html = fetch(source)
            digest = hashlib.sha256(html.encode()).hexdigest()
            extracted, held = adapter(source, html, today)
            if not extracted:
                raise ValueError('no provable released albums; source unchanged')
            artist = existing or dict(id=identity['id'], name=identity['name'], aliases=identity.get('aliases', []), albums=[])
            keys = {norm(work_title(v)) for a in artist['albums'] for v in [a['title'], a.get('candidateTitle', a['title'])]}
            if source.get('discoveredFrom') and not existing:
                artist['officialDiscovery'] = dict(provider=source['provider'], **source['discoveredFrom'])
            entries = []
            for item in extracted:
                title = work_title(item['title'])
                if not title or len(title) > 240:
                    held += 1
                    continue
                label = provider.get('label') or item.get('label')
                if not good_label(label) or (item.get('label') and provider.get('label') and norm(item['label']) != norm(provider['label'])):
                    held += 1
                    continue
                key = norm(title)
                if key in keys:
                    continue
                proof = dict(rule=rule, sourceId=source['id'], provider=source['provider'], artistId=identity['id'], sourceUrl=item['url'], sourceSha256=digest)
                proof.update({k: v for k, v in item.items() if k.startswith('listedRelease')})
                if source.get('discoveredFrom'):
                    proof['discoveredFrom'] = source['discoveredFrom']
                entry_id = hashlib.sha256((identity['id']+'\n'+key).encode()).hexdigest()[:24]
                entries.append(dict(id='generated:'+entry_id, title=title, year=None, label=label, official=True, scope='work', sourceUrl=item['url'], sourceName=provider['name'], checkedAt=today.isoformat(), reviewNote='公式情報源の名義・アルバム区分・発売済み表記を共通ルールで検証。初回発売年と配信先は未確認。', verificationMethod=RULE_VERSION, candidateTitle=item['title'], generationProof=proof))
                keys.add(key)
            # Commit this source only after parsing and validation have completed.
            if entries and not existing:
                result['artists'].append(artist)
                artists[identity['id']] = artist
            artist['albums'].extend(entries)
            observation.update(status='ok', sourceSha256=digest, extracted=len(extracted), held=held, added=len(entries))
            report['added'] += len(entries)
        except Exception as error:
            observation.update(status='error', error=str(error))
            report['errorCount'] += 1
        report['sources'].append(observation)
    return result, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT/'data/official-catalog.json')
    parser.add_argument('--config', type=Path, default=ROOT/'data/official-generation.json')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/official-catalog.generated.json')
    parser.add_argument('--report', type=Path, default=ROOT/'reports/official-generation.json')
    args = parser.parse_args()
    protected = {args.catalog.resolve(), args.config.resolve()}
    if args.output.resolve() in protected or args.report.resolve() in protected or args.output.resolve() == args.report.resolve():
        parser.error('use separate output/report paths; replace the published catalog only in a tested PR')
    catalog, report = generate(json.loads(args.catalog.read_text()), json.loads(args.config.read_text()))
    write_json(args.output, catalog)
    write_json(args.report, report)
    print(json.dumps(dict(added=report['added'], errors=report['errorCount'])))
    if report['errorCount']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
