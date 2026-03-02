# Design: Switch from Perplexity to OpenCode Zen

**Date:** 2026-03-01  
**Status:** Approved  
**Author:** OpenCode Assistant

## Problem Statement

Perplexity's sonar-pro model is not effectively filtering Hudson, Ohio articles. It frequently includes regional Summit County news (Akron, Cuyahoga Falls, etc.) that isn't specifically about Hudson city.

**Root cause:** Perplexity is a search/research model designed to find and synthesize information. When asked to filter scraped content, it may add external context or interpret regional news as Hudson-relevant.

## Solution

Switch from Perplexity to OpenCode Zen, using a standard LLM optimized for analysis tasks. Standard LLMs are better at pure content analysis - they work only with provided content without adding external context.

## Design

### 1. Architecture

**Current:**
- API: `https://api.perplexity.ai`
- Model: `sonar-pro`
- Client: AsyncOpenAI (OpenAI-compatible)

**New:**
- API: `https://opencode.ai/zen/v1/chat/completions`
- Model: `claude-haiku-3-5` (recommended) or `gpt-5-nano` (free)
- Client: AsyncOpenAI (unchanged - OpenAI-compatible)

**Why this solves the problem:**
- Standard LLMs excel at analyzing provided content without external search
- More deterministic filtering (no external context pollution)
- Better geographic precision for city-level filtering

### 2. Configuration Changes

**File: `src/hudson_news_bot/config/settings.py`**

Update `DEFAULT_CONFIG`:
```python
"llm": {
    "model": "claude-haiku-3-5",
    "max_tokens": 4096,
    "timeout_seconds": 300,
    "base_url": "https://opencode.ai/zen/v1/chat/completions",
}
```

**Environment variable:**
- Change: `PERPLEXITY_API_KEY` → `LLM_API_KEY`
- Update code to check both names for backward compatibility

**File: `config/config.toml`**

Update LLM configuration:
```toml
[llm]
model = "claude-haiku-3-5"
base_url = "https://opencode.ai/zen/v1/chat/completions"
max_tokens = 4096
timeout_seconds = 300
```

### 3. Code Changes

**Modified files:**
1. `src/hudson_news_bot/config/settings.py`
    - Update `DEFAULT_CONFIG` llm section
    - Update `llm_api_key` property to check `LLM_API_KEY` first, then `PERPLEXITY_API_KEY` for backward compatibility

2. `src/hudson_news_bot/news/aggregator.py`
    - Update docstrings/comments referencing Perplexity
    - Change API key retrieval to use `config.llm_api_key`

3. `.env.example`
    - Update from `PERPLEXITY_API_KEY` to `LLM_API_KEY`
    - Add comment about OpenCode Zen

4. `README.md`
    - Update setup instructions
    - Change API key references
    - Update provider links

**What stays unchanged:**
- All prompt logic (system prompt, user prompt generation)
- JSON Schema structured output
- AsyncOpenAI client usage
- Error handling and logging
- Business logic and workflow

### 4. Model Selection

**Recommended models:**

| Model | Cost (per 1M tokens) | Use Case |
|-------|---------------------|----------|
| `claude-haiku-3-5` | $0.80 / $4.00 | Production (recommended) |
| `gpt-5-nano` | Free | Testing / Low volume |
| `gemini-3-flash` | $0.50 / $3.00 | Budget option |

**Default:** `claude-haiku-3-5` - excellent balance of accuracy and cost for content analysis

### 5. Testing Plan

**Steps:**
1. Update `.env` with OpenCode Zen API key
2. Run `make test-connections` - verify API connectivity
3. Run `make run-dry` - test article filtering without posting
4. Compare output - verify Summit County regional news is filtered
5. Run full workflow - ensure no regressions

**Success criteria:**
- API connection test passes
- Articles are properly filtered (Hudson-only, no regional Summit County news)
- JSON Schema structured output works correctly
- No errors in scraping, filtering, or posting workflow

### 6. Rollback Plan

If issues occur:
1. Revert configuration changes
2. Restore `PERPLEXITY_API_KEY` environment variable
3. All code changes are backward compatible with Perplexity

### 7. Documentation Updates

**Files to update:**
- `README.md` - Setup section, API key instructions
- `.env.example` - Environment variable name and instructions
- `AGENTS.md` - Update LLM provider references if mentioned

## Trade-offs

**Pros:**
✅ Better filtering accuracy (no external context pollution)  
✅ More deterministic output  
✅ Likely lower cost (Claude Haiku vs sonar-pro)  
✅ Access to multiple model options through Zen  
✅ Simple migration (OpenAI-compatible API)

**Cons:**
❌ Requires new API key (OpenCode Zen account)  
❌ Different pricing model (pay-as-you-go per token)

## Implementation Notes

- Maintain backward compatibility by checking both `LLM_API_KEY` and `PERPLEXITY_API_KEY`
- No changes to prompt engineering (test first, optimize later if needed)
- AsyncOpenAI client already supports OpenAI-compatible endpoints
- Consider adding model selection as a CLI argument for easy testing

## Future Enhancements

If filtering still isn't precise enough after LLM switch:
1. Add stricter prompt engineering (explicit geographic rules)
2. Implement two-stage filtering (initial + validation pass)
3. Add confidence scoring for article relevance
4. Create test suite with known Hudson vs non-Hudson articles
