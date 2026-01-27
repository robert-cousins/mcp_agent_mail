# Implementation Plan: Refactor Agent Naming to Program+Model Format

## Overview

**Current System:** Random Adjective+Noun names (e.g., `GreenHorse`, `BlueLake`)
**New System:** Descriptive Program+Model names (e.g., `Claude Code Opus 4.5 #1`, `Cline ChatGPT 5.2 #1`)

**Uniqueness Strategy:** Numeric suffix counter per program+model combination
**Migration Approach:** Rename all existing agents to new format

## Design Decisions

### Name Format
```
{program} {model} #{counter}
```

**Examples:**
- `Claude Code Opus 4.5 #1`
- `Cline ChatGPT 5.2 #1`
- `Cursor Sonnet 3.5 #2`
- `Codex GPT-5 #1`

### Format Rules
- Program and model are separated by space
- Counter starts at #1 (not #0)
- Counter increments for each additional agent with same program+model in a project
- Max length: 128 characters (existing database constraint)
- No validation of "valid" program/model values (accept any string)

## Current Architecture Analysis

### Where Names are Generated/Validated
**Primary Location:** `src/mcp_agent_mail/utils.py` (lines 20-210)
- `ADJECTIVES` - 62 words (colors, weather, descriptive terms)
- `NOUNS` - 69 words (geography, animals, objects)
- `_VALID_AGENT_NAMES` - Pre-computed frozenset (4,278 combinations)
- `generate_agent_name()` - Random selection and concatenation
- `validate_agent_name_format()` - O(1) lookup against valid set
- `sanitize_agent_name()` - Cleanup function (128 char limit, alphanumeric only)

**Enforcement Configuration:** `src/mcp_agent_mail/config.py`
- `AGENT_NAME_ENFORCEMENT_MODE` env var (strict/coerce/always_auto)
- Default: `coerce` (auto-generate if invalid)

### Where Names are Used (as opaque identifiers)

**Good news:** After generation/validation, names are treated as **opaque strings** throughout:

1. **Database Storage** (`models.py`)
   - `Agent.name` - String field, max 128 chars, indexed
   - Foreign keys in: Messages, FileReservations, AgentLinks
   - **No schema-level format constraints**

2. **Tool Parameters** (`app.py`)
   - All 15+ tools accept agent names as string parameters
   - No decomposition or parsing of adjective/noun components
   - Names used for lookups, ownership, authorization

3. **Git Archive** (`storage.py`)
   - Commit messages: `"mail: {sender} -> {recipients}"`
   - Directory paths: `projects/{slug}/agents/{agent_name}/`
   - Names treated as atomic author identities

4. **Authentication** (`http.py`)
   - JWT claims use agent name as identifier
   - No format validation in auth layer

### Where Format is Hardcoded

**Critical dependencies on Adjective+Noun format:**

1. **Validation Logic** (`utils.py:189-210`)
   - Exact match against `_VALID_AGENT_NAMES` frozenset
   - This is the **single source of truth**

2. **Error Messages** (`app.py`)
   - Lines 2484-2577: References to "adjective+noun" format
   - Helper functions detect mistakes (descriptive names, usernames, emails)
   - Error messages suggest examples: "GreenLake", "BlueDog"

3. **Documentation**
   - `CLAUDE.md` - Mentions Adjective+Noun format
   - `README.md` - Explains naming rationale
   - `SKILL.md` - Documents convention
   - Integration scripts - Comments reference auto-generation

4. **Tests** (`tests/test_agent_name_validation.py`)
   - 630 lines testing validation logic
   - Tests for exact word matches, case sensitivity, namespace size
   - **Must be updated for any format change**

## Implementation Steps

### Phase 1: Update Name Generation Logic (`utils.py`)

**File:** `src/mcp_agent_mail/utils.py`

1. **Remove old word lists** (lines 20-172)
   - Delete `ADJECTIVES` and `NOUNS` constants
   - Delete `_VALID_AGENT_NAMES` frozenset

2. **Rewrite `generate_agent_name()`** (lines 182-186)
   ```python
   def generate_agent_name(program: str, model: str, counter: int = 1) -> str:
       """Generate name in format: {program} {model} #{counter}"""
       return f"{program} {model} #{counter}"
   ```

3. **Rewrite `validate_agent_name_format()`** (lines 189-210)
   - Accept any format (no strict validation)
   - Just check non-empty and max length
   - Or use regex to validate `{text} {text} #{number}` pattern

4. **Update `sanitize_agent_name()`** (lines 213-218)
   - Allow spaces (currently removes them?)
   - Allow hashes (#) for counter
   - Keep 128 char truncation

**New helper function needed:**
```python
def find_next_counter(project_id: int, program: str, model: str, session) -> int:
    """Query database to find next available counter for program+model combo"""
    # Query: SELECT MAX(counter) FROM derived_counters WHERE program=X AND model=Y
    # Return max + 1, or 1 if none exist
```

### Phase 2: Update Agent Creation Logic (`app.py`)

**File:** `src/mcp_agent_mail/app.py`

1. **Update `_generate_unique_agent_name()`** (lines 2506-2510)
   - Take `program` and `model` as parameters
   - Query database to find existing agents with same program+model
   - Parse counter from existing names (e.g., "Claude Code Opus 4.5 #2" → 2)
   - Generate name with next counter
   - No more retries loop (counter ensures uniqueness)

2. **Update `_get_or_create_agent()`** (lines 2537-2650)
   - Remove adjective+noun validation
   - Pass program/model to name generator
   - Update error messages to reference new format

3. **Update error detection helpers** (lines 1943-2051)
   - **Delete** `_looks_like_descriptive_name()` - no longer needed!
   - **Delete** `_looks_like_unix_username()` - no longer relevant
   - Keep `_looks_like_program_name()` but update message
   - Keep `_looks_like_model_name()` but update message
   - Update `_detect_agent_name_mistake()` to reference new format

4. **Update `register_agent` tool** (lines 4168-4272)
   - Change parameter: `name: Optional[str]` → remove or make it derived
   - Auto-generate name from program+model when called
   - Update docstring and examples

5. **Update `create_agent_identity` tool** (lines 4333-4406)
   - Change `name_hint` parameter behavior
   - Auto-derive name from program+model
   - Update docstring

6. **Update enforcement mode logic** (lines 2468-2510)
   - `AGENT_NAME_ENFORCEMENT_MODE` may no longer be needed
   - Or repurpose: "auto" = always generate, "custom" = allow user override

### Phase 3: Database Migration

**Create migration script:** `src/mcp_agent_mail/migrations/rename_agents.py`

1. **Query all existing agents:**
   ```sql
   SELECT id, project_id, name, program, model FROM agents;
   ```

2. **For each project, count duplicates:**
   ```python
   # Group by (project_id, program, model)
   # Assign counter: #1, #2, #3, etc.
   ```

3. **Update agent names:**
   ```sql
   UPDATE agents SET name = '{program} {model} #{counter}' WHERE id = ?;
   ```

4. **Considerations:**
   - Handle NULL or empty program/model (fallback to "Unknown Program Unknown Model #1")
   - Preserve case of program/model fields
   - Log all name changes for audit trail

### Phase 4: Git Archive Migration

**File:** `src/mcp_agent_mail/storage.py`

**Challenge:** Git archive directories use agent names as paths:
```
projects/{slug}/agents/{agent_name}/inbox/
```

**Options:**

**Option A: Keep old directories, create symlinks**
- Leave existing `projects/X/agents/GreenHorse/` as-is
- Create new directories with new names
- Add mapping file: `old_name → new_name`

**Option B: Rename directories in Git**
- `git mv projects/X/agents/GreenHorse projects/X/agents/Claude\ Code\ Opus\ 4.5\ #1`
- Requires careful handling of spaces in paths
- Preserves Git history

**Option C: Fresh archive**
- Keep old archive read-only
- Start new archive with new names
- Maintain backward compat for historical lookups

**Recommendation:** Option A (symlinks) - safest, no Git rewrite

### Phase 5: Update Tests

**File:** `tests/test_agent_name_validation.py`

1. **Delete old validation tests** (lines 34-630)
   - Remove word list tests
   - Remove adjective+noun format tests
   - Remove namespace size tests

2. **Add new tests:**
   - Test name generation from program+model
   - Test counter incrementation
   - Test uniqueness per project
   - Test max length handling (128 chars)
   - Test special characters in program/model
   - Test counter parsing from existing names

3. **Update integration tests**
   - Replace fixture names: "GreenLake" → "TestProgram TestModel #1"
   - Update assertions expecting old format

### Phase 6: Update Documentation

**Files to update:**

1. **CLAUDE.md**
   - Line 110: Change "Adjective+Noun format" → "Program+Model format"
   - Update examples

2. **README.md**
   - Lines 2090, 2219-2220: Explain new naming rationale
   - Update example names throughout

3. **SKILL.md**
   - Lines 18, 44: Update naming convention docs

4. **Integration scripts** (`scripts/integrate_*.sh`)
   - Update comments about name auto-generation
   - Examples now show program+model derivation

5. **templates/base.html**
   - Line 1420: Update UI text about agent names

## Estimated Effort

### Breakdown
- **Phase 1** (utils.py): 2 hours
- **Phase 2** (app.py logic): 4 hours
- **Phase 3** (DB migration): 3 hours
- **Phase 4** (Git archive): 2 hours
- **Phase 5** (tests): 4 hours
- **Phase 6** (docs): 2 hours

**Total: ~17 hours**

### Complexity Assessment

**HIGH COMPLEXITY** due to:
- Database migration with counter assignment
- Git archive directory renaming
- Extensive test suite rewrite
- Many documentation updates
- Backward compatibility considerations

**Risk Level: MEDIUM**
- Data migration required (agents table)
- File system changes (archive directories)
- Extensive validation logic changes

## Critical Files to Modify

### Must Change
1. **`src/mcp_agent_mail/utils.py`** (~200 lines)
   - Delete ADJECTIVES/NOUNS word lists (lines 20-172)
   - Rewrite `generate_agent_name()` (lines 182-186)
   - Rewrite `validate_agent_name_format()` (lines 189-210)
   - Update `sanitize_agent_name()` (lines 213-218)
   - Add `find_next_counter()` helper

2. **`src/mcp_agent_mail/app.py`** (~400 lines affected)
   - Update `_generate_unique_agent_name()` (lines 2506-2510)
   - Update `_get_or_create_agent()` (lines 2537-2650)
   - Delete/update error helpers (lines 1943-2051)
   - Update `register_agent` tool (lines 4168-4272)
   - Update `create_agent_identity` tool (lines 4333-4406)
   - Update all error messages referencing old format

3. **`tests/test_agent_name_validation.py`** (630 lines → complete rewrite)
   - Delete old validation tests
   - Add counter logic tests
   - Add uniqueness tests
   - Update integration tests

4. **Create new migration:**
   - `src/mcp_agent_mail/migrations/rename_agents.py`

### Should Update
5. **Documentation** (~50 changes)
   - `CLAUDE.md` - Update naming section
   - `README.md` - Update examples and rationale
   - `SKILL.md` - Update convention docs
   - `scripts/integrate_*.sh` - Update comments

6. **Templates**
   - `src/mcp_agent_mail/templates/base.html` (line 1420)

### No Changes Needed
- `models.py` - Schema already supports any string format
- `storage.py` - Treats names as opaque strings
- `http.py` - No format assumptions
- `config.py` - Enforcement mode may be deprecated

## Verification Plan

### After Implementation

1. **Run linting and type checking:**
   ```bash
   make lint
   make typecheck
   ```

2. **Run test suite:**
   ```bash
   uv run pytest tests/test_agent_name_validation.py -v
   uv run pytest tests/ -v
   ```

3. **Test migration script:**
   ```bash
   # Create test database with old names
   python -m mcp_agent_mail.migrations.rename_agents --dry-run
   python -m mcp_agent_mail.migrations.rename_agents
   ```

4. **Manual verification:**
   ```bash
   # Start server
   make serve-http

   # Register new agent and verify name format
   # Use MCP tools to test:
   # - register_agent(program="Claude Code", model="Opus 4.5")
   # - Expected name: "Claude Code Opus 4.5 #1"
   # - Register second agent with same program+model
   # - Expected name: "Claude Code Opus 4.5 #2"
   ```

5. **Check Git archive:**
   ```bash
   # Verify agent directories use new names
   ls -la .archive/projects/*/agents/
   ```

## Risks & Mitigation

### Risk 1: Long Names Exceed 128 Chars
**Scenario:** `Very Long Program Name With Lots Of Words Model Name With Version Numbers #123`
**Mitigation:** Truncate program+model to fit within limit, or raise validation error

### Risk 2: Special Characters in Program/Model
**Scenario:** Program name contains slashes, quotes, or other problematic chars
**Mitigation:** `sanitize_agent_name()` already strips non-alphanumeric; may need to preserve spaces and hashes

### Risk 3: Git Archive Directory Spaces
**Scenario:** Directory names like `projects/X/agents/Claude Code Opus 4.5 #1/` break shell scripts
**Mitigation:** Test all Git operations with properly quoted paths; consider Option A (symlinks)

### Risk 4: Migration Conflicts
**Scenario:** Two agents in same project have identical program+model
**Mitigation:** Counter assignment handles this; agent1 gets #1, agent2 gets #2

### Risk 5: Empty Program/Model Fields
**Scenario:** Existing agents have NULL or empty program/model
**Mitigation:** Fallback to "Unknown Program Unknown Model #{counter}"

## Rollback Strategy

If issues arise post-deployment:

1. **Revert code changes:**
   ```bash
   git revert <commit-hash>
   ```

2. **Restore database:**
   ```bash
   # Backup before migration:
   cp data.db data.db.backup

   # Restore if needed:
   cp data.db.backup data.db
   ```

3. **Revert Git archive:**
   - If using symlinks: delete new symlinks
   - If using git mv: `git revert` archive commits

## Open Questions

1. Should we allow user-provided names that don't match program+model?
   - Current plan: No, always derive from program+model
   - Alternative: Allow override with `custom_name` parameter

2. Should counter be stored in database or parsed from name?
   - Current plan: Parse from name (no schema change)
   - Alternative: Add `counter` column to agents table

3. What if program or model contains "#" character?
   - Current plan: Sanitize or reject
   - Alternative: Use different separator (e.g., " [1]", " v1")

4. Should we preserve old names in archive for historical queries?
   - Current plan: Use symlinks (Option A)
   - Alternative: Maintain alias mapping table
