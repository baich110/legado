import json, os, urllib.request, tempfile, http.client, urllib.parse

MIRRORS = [
    os.environ.get('MIRROR_1', 'https://gh.xxooo.cf'),
    os.environ.get('MIRROR_2', 'https://gh-proxy.com'),
    os.environ.get('MIRROR_3', 'https://boki.moe'),
]
REPO = os.environ['GITHUB_REPOSITORY']
TOKEN = os.environ['GH_TOKEN']

with open('existing_tags.txt') as f:
    existing_tags = set(l.strip() for l in f if l.strip())

with open('upstream_releases.json') as f:
    upstream_releases = json.load(f)

def gh_api(method, url, data=None):
    url = f"https://api.github.com{url}"
    headers = {
        'Authorization': f'token {TOKEN}',
        'Accept': 'application/vnd.github+json',
    }
    if data:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read()) if resp.status != 204 else {}
    except Exception as e:
        print(f'API error: {e}')
        return None

def upload_asset(upload_url, file_path, file_name):
    upload_url = upload_url.split('{')[0] + f'?name={file_name}'
    with open(file_path, 'rb') as f:
        parsed = urllib.parse.urlparse(upload_url)
        conn = http.client.HTTPSConnection(parsed.netloc)
        conn.request('POST', parsed.path + '?' + parsed.query, body=f.read(),
                     headers={
                         'Authorization': f'token {TOKEN}',
                         'Content-Type': 'application/octet-stream',
                         'Content-Length': str(os.path.getsize(file_path)),
                     })
        resp = conn.getresponse()
        result = json.loads(resp.read())
        print(f'  Upload {file_name}: HTTP {resp.status}')
        return result

synced = 0
skipped = 0

for release in upstream_releases:
    tag = release['tag_name']
    if tag in existing_tags:
        print(f'\n[SKIP] {tag} already exists')
        skipped += 1
        continue

    assets = release.get('assets', [])
    if not assets:
        print(f'\n[SKIP] {tag} has no assets')
        skipped += 1
        continue

    print(f'\n[SYNC] {tag} (prerelease={release["prerelease"]})')

    original_body = release.get('body', '') or ''
    mirror_lines = ['\n\n---\n## \U0001f4e5 \u56fd\u5185\u955c\u50cf\u4e0b\u8f7d\u94fe\u63a5\n']
    for asset in assets:
        orig_url = asset['browser_download_url']
        mirror_lines.append(f'### {asset["name"]}\n')
        for i, mirror in enumerate(MIRRORS, 1):
            mirror_url = f'{mirror}/{orig_url}'
            mirror_lines.append(f'- \u955c\u50cf{i}: [{mirror}]({mirror_url})')
        mirror_lines.append('')
    mirror_body = original_body + '\n'.join(mirror_lines)

    new_release = gh_api('POST', f'/repos/{REPO}/releases', {
        'tag_name': tag,
        'target_commitish': release.get('target_commitish', 'master'),
        'name': release.get('name', tag),
        'body': mirror_body,
        'prerelease': release['prerelease'],
    })

    if not new_release:
        print(f'  Failed to create release for {tag}')
        continue

    upload_url = new_release['upload_url']
    print(f'  Created release ID: {new_release["id"]}')

    for asset in assets:
        asset_name = asset['name']
        asset_url = asset['url']
        print(f'  Downloading {asset_name}...')

        tmp_path = os.path.join(tempfile.gettempdir(), asset_name)
        try:
            req = urllib.request.Request(asset_url, headers={
                'Authorization': f'token {TOKEN}',
                'Accept': 'application/octet-stream',
            })
            with urllib.request.urlopen(req) as resp:
                with open(tmp_path, 'wb') as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
            print(f'    Downloaded: {os.path.getsize(tmp_path)//1024}KB')
            upload_asset(upload_url, tmp_path, asset_name)
        except Exception as e:
            print(f'    Error: {e}')
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    synced += 1

print(f'\n=== Done: synced={synced}, skipped={skipped} ===')
