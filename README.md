# JAV Expert — MediaMatrix Plugin

> [中文文档](README.zh.md)

[![Tests](https://img.shields.io/github/actions/workflow/status/prettygoods/mediamatrix-jav-expert/test.yml?branch=main&label=tests)](https://github.com/prettygoods/mediamatrix-jav-expert/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/codecov/c/github/prettygoods/mediamatrix-jav-expert/main?label=coverage)](https://codecov.io/gh/prettygoods/mediamatrix-jav-expert)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/github/license/prettygoods/mediamatrix-jav-expert)](LICENSE)
[![MediaMatrix](https://img.shields.io/badge/plugin-MediaMatrix-orange)](https://github.com/aidenplus/MediaMatrix)

A [MediaMatrix](https://github.com/aidenplus/MediaMatrix) plugin for automatic AV metadata scraping. Identifies video codes from filenames and fetches titles, cover art, cast, ratings, and more from JavDB — with optional DMM enrichment for higher-quality artwork.

---

## Features

- **Auto code detection** — extracts codes from filenames; supports hyphenated (`SSIS-001`), unhyphenated (`IPX726`), and FC2 (`FC2-PPV-1234567`) formats. Silently exits on non-AV files, leaving TMDB scraping unaffected.
- **JavDB source** *(required)* — title, original title, cover art, release date, runtime, director, studio, series, genres, cast, and community rating
- **DMM source** *(optional)* — official Japanese title, high-resolution cover, and fanart, merged on top of JavDB results
- **Anti-block measures** — User-Agent rotation, rate limiting, automatic retries, Cloudflare bypass via `curl_cffi`

---

## Network Requirements

| Source | Restriction | Recommendation |
|--------|-------------|----------------|
| JavDB (`javdb.com`) | Blocked in mainland China | Use a proxy or non-mainland IP |
| DMM (`dmm.co.jp`) | Japan IPs only | Requires a Japanese proxy; returns 403 otherwise |

**Recommended setup**: deploy on a server in Hong Kong, Taiwan, or Japan, or configure a global proxy locally.

> DMM is disabled by default (`enabled: false`). Skip DMM configuration if you do not need Japanese-IP access.

---

## Installation

```bash
# Navigate to the MediaMatrix plugins directory
cd <MediaMatrix-root>/plugins

# Clone this plugin
git clone https://github.com/prettygoods/mediamatrix-jav-expert.git jav_expert

# Install dependencies
cd jav_expert && bash install.sh
```

---

## Configuration

Add a `jav_expert` block to MediaMatrix's `config/settings.yaml`:

```yaml
plugins:
  jav_expert:
    sources:
      javdb:
        base_url: "https://javdb.com"
        delay: 2.0        # seconds between requests, minimum 1.5 recommended
        max_retries: 3

      dmm:
        enabled: false    # set to true if you have a Japanese IP
        delay: 3.0
```

All options have defaults. The plugin works out of the box in JavDB-only mode with no configuration required.

---

## Supported Code Formats

| Format | Example | Notes |
|--------|---------|-------|
| Standard | `SSIS-001`, `STARS-500`, `FC2-PPV-1234567` | Preferred |
| With path | `/media/jav/SSIS-001.mkv` | Filename is extracted automatically |
| With tags | `[SSIS-001] Title [1080p].mkv` | Square, round, and angle brackets all supported |
| No hyphen | `IPX726`, `bbsxv.xyz-IPX726` | Auto-expanded to `IPX-726` |
| With suffix | `SSIS-001-C`, `SSIS-001-uncensored-HD` | Trailing noise is stripped |
| Underscore-separated | `SSIS-001_1080p.mkv` | Underscores treated as delimiters |

Regular movies (`Inception 2010.mkv`) and TV episodes (`S01E01.mkv`) are never misidentified.

---

## Data Sources

- **JavDB** — community-maintained AV database with broad coverage, community ratings, and full cast information; the primary data source for this plugin
- **DMM** — Japan's largest adult content platform; provides official Japanese titles and high-resolution artwork as an optional enhancement layer

---

## License

MIT License
