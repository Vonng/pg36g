# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the source for "PostgreSQL 36 计" (PostgreSQL 36 Stratagems), a Chinese production field guide to PostgreSQL and Pigsty. Its 36 chapters are grouped editorially into application-engineering and operations volumes while retaining flat, stable chapter URLs.

## Technology Stack

- **Static Site Generator**: Hugo Extended 0.168.0 for local theme development; production OINK is pinned in `go.mod`
- **Content Format**: Markdown files in `docs/` directory
- **Language**: Chinese manuscript (zh-CN) with an English landing guide at `/en/`
- **Shell**: OINK Book shell; the home page uses the OINK landing renderer
- **Deployment**: GitHub Pages via GitHub Actions

## Essential Commands

```bash
# Current local theme with hot reload
make dev
# Optional checkout and port override
make dev OINK_LOCAL=/path/to/oink PORT=1314

# Build static site
make build

# Full publication check against the module version locked in go.mod
make check

# Generate Traditional Chinese (zh-tw) version
make translate

# Generate EPUB version
make epub
```

## Project Structure

- `docs/`: Content source files (Markdown)
  - 36 top-level chapter directories, each containing `_index.md` and section pages
  - `_index.md` / `_index.en.md`: Book landing-page resources
  - `toc.md`: Table of contents
  - `preface.md`: Book preface
- `data/home/`: Chinese and English OINK landing-page data
- `config/_default/menus.*.yaml`: Language-specific navbar menus
- `public/`: Generated static site (git-ignored, auto-generated)
- `static/`: Static assets (images, logos)
- `layouts/`: Hugo template overrides
- `assets/scss/`: Project styling layered over OINK
- `bin/`: Utility scripts
- `bin/scaffold_book.rb`: Regenerates the book scaffold
- `bin/check_book_scaffold.rb`: Validates structure, metadata, aliases, and links
- `.github/workflows/pages.yaml`: GitHub Pages deployment workflow

## Content Architecture

The book follows a structured approach with two main volumes:

1. **上卷 (Volume 1)**: Application Development (`/upper-volume/`)
   - Chapters 1-18 covering PostgreSQL fundamentals, development practices, and extensions

2. **下卷 (Volume 2)**: Operations Management (`/lower-volume/`)
   - Chapters 19-36 covering deployment, high availability, maintenance, and troubleshooting

Each chapter directory can contain:
- `_index.md`: Chapter main content
- Supporting images and assets
- Sub-pages with additional content

## Hugo Configuration

- **Config File**: `hugo.yaml`
- **Base URL**: https://pg36g.vonng.com/
- **Theme**: OINK v1.4.0 (pinned as a Go module)
- **Layout contract**: Root resources use `type: book`, `layout: landing`, and cascade `type: book`
- **Navigation**: `目录` contains all 36 chapters; `索引` contains the curated engineering indexes
- **Content Directory**: `docs/`
- **Comments**: Giscus
- **Search**: OINK offline search and command palette

## Development Workflow

1. Content changes should be made in `docs/` directory
2. Test locally with `make dev`; use `make check` before publication
3. Commits to `main` branch trigger automatic deployment to GitHub Pages
4. Hugo uses Git info for last modified dates - ensure proper Git history

## Important Notes

- Keep the full manuscript in Chinese unless a complete translation is explicitly requested; the English resource is an honest guide into the Chinese book
- Do not add `type: docs` to content pages; the root Book cascade supplies the page type
- `make dev` uses the local OINK checkout for theme development; `make check` verifies the exact module version in `go.mod`
- The site uses Hugo's goldmark renderer with extended features (footnotes, tables, task lists)
- Static assets go in `static/` directory and are copied as-is to the build
- The project uses CC BY-NC-SA 4.0 license for content
