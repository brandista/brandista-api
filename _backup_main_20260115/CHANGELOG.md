# main.py Parannukset - 15.1.2026

## Backup

Alkuperäinen tiedosto: `main.py` (10 643 riviä)

---

## Tehdyt muutokset

### 1. Google PageSpeed Insights API -integraatio (Core Web Vitals)

**Uusi funktio:** `analyze_core_web_vitals(url)` (rivit 3171-3309)

**Mittaa oikeat arvot Googlelta:**
- LCP (Largest Contentful Paint): < 2.5s hyvä
- FID (First Input Delay): < 100ms hyvä
- INP (Interaction to Next Paint): < 200ms hyvä
- CLS (Cumulative Layout Shift): < 0.1 hyvä
- TTFB (Time to First Byte): < 800ms hyvä
- FCP (First Contentful Paint): < 1.8s hyvä

**Palauttaa myös:**
- `opportunities[]` - Top 5 parannusehdotusta (ms säästöineen)
- `diagnostics[]` - DOM size, JS execution time yms.
- `overall_score` - Lighthouse performance score (0-100)

**Konfigurointi:**
```bash
# Aseta ympäristömuuttuja
export PAGESPEED_API_KEY="your-api-key"
```

API-avain hankitaan: https://developers.google.com/speed/docs/insights/v5/get-started

**Jos API-avainta ei ole, palautetaan tyhjät arvot (ei estä analyyseja).**

---

### 2. Laajennettu Accessibility-analyysi (WCAG 2.1)

**Päivitetty funktio:** `analyze_ux_elements(html)` (rivit 3858-4119)

**Uudet WCAG 2.1 tarkistukset:**

| WCAG Kriteeri | Taso | Mitä tarkistetaan |
|---------------|------|-------------------|
| 3.1.1 Language | A | `<html lang="">` |
| 1.1.1 Non-text | A | Alt-tekstit kuvissa |
| 2.4.1 Bypass | A | Skip links |
| 4.1.2 Name/Role | A | ARIA-labelit |
| 1.3.1 Info | A | Heading hierarchy, form labels |
| 2.4.4 Link Purpose | A | Ei "click here" linkkejä |
| 2.4.7 Focus Visible | AA | Focus indicators CSS:ssä |
| 2.1.1 Keyboard | A | Tabindex, keyboard handlers |
| 1.4.3 Contrast | AA | Matalan kontrastin värit |
| 1.4.1 Use of Color | A | Pelkän värin käyttö |

**Uudet `accessibility_features` kentät:**
```json
{
  "has_lang": true,
  "lang_value": "fi",
  "images_total": 12,
  "images_with_alt": 10,
  "images_decorative": 1,
  "alt_text_coverage_percent": 91.7,
  "has_skip_links": true,
  "aria_label_count": 8,
  "aria_role_count": 15,
  "has_aria_labels": true,
  "heading_structure": {"h1": 1, "h2": 5, "h3": 12, "h4": 3},
  "has_proper_heading_hierarchy": true,
  "form_inputs_total": 4,
  "form_inputs_labeled": 4,
  "form_label_coverage_percent": 100,
  "links_total": 45,
  "vague_link_count": 2,
  "has_focus_indicators": true,
  "tabindex_elements": 3,
  "positive_tabindex_count": 0,
  "has_keyboard_handlers": true,
  "potential_contrast_issues": false,
  "may_use_color_only": false
}
```

---

### 3. Integraatio pääanalyysiin

**Muokattu:** `_perform_comprehensive_analysis_internal()` (rivi 7191-7193)

- CWV-analyysi kutsutaan automaattisesti
- Tulos lisätään `result["core_web_vitals"]` -kenttään
- `metadata.pagespeed_api_enabled` kertoo onko API käytössä

**Cache-versio päivitetty:** `ai_comprehensive_v6.5.0_cwv_a11y`

---

## Tulosdata (uudet kentät)

```json
{
  "core_web_vitals": {
    "source": "pagespeed_api",
    "overall_score": 72,
    "overall_rating": "needs_improvement",
    "lcp": {"value": 2800, "rating": "needs_improvement", "unit": "ms"},
    "fid": {"value": 45, "rating": "good", "unit": "ms"},
    "cls": {"value": 0.08, "rating": "good", "unit": ""},
    "opportunities": [
      {"id": "render-blocking-resources", "title": "...", "savings_ms": 1200}
    ]
  },
  "ux": {
    "accessibility_score": 78,
    "accessibility_features": {...},
    "accessibility_issues": [...]
  }
}
```

---

## Palautusohje

```bash
cd /Users/tuukka/.claude-worktrees/Projects/thirsty-rosalind

# Palauta alkuperäinen
cp _backup_main_20260115/main.py ./main.py
```

## Tiedostot

- `_backup_main_20260115/main.py` - Alkuperäinen (10 643 riviä)
- `_backup_main_20260115/CHANGELOG.md` - Tämä dokumentti
