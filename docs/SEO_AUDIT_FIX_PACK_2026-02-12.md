# SEO Audit Fix Pack Evidence (2026-02-12)

Scope: `PR #95` for bounty `#121`.

## 1) Before/After Evidence

Measured against `upstream/main` vs this branch (`codex/seo-fix-pack-121`).

### Command Set

```bash
# Missing alt attributes
rg -n --pcre2 '<img(?![^>]*\\balt=)[^>]*>' bottube_templates bottube_server.py -S

# Images without loading/fetchpriority
rg -n --pcre2 '<img(?![^>]*(loading=|fetchpriority=))[^>]*>' bottube_templates -S

# target=_blank without rel attr in footer base template
rg -n --pcre2 'target="_blank"(?![^>]*\\brel=)' bottube_templates/base.html -S
```

### Results

- Missing `alt`:
  - Before: `2`
  - After: `0`
- Missing `loading/fetchpriority` in template images:
  - Before: `24`
  - After: `0`
- `target="_blank"` without `rel` in `base.html`:
  - Before: `2`
  - After: `0`

## 2) Metadata / Canonical / Robots / Sitemap Verification

### Metadata + Canonical

Verified in `bottube_templates/base.html`:

- `meta name="description"`
- `meta property="og:*"`
- `meta name="twitter:*"`
- `link rel="canonical"`

### Robots + Sitemap

Verified in `seo_routes.py`:

- `GET /robots.txt`
- `GET /sitemap.xml`

Both routes remain intact and unchanged by this fix pack.

## 3) Inline Script Requirement

Per maintainer request, the new inline image-default script was removed from `bottube_templates/base.html`.

## 4) Additional Notes

- RSS thumbnail `<img>` output in `bottube_server.py` now includes `alt`, `loading`, and `decoding` attributes.
- Core avatar/badge/template images were updated to include lazy/async hints where appropriate.
