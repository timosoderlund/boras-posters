#!/usr/bin/env python3
"""
Borås Poster Project 2026 — Zero-Dependency Static Site Builder
Built by Tord Persson (GitHub & Web Architecture) & Anders Gulliksson (Google Search & Image SEO).

Usage:
    python3 build_site.py
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

SITE_TITLE = "Borås Poster Project 2026"
SITE_SUBTITLE = "Fine Art Photography Posters · Borås, Sweden"
SITE_DESCRIPTION = (
    "Borås Poster Project 2026 — Fine art photography posters from Borås (Boras), "
    "Sweden by Timo T Söderlund. Featuring Viskan, Bodhi, Caroli Kyrka, Pinocchio, and Österlånggatan."
)
BASE_URL = "https://timosoderlund.github.io/boras-posters"
CREATOR_NAME = "Timo T Söderlund"

ROOT_DIR = Path(__file__).resolve().parent
CONTENT_DIR = ROOT_DIR / "content" / "posters"
ASSETS_DIR = ROOT_DIR / "assets" / "posters"
DOCS_DIR = ROOT_DIR / "docs"
DOCS_IMAGES_DIR = DOCS_DIR / "images"
DOCS_POSTERS_DIR = DOCS_DIR / "posters"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IMAGE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.webp$")
MAX_IMAGE_BYTES = 700 * 1024  # 700 KB limit for fast Core Web Vitals


def parse_frontmatter(text: str, filepath: Path) -> tuple[dict[str, str], str]:
    """Parse simple YAML-like frontmatter without external dependencies."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{filepath.name}: Missing opening '---' frontmatter delimiter.")
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        raise ValueError(f"{filepath.name}: Missing closing '---' frontmatter delimiter.")

    meta: dict[str, str] = {}
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"{filepath.name}: Invalid frontmatter line: {line}")
        key, val = stripped.split(":", 1)
        meta[key.strip()] = val.strip().strip('"').strip("'")

    body = "\n".join(lines[end_idx + 1 :]).strip()
    return meta, body


def split_bilingual_body(body: str) -> tuple[str, str]:
    """Extract English and Svenska sections from the Markdown body."""
    en_lines: list[str] = []
    sv_lines: list[str] = []
    current = None
    for line in body.splitlines():
        heading = line.strip().lower()
        if heading == "## english":
            current = "en"
            continue
        if heading == "## svenska":
            current = "sv"
            continue
        if current == "en":
            en_lines.append(line)
        elif current == "sv":
            sv_lines.append(line)
    return "\n".join(en_lines).strip(), "\n".join(sv_lines).strip()


def md_paragraphs_to_html(text: str) -> str:
    """Convert simple Markdown paragraphs and *italics* / **bold** to HTML."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    for p in paragraphs:
        escaped = html.escape(p)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
        out.append(f"<p>{escaped}</p>")
    return "\n".join(out)


def load_and_validate_posters() -> list[dict]:
    """Load all poster Markdown files and run Tord & Anders pre-flight checks."""
    if not CONTENT_DIR.exists():
        raise FileNotFoundError(f"Missing content directory: {CONTENT_DIR}")

    md_files = sorted(CONTENT_DIR.glob("*.md"))
    if not md_files:
        raise RuntimeError(f"No poster Markdown files found in {CONTENT_DIR}")

    posters: list[dict] = []
    seen_slugs: set[str] = set()
    errors: list[str] = []

    for md_path in md_files:
        raw = md_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw, md_path)

        required = ["slug", "title", "subtitle", "image", "year", "order", "alt", "description"]
        for field in required:
            if not meta.get(field):
                errors.append(f"{md_path.name}: Missing required field '{field}'.")

        slug = meta.get("slug", "")
        if slug and not SLUG_RE.match(slug):
            errors.append(f"{md_path.name}: Slug '{slug}' must be lowercase letters, numbers, and hyphens only.")
        if slug in seen_slugs:
            errors.append(f"{md_path.name}: Duplicate slug '{slug}'.")
        seen_slugs.add(slug)

        img_name = meta.get("image", "")
        if img_name and not IMAGE_RE.match(img_name):
            errors.append(f"{md_path.name}: Image '{img_name}' must be lowercase hyphenated .webp.")

        img_path = ASSETS_DIR / img_name
        if not img_path.exists():
            errors.append(f"{md_path.name}: Missing image file '{img_path}'.")
        else:
            size_bytes = img_path.stat().st_size
            if size_bytes > MAX_IMAGE_BYTES:
                errors.append(
                    f"{md_path.name}: Image '{img_name}' is {size_bytes // 1024} KB (limit {MAX_IMAGE_BYTES // 1024} KB)."
                )

        en_text, sv_text = split_bilingual_body(body)
        if not en_text:
            errors.append(f"{md_path.name}: Missing '## English' section.")
        if not sv_text:
            errors.append(f"{md_path.name}: Missing '## Svenska' section.")

        posters.append(
            {
                "slug": slug,
                "title": meta.get("title", ""),
                "subtitle": meta.get("subtitle", ""),
                "image": img_name,
                "year": meta.get("year", "2026"),
                "order": int(meta.get("order", "999")),
                "alt": meta.get("alt", ""),
                "description": meta.get("description", ""),
                "en_html": md_paragraphs_to_html(en_text),
                "sv_html": md_paragraphs_to_html(sv_text),
                "source_image": img_path,
            }
        )

    if errors:
        print("PRE-FLIGHT FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    posters.sort(key=lambda p: (p["order"], p["title"]))
    return posters


def build_css() -> str:
    return """/* Borås Poster Project 2026 — Nordic Gallery Minimalism */
:root {
  --bg: #faf9f6;
  --surface: #ffffff;
  --ink: #181818;
  --muted: #5c5b57;
  --line: #e4e1da;
  --accent: #2b231d;
  --max-w: 1160px;
}

*, *::before, *::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}

a {
  color: inherit;
  text-decoration: none;
}

.site-header {
  border-bottom: 1px solid var(--line);
  padding: 2.5rem 1.5rem 2rem;
  text-align: center;
}

.eyebrow {
  font-size: 0.72rem;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 0.65rem;
}

.site-title {
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(1.9rem, 4vw, 3rem);
  font-weight: 700;
  letter-spacing: 0.06em;
  margin: 0;
}

.site-subtitle {
  margin: 0.6rem auto 0;
  max-width: 620px;
  color: var(--muted);
  font-size: 0.98rem;
}

.container {
  max-width: var(--max-w);
  margin: 0 auto;
  padding: 2.5rem 1.5rem 4rem;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 2.5rem 2rem;
}

.poster-card {
  display: block;
  background: var(--surface);
  border: 1px solid var(--line);
  padding: 1rem;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.poster-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 28px rgba(24, 24, 24, 0.08);
}

.poster-card img {
  display: block;
  width: 100%;
  height: auto;
  aspect-ratio: 3 / 4;
  object-fit: cover;
  background: #ece9e2;
}

.poster-card-meta {
  padding: 0.9rem 0.2rem 0.2rem;
}

.poster-card-title {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.15rem;
  letter-spacing: 0.02em;
}

.poster-card-sub {
  margin: 0.25rem 0 0;
  font-size: 0.85rem;
  color: var(--muted);
}

.breadcrumb {
  font-size: 0.85rem;
  color: var(--muted);
  margin-bottom: 1.8rem;
  letter-spacing: 0.04em;
}

.breadcrumb a:hover {
  text-decoration: underline;
}

.poster-detail {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: 3rem;
  align-items: start;
}

@media (max-width: 820px) {
  .poster-detail {
    grid-template-columns: 1fr;
    gap: 2rem;
  }
}

.poster-frame {
  margin: 0;
  background: var(--surface);
  border: 1px solid var(--line);
  padding: 1.15rem;
  box-shadow: 0 10px 30px rgba(24, 24, 24, 0.06);
}

.poster-frame img {
  display: block;
  width: 100%;
  height: auto;
}

.poster-frame figcaption {
  margin-top: 0.85rem;
  font-size: 0.8rem;
  color: var(--muted);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-align: center;
}

.poster-info h1 {
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(1.8rem, 3vw, 2.4rem);
  margin: 0 0 0.4rem;
}

.poster-location {
  font-size: 0.92rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 1.8rem;
}

.story-block {
  margin-bottom: 1.8rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid var(--line);
}

.story-block:last-of-type {
  border-bottom: none;
}

.lang-label {
  font-size: 0.72rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 0.6rem;
}

.facts {
  font-size: 0.88rem;
  color: var(--muted);
  margin-top: 1.5rem;
  padding-top: 1.2rem;
  border-top: 1px solid var(--line);
}

.site-footer {
  border-top: 1px solid var(--line);
  padding: 2rem 1.5rem;
  text-align: center;
  font-size: 0.82rem;
  color: var(--muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
"""


def build_index_html(posters: list[dict]) -> str:
    first_img = f"{BASE_URL}/images/{posters[0]['image']}"
    canonical = f"{BASE_URL}/"

    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": SITE_TITLE,
        "description": SITE_DESCRIPTION,
        "url": canonical,
        "creator": {"@type": "Person", "name": CREATOR_NAME},
        "about": {
            "@type": "Place",
            "name": "Borås, Sweden",
            "alternateName": "Boras, Sweden",
        },
        "hasPart": [
            {
                "@type": "VisualArtwork",
                "name": p["title"],
                "url": f"{BASE_URL}/posters/{p['slug']}.html",
                "image": f"{BASE_URL}/images/{p['image']}",
                "creator": {"@type": "Person", "name": CREATOR_NAME},
            }
            for p in posters
        ],
    }

    cards_html = []
    for p in posters:
        cards_html.append(
            f"""      <a class="poster-card" href="posters/{html.escape(p['slug'])}.html">
        <img src="images/{html.escape(p['image'])}" alt="{html.escape(p['alt'])}" width="1200" height="1600" loading="lazy">
        <div class="poster-card-meta">
          <h2 class="poster-card-title">{html.escape(p['title'])}</h2>
          <p class="poster-card-sub">{html.escape(p['subtitle'])}</p>
        </div>
      </a>"""
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="google-site-verification" content="1sGtVvRS997PubTEtp1xxuXLRrDvLaDhdALp4ERRA-Q">
  <title>{html.escape(SITE_TITLE)} — Fine Art Posters from Borås, Sweden</title>
  <meta name="description" content="{html.escape(SITE_DESCRIPTION)}">
  <link rel="canonical" href="{html.escape(canonical)}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{html.escape(SITE_TITLE)}">
  <meta property="og:description" content="{html.escape(SITE_DESCRIPTION)}">
  <meta property="og:url" content="{html.escape(canonical)}">
  <meta property="og:image" content="{html.escape(first_img)}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="stylesheet" href="style.css">
  <script type="application/ld+json">
{json.dumps(schema, ensure_ascii=False, indent=2)}
  </script>
</head>
<body>
  <header class="site-header">
    <p class="eyebrow">Sweden · 57°43′N 12°56′E</p>
    <h1 class="site-title">{html.escape(SITE_TITLE)}</h1>
    <p class="site-subtitle">Fine art photography posters from Borås (Boras), Sweden by {html.escape(CREATOR_NAME)}. Fotokonst och affischer från Borås.</p>
  </header>

  <main class="container">
    <section class="gallery-grid" aria-label="Poster Gallery">
{chr(10).join(cards_html)}
    </section>
  </main>

  <footer class="site-footer">
    {html.escape(CREATOR_NAME)} · Borås, Sweden
  </footer>
</body>
</html>
"""


def build_poster_html(poster: dict) -> str:
    page_url = f"{BASE_URL}/posters/{poster['slug']}.html"
    img_url = f"{BASE_URL}/images/{poster['image']}"
    page_title = f"{poster['title']} — Borås, Sweden Poster | {SITE_TITLE}"

    schema = [
        {
            "@context": "https://schema.org",
            "@type": "VisualArtwork",
            "name": f"{poster['title']} — Borås, Sweden",
            "alternateName": f"{poster['title']} — Boras, Sweden Poster",
            "description": poster["description"],
            "url": page_url,
            "image": {
                "@type": "ImageObject",
                "url": img_url,
                "width": 1200,
                "height": 1600,
                "caption": poster["alt"],
            },
            "creator": {"@type": "Person", "name": CREATOR_NAME},
            "dateCreated": str(poster["year"]),
            "artMedium": "Fine Art Photography Poster",
            "artform": "Photography",
            "locationCreated": {
                "@type": "Place",
                "name": "Borås, Sweden",
                "alternateName": "Boras, Sweden",
            },
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": SITE_TITLE,
                    "item": f"{BASE_URL}/",
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": poster["title"],
                    "item": page_url,
                },
            ],
        },
    ]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <meta name="description" content="{html.escape(poster['description'])}">
  <link rel="canonical" href="{html.escape(page_url)}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{html.escape(page_title)}">
  <meta property="og:description" content="{html.escape(poster['description'])}">
  <meta property="og:url" content="{html.escape(page_url)}">
  <meta property="og:image" content="{html.escape(img_url)}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="stylesheet" href="../style.css">
  <script type="application/ld+json">
{json.dumps(schema, ensure_ascii=False, indent=2)}
  </script>
</head>
<body>
  <header class="site-header">
    <p class="eyebrow"><a href="../index.html">{html.escape(SITE_TITLE)}</a></p>
    <p class="site-subtitle">Borås, Sweden · {html.escape(CREATOR_NAME)}</p>
  </header>

  <main class="container">
    <nav class="breadcrumb" aria-label="Breadcrumb">
      <a href="../index.html">← All Borås Posters</a> / {html.escape(poster['title'])}
    </nav>

    <article class="poster-detail">
      <figure class="poster-frame">
        <img src="../images/{html.escape(poster['image'])}" alt="{html.escape(poster['alt'])}" width="1200" height="1600">
        <figcaption>{html.escape(poster['title'])} · {html.escape(poster['subtitle'])}</figcaption>
      </figure>

      <div class="poster-info">
        <h1>{html.escape(poster['title'])}</h1>
        <p class="poster-location">{html.escape(poster['subtitle'])}</p>

        <section class="story-block" lang="en">
          <p class="lang-label">English</p>
          {poster['en_html']}
        </section>

        <section class="story-block" lang="sv">
          <p class="lang-label">Svenska</p>
          {poster['sv_html']}
        </section>

        <p class="facts">
          Photographer &amp; Edition: {html.escape(CREATOR_NAME)} · Borås, Sweden ({html.escape(str(poster['year']))})
        </p>
      </div>
    </article>
  </main>

  <footer class="site-footer">
    {html.escape(CREATOR_NAME)} · Borås, Sweden
  </footer>
</body>
</html>
"""


def build_sitemap(posters: list[dict]) -> str:
    today = date.today().isoformat()
    urls = [
        f"""  <url>
    <loc>{BASE_URL}/</loc>
    <lastmod>{today}</lastmod>
  </url>"""
    ]
    for p in posters:
        page_url = html.escape(f"{BASE_URL}/posters/{p['slug']}.html")
        img_url = html.escape(f"{BASE_URL}/images/{p['image']}")
        img_title = html.escape(f"{p['title']} — Borås, Sweden Poster")
        img_caption = html.escape(p["alt"])
        urls.append(
            f"""  <url>
    <loc>{page_url}</loc>
    <lastmod>{today}</lastmod>
    <image:image>
      <image:loc>{img_url}</image:loc>
      <image:title>{img_title}</image:title>
      <image:caption>{img_caption}</image:caption>
    </image:image>
  </url>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
{chr(10).join(urls)}
</urlset>
"""


def build_robots_txt() -> str:
    return f"""User-agent: *
Allow: /

Sitemap: {BASE_URL}/sitemap.xml
"""


def main() -> None:
    posters = load_and_validate_posters()

    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_POSTERS_DIR.mkdir(parents=True, exist_ok=True)

    # Required for GitHub Pages to serve static files directly without Jekyll
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (DOCS_DIR / "style.css").write_text(build_css(), encoding="utf-8")
    (DOCS_DIR / "index.html").write_text(build_index_html(posters), encoding="utf-8")
    (DOCS_DIR / "sitemap.xml").write_text(build_sitemap(posters), encoding="utf-8")
    (DOCS_DIR / "robots.txt").write_text(build_robots_txt(), encoding="utf-8")

    for p in posters:
        shutil.copy2(p["source_image"], DOCS_IMAGES_DIR / p["image"])
        (DOCS_POSTERS_DIR / f"{p['slug']}.html").write_text(
            build_poster_html(p), encoding="utf-8"
        )

    print(f"PRE-FLIGHT OK: Built {len(posters)} posters into {DOCS_DIR}")
    for p in posters:
        kb = (DOCS_IMAGES_DIR / p["image"]).stat().st_size / 1024
        print(f"  - {p['slug']}.html ({p['image']}, {kb:.1f} KB)")


if __name__ == "__main__":
    main()
