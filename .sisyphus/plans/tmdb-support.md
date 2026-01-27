# Plan: Support TMDB IDs in Stream Route

## TL;DR

> **Quick Summary**: Modify the TMDB metadata provider to support IDs prefixed with `tmdb:` (e.g., `tmdb:12345`) in addition to IMDb IDs (`tt...`).
> 
> **Deliverables**:
> - Updated `metadata/tmdb.py` with dual ID support logic.
> 
> **Estimated Effort**: Short
> **Parallel Execution**: NO - sequential
> **Critical Path**: Update Logic → Verify

---

## Context

### Original Request
The addon currently supports `/stream/movie/tt32642706.json`. The user wants to support `/stream/movie/tmdb:153492.json`.

### Analysis
- **Current Logic**: `metadata/tmdb.py` assumes the ID passed is an IMDb ID and uses the TMDB `/find` endpoint with `external_source=imdb_id`.
- **Problem**: Passing `tmdb:123` to `/find` fails because it's not an IMDb ID.
- **Solution**: Detect `tmdb:` prefix. If present, use the direct `/movie/{id}` or `/tv/{id}` endpoints.

---

## Work Objectives

### Core Objective
Enable the addon to resolve metadata correctly when provided with a TMDB ID.

### Concrete Deliverables
- [x] Modified `metadata/tmdb.py` handling `tmdb:` prefix.

### Definition of Done
- [x] `get_metadata` returns correct `Movie` object for `tmdb:153492`.
- [x] `get_metadata` still returns correct `Movie` object for `tt32642706` (regression test).

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: NO
- **User wants tests**: Manual QA Only (implicit)
- **Framework**: None

### Manual QA Procedure

Since there are no unit tests, verification will be done via a temporary script or REPL.

**Verification Script:**
```python
import asyncio
import httpx
from metadata.tmdb import TMDB
from config import TMDB_KEY

# Mock config if needed or rely on env
async def test():
    async with httpx.AsyncClient() as client:
        tmdb = TMDB(client)
        
        # Test 1: New TMDB ID format
        print("Testing TMDB ID...")
        movie_tmdb = await tmdb.get_metadata("tmdb:153492", "movie")
        print(f"Result: {movie_tmdb.titles[0] if movie_tmdb else 'None'}")
        
        # Test 2: Existing IMDb ID format (Regression)
        print("Testing IMDb ID...")
        movie_imdb = await tmdb.get_metadata("tt32642706", "movie")
        print(f"Result: {movie_imdb.titles[0] if movie_imdb else 'None'}")

if __name__ == "__main__":
    asyncio.run(test())
```

---

## TODOs

- [x] 1. Update `metadata/tmdb.py` to support `tmdb:` prefix

  **What to do**:
  - Modify `get_metadata` method.
  - Check if `id` starts with `tmdb:`.
  - If yes:
    - Extract ID (e.g., `153492`).
    - Call `https://api.themoviedb.org/3/movie/{id}` (or `/tv/{id}` for series).
    - Parse the response directly (structure differs from `/find`).
    - Return `Movie` or `Series` object.
  - If no (IMDb ID):
    - Keep existing `/find` logic.

  **Code Logic Reference**:
  ```python
  if id.startswith("tmdb:"):
      # Handle direct lookup
      full_id = id.split(":")
      tmdb_id = full_id[1]
      # ... fetch and parse
  else:
      # Existing logic
  ```

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`python`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential

  **References**:
  - `metadata/tmdb.py:get_metadata` - Target function to modify.
  - `models/movie.py` - Model structure to populate.
  - `models/series.py` - Model structure to populate.

  **Acceptance Criteria**:
  - [x] Create verification script `verify_tmdb.py` (content provided in Verification Strategy).
  - [x] Run `python3 verify_tmdb.py`.
  - [x] Output shows successful title retrieval for BOTH `tmdb:153492` and `tt32642706`.
  - [x] Delete `verify_tmdb.py` after success.

---

## Success Criteria

### Final Checklist
- [x] `/stream/movie/tmdb:153492.json` resolves correctly (simulated via metadata call).
- [x] Existing IMDb IDs still work.
