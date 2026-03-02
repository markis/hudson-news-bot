# Prompt Externalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract LLM prompts from Python code into external Jinja2 template files for easier editing and version control.

**Architecture:** Move system and analysis prompts to `config/prompts/` directory as Jinja2 templates. Load templates at NewsAggregator initialization, render with dynamic context (dates, articles, flairs) at runtime.

**Tech Stack:** Jinja2 3.1+, Python 3.12+, pytest

---

## Task 1: Add Jinja2 Dependency

**Files:**
- Modify: `pyproject.toml` (via uv command)

**Step 1: Add jinja2 dependency**

Run: `uv add jinja2`

Expected: Adds `jinja2` to `pyproject.toml` dependencies and installs package

**Step 2: Verify installation**

Run: `uv pip list | grep -i jinja`

Expected: Shows `jinja2` version 3.1.x or higher

**Step 3: Commit dependency change**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add jinja2 dependency for prompt templates"
```

---

## Task 2: Create Prompt Template Directory and Files

**Files:**
- Create: `config/prompts/system.jinja`
- Create: `config/prompts/analysis.jinja`

**Step 1: Create prompts directory**

Run: `mkdir -p config/prompts`

Expected: Directory created at project root

**Step 2: Create system.jinja template**

Create file `config/prompts/system.jinja` with content:

```jinja
You are a news article analyzer. Your task is to:
1. Review the scraped article content provided
2. Identify the newest/most recent articles
3. Extract key information from each article
4. Format the output as valid JSON

Focus on finding local Hudson, Ohio news articles from the last 24-48 hours.
Prioritize articles with clear dates and local relevance.
```

**Step 3: Create analysis.jinja template**

Create file `config/prompts/analysis.jinja` with content:

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

**Step 4: Verify template files created**

Run: `ls -la config/prompts/`

Expected: Shows `system.jinja` and `analysis.jinja` files

**Step 5: Commit template files**

```bash
git add config/prompts/
git commit -m "feat: add Jinja2 prompt templates"
```

---

## Task 3: Update Config Class with prompts_dir Property

**Files:**
- Modify: `src/hudson_news_bot/config/settings.py:1-10` (imports)
- Modify: `src/hudson_news_bot/config/settings.py:218-225` (after scraping_cache_hours property)

**Step 1: Add Path import if not present**

At top of `src/hudson_news_bot/config/settings.py`, ensure Path is imported:

```python
from pathlib import Path
```

(Already imported on line 7 based on earlier read)

**Step 2: Add prompts_dir property**

After the `scraping_cache_hours` property (around line 217), add:

```python
@cached_property
def prompts_dir(self) -> Path:
    """Get prompts directory path."""
    # Default to config/prompts relative to project root
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / "config" / "prompts"
```

**Step 3: Run type checking**

Run: `make typecheck`

Expected: No type errors

**Step 4: Commit config changes**

```bash
git add src/hudson_news_bot/config/settings.py
git commit -m "feat: add prompts_dir property to Config"
```

---

## Task 4: Update NewsAggregator Imports

**Files:**
- Modify: `src/hudson_news_bot/news/aggregator.py:1-17` (imports section)

**Step 1: Add Jinja2 imports**

After line 11 (after `from pydantic import BaseModel, Field`), add:

```python
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from pathlib import Path
```

**Step 2: Run type checking**

Run: `make typecheck`

Expected: No type errors

**Step 3: Commit import changes**

```bash
git add src/hudson_news_bot/news/aggregator.py
git commit -m "feat: add Jinja2 imports to aggregator"
```

---

## Task 5: Update NewsAggregator.__init__ with Template Loading

**Files:**
- Modify: `src/hudson_news_bot/news/aggregator.py:46-69` (__init__ method)

**Step 1: Add template loading after OpenAI client setup**

After the `self.client = AsyncOpenAI(...)` block (line 65-69), add:

```python
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

**Step 2: Run type checking**

Run: `make typecheck`

Expected: No type errors

**Step 3: Run linting**

Run: `make lint`

Expected: No linting errors

**Step 4: Commit initialization changes**

```bash
git add src/hudson_news_bot/news/aggregator.py
git commit -m "feat: initialize Jinja2 templates in NewsAggregator"
```

---

## Task 6: Add Template Rendering Method

**Files:**
- Modify: `src/hudson_news_bot/news/aggregator.py:143-217` (replace create_analysis_prompt)

**Step 1: Replace create_analysis_prompt with render_analysis_prompt**

Replace the entire `create_analysis_prompt` method (lines 143-217) with:

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

**Step 2: Run type checking**

Run: `make typecheck`

Expected: No type errors

**Step 3: Run linting**

Run: `make lint`

Expected: No linting errors (may need to add trailing comma in context dict)

**Step 4: Commit rendering method**

```bash
git add src/hudson_news_bot/news/aggregator.py
git commit -m "feat: replace create_analysis_prompt with render_analysis_prompt"
```

---

## Task 7: Update aggregate_news to Use New Methods

**Files:**
- Modify: `src/hudson_news_bot/news/aggregator.py:112` (method call)
- Modify: `src/hudson_news_bot/news/aggregator.py:119` (system prompt)

**Step 1: Update analysis prompt call**

Change line 112 from:
```python
prompt = self.create_analysis_prompt(articles, flair_options)
```

To:
```python
prompt = self.render_analysis_prompt(articles, flair_options)
```

**Step 2: Update system prompt usage**

Change line 119 from:
```python
{"role": "system", "content": self.config.system_prompt},
```

To:
```python
{"role": "system", "content": self._system_template.render()},
```

**Step 3: Run type checking**

Run: `make typecheck`

Expected: No type errors

**Step 4: Commit aggregate_news changes**

```bash
git add src/hudson_news_bot/news/aggregator.py
git commit -m "feat: use template rendering in aggregate_news"
```

---

## Task 8: Write Unit Test for Template Loading

**Files:**
- Modify: `tests/test_aggregator.py` (add test class)

**Step 1: Add test for successful template loading**

Add to `tests/test_aggregator.py`:

```python
class TestTemplateLoading:
    """Test Jinja2 template loading."""

    def test_templates_load_successfully(self) -> None:
        """Test that templates load without errors."""
        config = Config()
        reddit_client = MagicMock()
        
        aggregator = NewsAggregator(config, reddit_client)
        
        assert aggregator._system_template is not None
        assert aggregator._analysis_template is not None

    def test_missing_template_raises_error(self, tmp_path: Path) -> None:
        """Test that missing templates raise ValueError."""
        from unittest.mock import patch
        
        config = Config()
        with patch.object(config, 'prompts_dir', tmp_path):
            with pytest.raises(ValueError, match="Prompt template not found"):
                NewsAggregator(config, None)
```

**Step 2: Add Path import if needed**

At top of test file, ensure:
```python
from pathlib import Path
```

**Step 3: Run the test**

Run: `uv run pytest tests/test_aggregator.py::TestTemplateLoading -v`

Expected: Tests pass

**Step 4: Commit template loading tests**

```bash
git add tests/test_aggregator.py
git commit -m "test: add template loading tests"
```

---

## Task 9: Write Unit Test for Template Rendering

**Files:**
- Modify: `tests/test_aggregator.py` (add test methods)

**Step 1: Add test for rendering with full context**

Add to `TestTemplateLoading` class:

```python
def test_render_analysis_with_flair(self) -> None:
    """Test rendering analysis prompt with flair options."""
    config = Config()
    aggregator = NewsAggregator(config, None)
    
    articles = [
        {
            "url": "https://example.com/article1",
            "headline": "Test Article",
            "date": "2026-03-02",
            "content": "Test content here",
        }
    ]
    flair_options = {"News": "123", "Events": "456"}
    
    result = aggregator.render_analysis_prompt(articles, flair_options)
    
    assert "2026-03-02" in result or "Today is" in result
    assert "Test Article" in result
    assert "Available Categories for Classification:" in result
    assert "News" in result

def test_render_analysis_without_flair(self) -> None:
    """Test rendering analysis prompt without flair options."""
    config = Config()
    aggregator = NewsAggregator(config, None)
    
    articles = [
        {
            "url": "https://example.com/article1",
            "headline": "Test Article",
            "date": "2026-03-02",
            "content": "Test content",
        }
    ]
    
    result = aggregator.render_analysis_prompt(articles, None)
    
    assert "Test Article" in result
    assert "Available Categories for Classification:" not in result
```

**Step 2: Run the tests**

Run: `uv run pytest tests/test_aggregator.py::TestTemplateLoading::test_render_analysis_with_flair -v`

Expected: Test passes

Run: `uv run pytest tests/test_aggregator.py::TestTemplateLoading::test_render_analysis_without_flair -v`

Expected: Test passes

**Step 3: Commit rendering tests**

```bash
git add tests/test_aggregator.py
git commit -m "test: add template rendering tests"
```

---

## Task 10: Write Unit Test for Article Truncation

**Files:**
- Modify: `tests/test_aggregator.py` (add test method)

**Step 1: Add test for article limit**

Add to `TestTemplateLoading` class:

```python
def test_render_limits_to_20_articles(self) -> None:
    """Test that rendering only uses first 20 articles."""
    config = Config()
    aggregator = NewsAggregator(config, None)
    
    # Create 25 articles
    articles = []
    for i in range(25):
        articles.append({
            "url": f"https://example.com/article{i}",
            "headline": f"Article {i}",
            "date": "2026-03-02",
            "content": "Content",
        })
    
    result = aggregator.render_analysis_prompt(articles, None)
    
    # Should contain Article 19 (20th article, 0-indexed)
    assert "Article 19" in result
    # Should NOT contain Article 20 (21st article)
    assert "Article 20" not in result

def test_render_truncates_content(self) -> None:
    """Test that content is truncated to 500 chars."""
    config = Config()
    aggregator = NewsAggregator(config, None)
    
    long_content = "x" * 1000
    articles = [
        {
            "url": "https://example.com/article1",
            "headline": "Test",
            "date": "2026-03-02",
            "content": long_content,
        }
    ]
    
    result = aggregator.render_analysis_prompt(articles, None)
    
    # Content should be truncated
    assert "x" * 500 in result
    assert "x" * 501 not in result
```

**Step 2: Run the tests**

Run: `uv run pytest tests/test_aggregator.py::TestTemplateLoading::test_render_limits_to_20_articles -v`

Expected: Test passes

Run: `uv run pytest tests/test_aggregator.py::TestTemplateLoading::test_render_truncates_content -v`

Expected: Test passes

**Step 3: Commit truncation tests**

```bash
git add tests/test_aggregator.py
git commit -m "test: add article truncation tests"
```

---

## Task 11: Run Full Test Suite

**Files:**
- None (verification step)

**Step 1: Run all tests**

Run: `make test`

Expected: All tests pass

**Step 2: Run type checking**

Run: `make typecheck`

Expected: No type errors

**Step 3: Run linting**

Run: `make lint`

Expected: No linting errors

**Step 4: Run quality checks**

Run: `make quality`

Expected: All checks pass

---

## Task 12: Remove system_prompt from config.toml

**Files:**
- Modify: `config/config.toml:3-11` (remove system_prompt)

**Step 1: Remove system_prompt from config.toml**

Delete lines 3-11 from `config/config.toml` (the entire `system_prompt` field and its value).

The file should now start with:
```toml
[news]
max_articles = 5
# News sites to scrape for Hudson, Ohio news
news_sites = [
  ...
]
```

**Step 2: Verify configuration still loads**

Run: `uv run python -m hudson_news_bot.config.settings --validate`

Expected: Configuration validates successfully

**Step 3: Run tests again**

Run: `make test`

Expected: All tests pass (Config.system_prompt now loads from template)

**Step 4: Commit config cleanup**

```bash
git add config/config.toml
git commit -m "refactor: remove system_prompt from config.toml (now in template)"
```

---

## Task 13: Update Documentation

**Files:**
- Modify: `AGENTS.md` (add prompts section)
- Modify: `README.md` (add prompt customization section)

**Step 1: Add prompts section to AGENTS.md**

In the "Project Architecture" section of `AGENTS.md`, after the `config/` directory description, add:

```markdown
## Prompt Templates

LLM prompts are stored as Jinja2 templates in `config/prompts/`:
- `system.jinja` - System prompt for news analysis
- `analysis.jinja` - User prompt with dynamic article data

Templates support variables, loops, and conditionals:
- `{{ today }}` - Current date
- `{% for article in articles %}` - Iterate over articles
- `{% if flair_options %}` - Conditional flair section

Edit templates directly without code changes. Restart bot to reload.
```

**Step 2: Add prompt customization to README.md**

Find the configuration section in `README.md` and add:

```markdown
### Customizing Prompts

LLM prompts are stored in `config/prompts/` as Jinja2 templates:

- **System Prompt**: `config/prompts/system.jinja`
- **Analysis Prompt**: `config/prompts/analysis.jinja`

Edit these files to customize how the bot analyzes news articles. Changes require restarting the bot.

The analysis prompt supports dynamic variables:
- `{{ today }}` - Current date
- `{{ articles }}` - List of scraped articles
- `{{ flair_options }}` - Available Reddit flairs

Example template syntax:
```jinja
Today is {{ today }}. 
{% for article in articles %}
- {{ article.headline }}
{% endfor %}
```
```

**Step 3: Verify documentation formatting**

Run: `cat AGENTS.md | head -100`

Expected: Shows new prompts section

Run: `cat README.md | grep -A 10 "Customizing Prompts"`

Expected: Shows new customization section

**Step 4: Commit documentation updates**

```bash
git add AGENTS.md README.md
git commit -m "docs: add prompt template documentation"
```

---

## Task 14: Final Verification and Integration Test

**Files:**
- None (verification step)

**Step 1: Run complete test suite**

Run: `make pre-commit`

Expected: All quality checks and tests pass

**Step 2: Test connection**

Run: `make test-connections`

Expected: LLM API connection succeeds

**Step 3: Run dry-run test**

Run: `make run-dry`

Expected: Bot executes without errors, logs show "Loaded prompt templates from..."

**Step 4: Verify prompt rendering in logs**

Check logs from dry-run for prompt content.

Expected: Prompts contain dynamic data (today's date, article info)

**Step 5: Create final commit if any fixes needed**

If any issues found and fixed:
```bash
git add .
git commit -m "fix: final adjustments for prompt externalization"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `jinja2` dependency added to `pyproject.toml`
- [ ] `config/prompts/system.jinja` exists with correct content
- [ ] `config/prompts/analysis.jinja` exists with correct content
- [ ] `Config.prompts_dir` property implemented
- [ ] `NewsAggregator` loads templates in `__init__`
- [ ] `render_analysis_prompt()` replaces `create_analysis_prompt()`
- [ ] `aggregate_news()` uses template rendering
- [ ] All tests pass (`make test`)
- [ ] Type checking passes (`make typecheck`)
- [ ] Linting passes (`make lint`)
- [ ] Documentation updated (AGENTS.md, README.md)
- [ ] Dry-run executes successfully (`make run-dry`)

---

## Success Criteria

1. Bot starts without errors
2. Templates load successfully (logged)
3. Prompts render with dynamic content (dates, articles, flairs)
4. All tests pass
5. No type errors or linting issues
6. Documentation updated
