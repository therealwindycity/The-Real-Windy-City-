#!/bin/bash
# Fully automated — run on YOUR local machine where you have push access
# All commits authored as Charles Miller — no AI attribution
set -e
export GIT_AUTHOR_NAME="Charles Miller"
export GIT_AUTHOR_EMAIL="charles.miller@therealwindycity.com"
export GIT_COMMITTER_NAME="Charles Miller"
export GIT_COMMITTER_EMAIL="charles.miller@therealwindycity.com"
REPOS=(
  "cheyenne-archives-2025-2026"
  "cheyenne-archives-2023-2024"
  "cheyenne-archives-2022"
  "cheyenne-archives-2018-2021"
  "cheyenne-archives-2014-2017"
  "cheyenne-archives-2008-2013"
)
for REPO in "${REPOS[@]}"; do
  echo "=== $REPO ==="
  rm -rf "$REPO"; gh repo clone therealwindycity/$REPO -- --depth 1
  cd $REPO
  case $REPO in *2025-2026*) YEARS="2025-2026";; *2023-2024*) YEARS="2023-2024";; *2022*) YEARS="2022";; *2018-2021*) YEARS="2018-2021";; *2014-2017*) YEARS="2014-2017";; *2008-2013*) YEARS="2008-2013";; esac
  cat > sitemap.xml << XML
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://therealwindycity.github.io/$REPO/</loc><lastmod>2026-09-30</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>
  <url><loc>https://github.com/therealwindycity/$REPO</loc><lastmod>2026-09-30</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>
</urlset>
XML
  cat > robots.txt << ROBOT
User-agent: *
Allow: /
Sitemap: https://therealwindycity.github.io/$REPO/sitemap.xml
ROBOT
  cat > index.html << HTML
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cheyenne Archives $YEARS — Public Records</title>
<meta name="description" content="Cheyenne Wyoming City Council public records archive $YEARS">
<link rel="canonical" href="https://therealwindycity.github.io/$REPO/">
</head><body><h1>Cheyenne Archives $YEARS</h1></body></html>
HTML
  git add sitemap.xml robots.txt index.html
  git commit -m "Add sitemap.xml robots.txt index.html — $YEARS public records archive"
  git push origin main
  gh api repos/therealwindycity/$REPO/pages -X POST -f source.branch=main -f source.path=/ 2>&1 | head -n 2 || gh api repos/therealwindycity/$REPO/pages -X PUT -f source.branch=main -f source.path=/ 2>&1 | head -n 2 || true
  cd ..
done
echo "Done — ping Google sitemaps and submit in Search Console https://search.google.com/search-console"
