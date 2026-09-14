# Transcript data directory

Drop transcripts here as `.md` or `.txt` files, then ingest via:

- `POST /api/ingest` (ingest everything in this directory), or
- `POST /api/ingest/url` with a `{"url": ...}` body, or
- `make ingest` / `make seed`.

Each file may start with optional YAML-style frontmatter:

```markdown
---
title: "My Episode Title"
episode_id: "123"
speaker: "Lenny Rachitsky"
url: "https://..."
---
Transcript body here...
```

> **Important:** the bundled files are clearly-marked `[SAMPLE]` transcripts written
> for demonstration so a fresh clone can run end-to-end without scraping. Replace
> them with real Lenny's Podcast transcripts (fetched from the public transcript
> source or added manually) before treating answers as authoritative. Re-ingestion is
> idempotent (deduplicated by content hash), so you can drop in real files and re-run
> `/api/ingest` safely.
