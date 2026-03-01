# Switch to OpenCode Zen Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Perplexity API with OpenCode Zen for better Hudson-specific article filtering

**Architecture:** Update configuration defaults to use OpenCode Zen API endpoint and Claude Haiku model. Maintain backward compatibility by checking both LLM_API_KEY and PERPLEXITY_API_KEY environment variables. Keep all existing prompt logic and JSON Schema structured output unchanged.

**Tech Stack:** Python 3.12+, AsyncOpenAI client (OpenAI-compatible), OpenCode Zen API

---

## Task 1: Update Configuration Defaults

**Files:**
- Modify: `src/hudson_news_bot/config/settings.py:91-118`
- Modify: `config/config.toml:1-20`

**Step 1: Update DEFAULT_CONFIG in settings.py**

Locate the `DEFAULT_CONFIG` dictionary (lines 91-118) and update the `llm` section:

```python
"llm": {
    "model": "claude-haiku-3-5",
    "max_tokens": 4096,
    "timeout_seconds": 300,
    "base_url": "https://opencode.ai/zen/v1/chat/completions",
},
```

Change from:
- `"model": "sonar-pro"` → `"model": "claude-haiku-3-5"`
- `"base_url": "https://api.perplexity.ai"` → `"base_url": "https://opencode.ai/zen/v1/chat/completions"`

**Step 2: Add llm_api_key property with backward compatibility**

Add new cached property after `perplexity_api_key` (around line 230):

```python
@cached_property
def llm_api_key(self) -> str | None:
    """Get LLM API key from environment (checks both new and old names)."""
    # Check new name first, fall back to old name for backward compatibility
    return os.getenv("LLM_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
```

**Step 3: Update config/config.toml**

Update the `[llm]` section:

```toml
[llm]
model = "claude-haiku-3-5"
base_url = "https://opencode.ai/zen/v1/chat/completions"
max_tokens = 4096
timeout_seconds = 300
```

**Step 4: Verify changes compile**

Run: `uv run python -c "from hudson_news_bot.config.settings import Config; c=Config(); print(c.llm_model, c.llm_base_url)"`
Expected: Output shows `claude-haiku-3-5 https://opencode.ai/zen/v1/chat/completions`

**Step 5: Commit**

```bash
git add src/hudson_news_bot/config/settings.py config/config.toml
git commit -m "feat: switch LLM provider to OpenCode Zen

- Update default model to claude-haiku-3-5
- Update base_url to OpenCode Zen API endpoint
- Add llm_api_key property with backward compatibility"
```

---

## Task 2: Update Aggregator to Use New API Key Property

**Files:**
- Modify: `src/hudson_news_bot/news/aggregator.py:59-69`

**Step 1: Update API key retrieval in NewsAggregator.__init__**

Locate the API key retrieval (lines 59-69) and change from `config.perplexity_api_key` to `config.llm_api_key`:

```python
# Configure OpenAI client for analyzing scraped content
api_key = config.llm_api_key
if not api_key or not api_key.strip():
    raise ValueError(
        "LLM_API_KEY or PERPLEXITY_API_KEY environment variable is required and must not be empty"
    )
```

Update error message from:
- `"PERPLEXITY_API_KEY environment variable is required..."` 
- → `"LLM_API_KEY or PERPLEXITY_API_KEY environment variable is required..."`

**Step 2: Update docstring/comments referencing Perplexity**

Line 1: Change from:
```python
"""News aggregation using website scraping and LLM for article identification."""
```
(Keep as-is - already generic)

Line 40: Update class docstring from:
```python
"""Handles news aggregation using OpenAI-compatible LLM API."""
```
(Keep as-is - already generic)

**Step 3: Update test_connection function**

Locate `test_connection()` function (lines 273-319) and update:

Line 284: Change from:
```python
logger.info("Testing LLM API connection...")
```
(Keep as-is - already generic)

Line 287-290: Update API key check:
```python
# Create OpenAI client
api_key = config.llm_api_key
if not api_key:
    logger.error("❌ LLM_API_KEY or PERPLEXITY_API_KEY not set")
    return False
```

**Step 4: Verify changes compile**

Run: `uv run python -c "from hudson_news_bot.news.aggregator import NewsAggregator"`
Expected: No import errors

**Step 5: Commit**

```bash
git add src/hudson_news_bot/news/aggregator.py
git commit -m "refactor: use llm_api_key property for backward compatibility

- Update API key retrieval to use config.llm_api_key
- Update error messages to mention both env var names"
```

---

## Task 3: Update Environment Documentation

**Files:**
- Modify: `.env.example`

**Step 1: Update .env.example**

Change the Perplexity section to be LLM provider agnostic:

```bash
# LLM API Configuration
# Get your API key from OpenCode Zen: https://opencode.ai/auth
# Supports OpenCode Zen, Perplexity, or any OpenAI-compatible provider
LLM_API_KEY=your_api_key_here

# Legacy environment variable (still supported for backward compatibility)
# PERPLEXITY_API_KEY=your_api_key_here

# Reddit API credentials
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USERNAME=your_username_here
REDDIT_PASSWORD=your_password_here
```

**Step 2: Verify .env.example is valid**

Run: `cat .env.example | grep -E "^(LLM_API_KEY|REDDIT_)" | wc -l`
Expected: Shows at least 5 lines (LLM_API_KEY + 4 Reddit vars)

**Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: update env example for OpenCode Zen

- Change PERPLEXITY_API_KEY to LLM_API_KEY
- Add OpenCode Zen link and instructions
- Note backward compatibility with old env var name"
```

---

## Task 4: Update README Documentation

**Files:**
- Modify: `README.md`

**Step 1: Find and update API key setup section**

Locate the section about API keys (likely in "Setup" or "Configuration") and update references from Perplexity to OpenCode Zen:

Before:
```markdown
- `PERPLEXITY_API_KEY`: Get from [Perplexity](https://www.perplexity.ai/settings/api)
```

After:
```markdown
- `LLM_API_KEY`: Get from [OpenCode Zen](https://opencode.ai/auth) (or use `PERPLEXITY_API_KEY` for backward compatibility)
```

**Step 2: Update any configuration examples**

Find and update any example configurations that mention `sonar-pro` or Perplexity:

```toml
[llm]
model = "claude-haiku-3-5"  # or gpt-5-nano, gemini-3-flash
base_url = "https://opencode.ai/zen/v1/chat/completions"
```

**Step 3: Verify README renders correctly**

Run: `grep -n "LLM_API_KEY\|OpenCode Zen" README.md`
Expected: Shows updated references

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for OpenCode Zen provider

- Change API key references from Perplexity to OpenCode Zen
- Update configuration examples with new model and endpoint
- Note backward compatibility"
```

---

## Task 5: Test API Connection

**Files:**
- Test: Manual testing with `make test-connections`

**Step 1: Set up OpenCode Zen API key**

Create or update `.env` file with your OpenCode Zen API key:

```bash
echo "LLM_API_KEY=your_actual_key_here" >> .env
```

**Step 2: Run connection test**

Run: `make test-connections`
Expected: Output shows "✅ LLM API connection successful"

**Step 3: Test with dry run**

Run: `make run-dry`
Expected: 
- Scrapes news sites successfully
- Sends articles to OpenCode Zen API
- Returns filtered Hudson articles
- Shows debug output with article filtering results

**Step 4: Verify structured output parsing**

Check logs for: "Successfully parsed N news items from structured output"
Expected: No JSON parsing errors, articles have proper structure

**Step 5: Document test results**

Create a test results file for reference:

```bash
make run-dry 2>&1 | tee test-results.txt
```

Review `test-results.txt` to verify:
- No API connection errors
- Articles are being filtered
- JSON Schema parsing works correctly

---

## Task 6: Update AGENTS.md (if needed)

**Files:**
- Read: `AGENTS.md`
- Modify: `AGENTS.md` (if it mentions Perplexity)

**Step 1: Check if AGENTS.md mentions Perplexity**

Run: `grep -i perplexity AGENTS.md`
Expected: May show references to Perplexity API

**Step 2: Update references if found**

If Perplexity is mentioned, update to be provider-agnostic:

Change from:
```markdown
uses Perplexity API (sonar-pro model)
```

To:
```markdown
uses LLM API (OpenCode Zen with claude-haiku-3-5 by default)
```

**Step 3: Verify AGENTS.md is accurate**

Run: `grep -E "LLM|API" AGENTS.md | head -20`
Expected: References are generic and accurate

**Step 4: Commit if changes were made**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md for generic LLM provider"
```

If no changes needed:
```bash
echo "No updates needed to AGENTS.md"
```

---

## Task 7: Run Full Test Suite

**Files:**
- Test: All tests via `make test`

**Step 1: Run all tests**

Run: `make test`
Expected: All tests pass (configuration and existing functionality unchanged)

**Step 2: Run type checking**

Run: `make typecheck`
Expected: No type errors

**Step 3: Run linting**

Run: `make lint`
Expected: No linting errors

**Step 4: Run full quality check**

Run: `make quality`
Expected: All checks pass (lint, typecheck, security)

**Step 5: Document any issues**

If any tests fail, document in a file:
```bash
make test 2>&1 | tee test-failures.txt
```

Expected: Empty file (no failures)

---

## Task 8: Final Integration Test

**Files:**
- Test: Manual end-to-end workflow

**Step 1: Run full workflow in dry-run mode**

Run: `make run-dry`
Expected: Complete workflow executes successfully with debug output

**Step 2: Verify article quality**

Review output and check:
- ✅ Articles are about Hudson, Ohio specifically
- ✅ No regional Summit County news (Akron, Cuyahoga Falls, etc.)
- ✅ Articles have proper headlines, summaries, dates, links
- ✅ Flair assignment works correctly

**Step 3: Compare with previous results (if available)**

If you have previous output from Perplexity, compare:
- Article count
- Article relevance (Hudson-specific vs regional)
- Summary quality

**Step 4: Document comparison**

Create notes:
```bash
echo "Migration complete. Testing shows improved filtering of Summit County regional news." > migration-notes.txt
```

**Step 5: Clean up test artifacts**

```bash
rm -f test-results.txt test-failures.txt migration-notes.txt
```

---

## Task 9: Final Commit and Verification

**Files:**
- All modified files

**Step 1: Review all changes**

Run: `git status`
Expected: Shows all modified files are staged

**Step 2: Review git log**

Run: `git log --oneline -10`
Expected: Shows clear commit history of the migration

**Step 3: Verify .env is not staged**

Run: `git status .env`
Expected: ".env" not staged (should be in .gitignore)

**Step 4: Create final summary commit if needed**

If there are any remaining unstaged changes:
```bash
git add -A
git commit -m "chore: finalize OpenCode Zen migration"
```

**Step 5: Verify working directory is clean**

Run: `git status`
Expected: "nothing to commit, working tree clean"

---

## Testing Checklist

After completing all tasks:

- [ ] `make test-connections` passes with OpenCode Zen API
- [ ] `make run-dry` completes without errors
- [ ] Articles are filtered correctly (Hudson-only, no regional news)
- [ ] JSON Schema parsing works
- [ ] `make test` passes all unit tests
- [ ] `make quality` passes all checks
- [ ] Documentation is updated (README, .env.example)
- [ ] Backward compatibility maintained (old env var still works)

## Rollback Plan

If issues occur:

1. Revert git commits: `git revert HEAD~N` (where N is number of commits)
2. Restore old environment variable: `PERPLEXITY_API_KEY=<key>`
3. Update config/config.toml to use Perplexity settings
4. Run tests to verify rollback: `make test-connections`

## Notes

- The migration is straightforward because AsyncOpenAI client supports any OpenAI-compatible API
- No changes to prompt logic or business logic required
- Backward compatibility ensures smooth transition
- If filtering still isn't precise enough, next step would be prompt engineering (separate task)
