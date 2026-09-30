# Archive Repos Indexing Package — For Google

Your 6 existing archive repos are PUBLIC and can be indexed to Google quickly, but they need sitemap.xml, robots.txt, and SEO index.html.

I created these files locally for each repo, but push failed with 403: arena-ai-coding-agent[bot] does not have permission for archive repos — only for The-Real-Windy-City-.

## Files created locally (ready to upload)

For each repo in /home/user/cheyenne-archives-* :
- sitemap.xml (454 bytes) — lists Pages URL + GitHub repo URL
- robots.txt (100 bytes) — allows all, points to sitemap
- index.html (SEO with meta description, keywords, og tags, JSON-LD ArchiveOrganization, lists files)

Example sitemap.xml:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://therealwindycity.github.io/cheyenne-archives-2025-2026/</loc><lastmod>2026-09-28</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>
  <url><loc>https://github.com/therealwindycity/cheyenne-archives-2025-2026</loc><lastmod>2026-09-28</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>
</urlset>
```

## How to upload manually (30 sec per repo) — no token needed

For each repo:
1. Go to repo page, e.g. https://github.com/therealwindycity/cheyenne-archives-2025-2026
2. Click Add file → Upload files
3. Drag sitemap.xml, robots.txt, index.html from this package
4. Commit directly to main

Or via GitHub UI: Click Add file → Create new file → Paste content → Commit

## After upload, enable Pages

Repo → Settings → Pages → Source: Deploy from branch → main → / (root) → Save

You get:
- https://therealwindycity.github.io/cheyenne-archives-2025-2026/
- https://therealwindycity.github.io/cheyenne-archives-2023-2024/
- https://therealwindycity.github.io/cheyenne-archives-2022/
- https://therealwindycity.github.io/cheyenne-archives-2018-2021/
- https://therealwindycity.github.io/cheyenne-archives-2014-2017/
- https://therealwindycity.github.io/cheyenne-archives-2008-2013/

## Then force Google to crawl

Go to Google Search Console: https://search.google.com/search-console
- Add property for each Pages URL
- Sitemaps → Submit sitemap.xml
- URL Inspection → Request Indexing

## Main repo The-Real-Windy-City- is now clean

Miller speeches from today's meeting have been taken down per your request — commit 3ae1faf on main and a9407d7 on arena branch — only transcripts archive remains — sitemap.xml + robots.txt + simple index.html for Google indexing.

Main repo is still PRIVATE — to be indexed by Google, you must make it public:
https://github.com/therealwindycity/The-Real-Windy-City-/settings#danger-zone → Change visibility → Make public

