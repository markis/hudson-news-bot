# Design: External Prompt Templates with Jinja2

**Date:** 2026-03-02  
**Status:** Approved  
**Author:** AI Assistant

## Overview

Extract LLM prompts from hardcoded Python strings into external Jinja2 template files. This enables prompt editing without code changes while maintaining dynamic content generation (date variables, article loops, conditional sections).

## Goals

1. Move system and analysis prompts to external template files
2. Maintain all dynamic scripting capabilities (loops, conditionals, variable substitution)
3. Preserve existing behavior and API compatibility
4. Enable easier prompt iteration and version control

## Non-Goals

- Hot-reloading templates during development (can add later if needed)
- Prompt versioning system (can add later if needed)
- Multi-language prompt support

## Architecture

### Directory Structure

```
config/prompts/
├── system.jinja      # System prompt (currently in config.toml lines 4-11)
└── analysis.jinja    # Analysis prompt (currently in aggregator.py lines 143-217)
```

### Component Changes

**1. Dependencies**

Add Jinja2 using `uv`:
```bash
uv add jinja2
```

This will update `pyproject.toml` with `jinja2 = "^3.1.0"` (or latest stable).

**2. Configuration (`src/hudson_news_bot/config/settings.py`)**

Add new property:
```python
@cached_property
def prompts_dir(self) -> Path:
    """Get prompts directory path."""
    # Default to config/prompts relative to project root
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / "config" / "prompts"
```

Keep `system_prompt` property for backward compatibility:
```python
@cached_property
def system_prompt(self) -> str:
    """Get LLM system prompt (loaded from template)."""
    # Will be loaded by NewsAggregator from template
    # Keep this property to avoid breaking Config API
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(self.prompts_dir))
    template = env.get_template("system.jinja")
    return template.render()
```

Update `config/config.toml`:
- Remove `system_prompt` field (lines 3-11)
- Content moves to `config/prompts/system.jinja`

**3. NewsAggregator (`src/hudson_news_bot/news/aggregator.py`)**

**Add imports:**
```python
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from pathlib import Path
```

**Update `__init__` method:**
```python
def __init__(self, config: Config, reddit_client: RedditClient | None = None):
    """Initialize the news aggregator.
    
    Args:
        config: Configuration instance
        reddit_client: Reddit client for getting flair options (optional)
    """
    self.config = config
    self.reddit_client = reddit_client
    self.logger = logging.getLogger(__name__)
    self.flair_mapping: dict[str, str] = {}
    
    # Configure OpenAI client
    api_key = config.llm_api_key
    if not api_key or not api_key.strip():
        raise ValueError(
            "LLM_API_KEY or PERPLEXITY_API_KEY environment variable is required"
        )
    
    self.client = AsyncOpenAI(
        api_key=api_key,
        base_url=config.llm_base_url,
        timeout=config.llm_timeout_seconds,
    )
    
    # Initialize Jinja2 template environment
    try:
        self._jinja_env = Environment(
            loader=FileSystemLoader(config.prompts_dir),
            undefined=StrictUndefined,  # Fail on missing variables
            trim_blocks=True,           # Remove newlines after blocks
            lstrip_blocks=True,         # Remove leading whitespace
        )
        self._system_template = self._jinja_env.get_template("system.jinja")
        self._analysis_template = self._jinja_env.get_template("analysis.jinja")
        self.logger.info(f"Loaded prompt templates from {config.prompts_dir}")
    except TemplateNotFound as e:
        raise ValueError(
            f"Prompt template not found: {e.name}. "
            f"Expected templates in {config.prompts_dir}"
        )
    except Exception as e:
        raise ValueError(f"Failed to load prompt templates: {e}")
```

**Refactor `create_analysis_prompt()` to `render_analysis_prompt()`:**
```python
def render_analysis_prompt(
    self, articles: list[NewsItemDict], flair_options: dict[str, str] | None = None
) -> str:
    """Render the analysis prompt using Jinja2 template.
    
    Args:
        articles: List of scraped article dictionaries
        flair_options: Optional mapping of flair text to template IDs
    
    Returns:
        Rendered prompt string
    
    Raises:
        ValueError: If template rendering fails
    """
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Limit to first 20 articles and truncate content
    limited_articles = []
    for article in articles[:20]:
        limited_articles.append({
            "url": article.get("url", "N/A"),
            "headline": article.get("headline", "N/A"),
            "date": article.get("date", "N/A"),
            "content": (article.get("content") or "N/A")[:500],
        })
    
    context = {
        "today": today,
        "articles": limited_articles,
        "flair_options": flair_options or {},
    }
    
    try:
        return self._analysis_template.render(**context)
    except Exception as e:
        self.logger.error(f"Template rendering failed: {e}")
        self.logger.debug(f"Context keys: {context.keys()}")
        raise ValueError(f"Failed to render analysis prompt: {e}")
```

**Update `aggregate_news()` call:**
Change line 112:
```python
# OLD:
prompt = self.create_analysis_prompt(articles, flair_options)

# NEW:
prompt = self.render_analysis_prompt(articles, flair_options)
```

Update line 119 to use rendered system prompt:
```python
# OLD:
{"role": "system", "content": self.config.system_prompt},

# NEW:
{"role": "system", "content": self._system_template.render()},
```

### Template Design

**`config/prompts/system.jinja`:**
```jinja
You are a news article analyzer. Your task is to:
1. Review the scraped article content provided
2. Identify the newest/most recent articles
3. Extract key information from each article
4. Format the output as valid JSON

Focus on finding local Hudson, Ohio news articles from the last 24-48 hours.
Prioritize articles with clear dates and local relevance.
```

**`config/prompts/analysis.jinja`:**
```jinja
Today is {{ today }}. I've scraped the following articles from Hudson, Ohio news sites.
Please analyze them and identify the NEWEST and most relevant local news articles.

{% for article in articles %}
Article {{ loop.index }}:
URL: {{ article.url }}
Headline: {{ article.headline }}
Date: {{ article.date }}
Content Preview: {{ article.content }}...

{% endfor %}
From these articles, select the most recent and relevant Hudson, Ohio news stories.
{%- if flair_options %}

Available Categories for Classification:
{% for flair_text in flair_options.keys() %}
- {{ flair_text }}
{% endfor %}

For each article, also assign the most appropriate category from the list above.
{%- endif %}

For each selected article, format your response as valid JSON using this EXACT structure:

{
  "news": [
    {
      "headline": "story headline",
      "summary": "brief 2-3 sentence summary of the article",
      "publication_date": "YYYY-MM-DD",
      "link": "https://source.com/article"{% if flair_options %},
      "flair": "category name"{% endif %}
    }
  ]
}

IMPORTANT:
- Only include articles that are clearly about Hudson, Ohio or directly relevant to Hudson residents
- Prioritize the most recent articles (from today or yesterday)
- Ensure dates are in YYYY-MM-DD format
- Write clear, concise summaries that capture the key points
- Output ONLY the JSON data, no explanatory text
- If no relevant articles are found, return an empty array: {"news": []}
{% if flair_options -%}
- Assign the most appropriate flair/category from the provided list
{% endif -%}
```

### Error Handling

**Template Loading Failures:**
- Raise `ValueError` with descriptive message during `__init__`
- Include expected template path in error message
- Fail fast (don't defer to runtime)

**Rendering Failures:**
- Catch Jinja2 `UndefinedError` for missing variables
- Log context keys provided vs expected
- Raise `ValueError` with specific variable name

**Missing Template Directory:**
- Raise clear error if `config/prompts/` doesn't exist
- Include setup instructions in error message

## Testing Strategy

**Unit Tests (add to `tests/test_aggregator.py`):**

1. **Test template loading:**
    - Valid templates load successfully
    - Missing template raises `ValueError`
    - Invalid template syntax raises descriptive error

2. **Test rendering with full context:**
    - All variables provided (articles, flair_options)
    - Output contains expected article data
    - Flair section appears correctly

3. **Test rendering with minimal context:**
    - No flair_options provided
    - Flair section omitted from output
    - No undefined variable errors

4. **Test whitespace handling:**
    - No excessive newlines in output
    - Clean formatting around conditionals

5. **Test article truncation:**
    - >20 articles only uses first 20
    - Content truncated to 500 chars

**Integration Test:**
- Mock `WebsiteScraper` with sample articles
- Verify `aggregate_news()` generates valid prompt
- Verify LLM receives correctly formatted prompt

## Migration Path

### Phase 1: Setup (No Breaking Changes)

1. Add `jinja2` dependency: `uv add jinja2`
2. Create `config/prompts/` directory
3. Create `system.jinja` template file
4. Create `analysis.jinja` template file
5. Run `make test` to verify baseline

### Phase 2: Code Updates

1. Update `Config` class with `prompts_dir` property
2. Update `NewsAggregator.__init__` with Jinja2 initialization
3. Refactor `create_analysis_prompt()` → `render_analysis_prompt()`
4. Update `aggregate_news()` to call new method
5. Add unit tests for template loading and rendering
6. Run `make quality` and `make test`

### Phase 3: Cleanup

1. Remove `system_prompt` from `config/config.toml`
2. Update AGENTS.md if needed (document prompts location)
3. Update README.md with prompt customization section
4. Commit all changes

## Rollback Plan

If issues arise:
1. Revert code changes to `aggregator.py`
2. Restore `system_prompt` to `config.toml`
3. Keep template files (no harm in keeping them)
4. Can retry later with lessons learned

## Open Questions

None - design approved.

## References

- Current system prompt: `config/config.toml` lines 4-11
- Current analysis prompt: `src/hudson_news_bot/news/aggregator.py` lines 143-217
- Jinja2 documentation: https://jinja.palletsprojects.com/
