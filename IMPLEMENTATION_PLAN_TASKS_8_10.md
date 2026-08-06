# Implementation Plan: Raphael Tasks #8-10
**Target**: Enhance Raphael with proactive engine, cron scheduler, and skill marketplace  
**Based on**: hermes-agent, Mark-XLVII, OpenJarvis patterns  
**Date**: 2026-08-06

---

## Task #8: Enhanced Proactive Engine

### Current State
- **File**: `orchestrator/proactive.py` (~87 lines)
- **Pattern**: Simple idle timer with single callback
- **Features**: Cooldown-based check-ins, `[PROACTIVE_CHECK]` prefix

### Target Pattern: Mark-XLVII Background Monitor
**Reference**: `d:/lab 3/Mark-XLVII/actions/background_monitor.py`

#### Key Patterns to Adapt
1. **Topic Watching** (lines 50-75)
   - DDG news checking with hash-based change detection
   - Per-topic daily check cadence
   - Blocked category filtering (crypto/finance)

2. **Change Detection** (lines 30-34)
   ```python
   def _title_hash(title: str) -> str:
       return hashlib.md5(title.encode("utf-8", errors="ignore")).hexdigest()[:12]
   ```

3. **Memory Persistence** (lines 40-58)
   - JSON-based monitor storage
   - Lock-protected writes
   - `{topic → {last_check, last_hash, added}}` structure

#### Implementation Steps

**File**: `orchestrator/proactive_engine.py` (new, ~450 lines)

**Class Structure**:
```python
class ProactiveEngine:
    # Existing idle check logic (from proactive.py)
    # NEW: Topic monitoring subsystem
    
    class TopicMonitor:
        """DDG news checking with hash-based change detection."""
        def __init__(self, storage_path: Path)
        def add_topic(topic: str) -> str
        def remove_topic(topic: str) -> str
        def check_all() -> list[str]  # returns [MONITOR_ALERT] strings
        
    class EventWatcher:
        """Time-based reminders and calendar integration."""
        def add_reminder(when: str, message: str)
        def check_due() -> list[str]
```

**Dependencies**:
- `duckduckgo_search` (already in requirements.txt)
- `memory/memory_manager.py` (for persistence)

**Config Additions** (`config.py`):
```python
PROACTIVE_ENABLED = True
PROACTIVE_COOLDOWN_SECONDS = 60
PROACTIVE_MIN_INTERVAL_SECONDS = 120
PROACTIVE_TOPICS_ENABLED = True  # NEW
PROACTIVE_DDG_CHECK_INTERVAL_HOURS = 24  # NEW
```

**Integration Points**:
1. `controller/raphael_controller.py` line ~450 (_poll_vad):
   ```python
   # Existing: self.proactive_engine.check()
   # NEW: self.proactive_engine.check_monitors()  # returns alerts
   ```

2. `orchestrator/core.py` (parse alerts in PROACTIVE_CHECK mode)

**Blocked Categories** (from Mark-XLVII):
```python
_BLOCKED = {
    "bitcoin", "ethereum", "dogecoin", "crypto", "nft", 
    "blockchain", "defi", "kripto", "暗号資産"
}
```

**Estimated LOC**: ~450 lines total
- Topic monitoring: ~180 lines
- Event watching: ~120 lines  
- Integration/tests: ~150 lines

---

## Task #9: Cron Scheduler

### Target Pattern: hermes-agent Cron System
**References**: 
- `d:/lab 3/hermes-agent/cron/scheduler.py` (1735 lines)
- `d:/lab 3/hermes-agent/cron/jobs.py` (1687 lines)
- `d:/lab 3/hermes-agent/cron/executions.py` (234 lines)

### Core Architecture (Simplified for Raphael)

#### File 1: `cron/scheduler.py` (~600 lines)

**Key Patterns to Adapt**:

1. **File Locking** (scheduler.py lines 24-42)
   ```python
   try:
       import fcntl
   except ImportError:
       fcntl = None
       try:
           import msvcrt  # Windows fallback
       except ImportError:
           msvcrt = None
   ```

2. **Tick with Lock** (scheduler.py lines 600-650)
   ```python
   def tick(verbose=True, sync=True):
       lock_dir, lock_file = _get_lock_paths()
       lock_fd = open(lock_file, "w")
       if msvcrt:
           msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
       # ... process due jobs
   ```

3. **Job Execution** (scheduler.py lines 400-550)
   - Workdir handling with ContextVars
   - Script timeout with configurable bounds
   - Background claim/heartbeat for one-shots

**Raphael Adaptations**:
```python
# cron/scheduler.py (Raphael version)
def run_job(job: dict) -> tuple[bool, str, str, str | None]:
    """Execute one cron job.
    
    Returns: (success, output_doc, final_response, error_message)
    """
    # 1. Load job script if present
    # 2. Build prompt with skill loading
    # 3. Call orchestrator.core.process_interaction()
    # 4. Handle delivery (TTS/notification)
```

#### File 2: `cron/jobs.py` (~650 lines)

**Key Patterns**:

1. **Schedule Parsing** (jobs.py lines 100-200)
   ```python
   def parse_schedule(schedule: str) -> dict:
       # "30m" → once in 30 minutes
       # "every 30m" → recurring every 30 minutes
       # "0 9 * * *" → cron expression (requires croniter)
       # "2026-02-03T14:00" → once at timestamp
   ```

2. **Due Job Detection** (jobs.py lines 900-1100)
   ```python
   def get_due_jobs() -> list[dict]:
       with _jobs_lock():
           jobs = load_jobs()
           now = _hermes_now()
           due = []
           for job in jobs:
               next_run = job.get("next_run_at")
               if next_run and datetime.fromisoformat(next_run) <= now:
                   due.append(job)
   ```

3. **Job CRUD with Lock** (jobs.py lines 550-750)
   ```python
   @contextmanager
   def _jobs_lock():
       """Cross-process advisory file locking."""
       with _jobs_file_lock:  # in-process RLock
           lock_fd = open(LOCK_FILE, "a+")
           if msvcrt:
               msvcrt.locking(lock_fd.fileno(), msvcrt.LK_LOCK, 1)
           try:
               yield
           finally:
               msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
   ```

**Raphael Structure**:
```
cron/
├── __init__.py
├── scheduler.py       # tick(), run_job(), file locking
├── jobs.py            # CRUD, schedule parsing, due detection
├── executions.py      # audit ledger (optional, start simple)
└── .jobs.lock         # cross-process lock file
```

**Storage**:
```
_user_settings/cron/
├── jobs.json          # [{id, prompt, schedule, next_run_at, ...}]
├── output/            # {job_id}/{timestamp}.md
│   └── abc123/
│       └── 2026-08-06_14-30-00.md
└── ticker_heartbeat   # liveness signal
```

#### File 3: `cron/executions.py` (~240 lines, optional Phase 2)

**Pattern**: SQLite audit ledger  
**Reference**: hermes-agent/cron/executions.py

**Schema**:
```sql
CREATE TABLE executions (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    status TEXT CHECK(status IN ('claimed','running','completed','failed')),
    claimed_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);
```

**For Raphael MVP**: Skip executions.py, use simple in-memory tracking

---

### Integration with Raphael

**Config Additions** (`config.py`):
```python
# Cron settings
CRON_ENABLED = True
CRON_TICK_INTERVAL = 60  # seconds
CRON_MAX_PARALLEL_JOBS = 2
CRON_SCRIPT_TIMEOUT = 3600  # 1 hour
CRON_JOB_DIR = Path("_user_settings/cron")
```

**Main Integration** (`main.py` or `raphael_app/main.py`):
```python
from cron.scheduler import tick, start_ticker_thread

def start_cron():
    """Start background cron ticker."""
    if config.CRON_ENABLED:
        start_ticker_thread(interval=config.CRON_TICK_INTERVAL)
```

**Ticker Thread**:
```python
# cron/scheduler.py
def start_ticker_thread(interval: int = 60):
    def _ticker_loop():
        while True:
            try:
                tick(verbose=False, sync=True)
                record_ticker_heartbeat(success=True)
            except Exception as e:
                logger.error("Cron tick failed: %s", e)
                record_ticker_error(str(e))
            time.sleep(interval)
    
    thread = threading.Thread(target=_ticker_loop, daemon=True, name="cron-ticker")
    thread.start()
```

**Windows-Specific Notes**:
1. Use `msvcrt.locking()` for file locks (scheduler.py line 28)
2. Use `Path.resolve()` instead of symlink handling
3. Use `subprocess` with `creationflags=CREATE_NO_WINDOW` for scripts

**Estimated LOC**:
- `cron/scheduler.py`: ~600 lines
- `cron/jobs.py`: ~650 lines
- Integration: ~50 lines
- Total: ~1300 lines

---

## Task #10: Skill Marketplace Enhancements

### Current State
**File**: `tools_meta/marketplace.py` (167 lines)

**Existing Features**:
- Export tool to .cap (zip: code.py, metadata.json, test.py)
- Import tool from .cap
- List local marketplace

**Missing**:
- Remote marketplace discovery
- Skill ratings/reviews
- Dependency resolution
- Version management

### Enhancement Plan

#### Phase 1: Enhanced Export/Import (~100 lines)

**Add to `marketplace.py`**:

1. **Dependency Auto-Detection**:
   ```python
   def _extract_dependencies(code: str) -> list[str]:
       """Parse imports from code.py to auto-detect dependencies."""
       imports = re.findall(r'^(?:from|import)\s+([\w.]+)', code, re.MULTILINE)
       # Map to known tool names from registry
   ```

2. **Version Conflict Resolution**:
   ```python
   def import_tool(cap_path: str, force: bool = False) -> str:
       """Enhanced import with version handling."""
       if existing and not force:
           return f"Tool '{name}' exists (v{existing['version']}). Use force=True to replace."
   ```

3. **Skill Metadata Enhancement** (metadata.json):
   ```json
   {
       "name": "weather_checker",
       "version": "1.2.0",
       "description": "...",
       "author": "tool_manager",
       "dependencies": ["http_tool"],
       "min_python": "3.10",
       "platforms": ["win32", "linux"],
       "tags": ["weather", "api"],
       "created": "2026-01-15T10:00:00",
       "updated": "2026-02-20T14:30:00",
       "changelog": [
           {"version": "1.2.0", "date": "2026-02-20", "changes": "Added forecast support"},
           {"version": "1.1.0", "date": "2026-02-01", "changes": "Initial release"}
       ]
   }
   ```

#### Phase 2: Remote Marketplace (~250 lines)

**New File**: `tools_meta/remote_marketplace.py`

**Functions**:
```python
def discover_remote(index_url: str = DEFAULT_INDEX) -> list[dict]:
    """Fetch available skills from remote marketplace."""
    # GET {index_url}/api/skills
    # Returns: [{"name": "...", "version": "...", "download_url": "..."}]

def download_skill(name: str, version: str | None = None) -> Path:
    """Download .cap file from remote marketplace."""
    # GET {MARKETPLACE_URL}/skills/{name}/{version or 'latest'}.cap
    # Save to _user_settings/marketplace/downloads/

def publish_skill(name: str, api_key: str) -> str:
    """Publish local tool to remote marketplace."""
    # 1. Export to .cap
    # 2. POST {MARKETPLACE_URL}/api/publish (with auth)
```

**Config** (add to `config.py`):
```python
MARKETPLACE_REMOTE_ENABLED = False  # Opt-in
MARKETPLACE_INDEX_URL = "https://marketplace.raphael.ai/api"
MARKETPLACE_AUTO_UPDATE = False
```

#### Phase 3: Ratings & Reviews (~150 lines)

**Storage**: `_user_settings/marketplace/reviews.json`

```json
{
    "weather_checker": {
        "rating": 4.5,
        "review_count": 12,
        "user_rating": 5,
        "user_review": "Great for quick weather checks!",
        "reviewed_at": "2026-03-01T10:00:00"
    }
}
```

**Functions**:
```python
def rate_skill(name: str, rating: int, review: str | None = None) -> str:
    """Rate a skill (1-5 stars) with optional text review."""

def get_skill_ratings(name: str) -> dict:
    """Get aggregated ratings for a skill."""
```

**Estimated LOC**:
- Enhanced export/import: ~100 lines
- Remote marketplace: ~250 lines
- Ratings system: ~150 lines
- Total: ~500 lines

---

## Summary: Total Implementation Estimate

| Task | Primary File | Lines | Complexity | References |
|------|-------------|-------|------------|-----------|
| #8 Proactive Engine | `orchestrator/proactive_engine.py` | ~450 | Medium | Mark-XLVII/actions/background_monitor.py |
| #9 Cron Scheduler | `cron/{scheduler,jobs}.py` | ~1300 | High | hermes-agent/cron/*.py |
| #10 Marketplace | `tools_meta/{marketplace,remote}.py` | ~500 | Medium | Existing marketplace.py |
| **Total** | | **~2250** | | |

---

## Key Workspace Patterns to Reuse

### 1. File Locking (Windows-Compatible)
**From**: hermes-agent/cron/jobs.py lines 20-40
```python
try:
    import msvcrt  # Windows
except ImportError:
    msvcrt = None

with open(lock_file, "a+") as fd:
    if msvcrt:
        msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
    try:
        # ... critical section
    finally:
        msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
```

### 2. Change Detection with Hashing
**From**: Mark-XLVII/actions/background_monitor.py lines 30-34
```python
def _title_hash(title: str) -> str:
    return hashlib.md5(title.encode("utf-8", errors="ignore")).hexdigest()[:12]
```

### 3. Atomic File Writes
**From**: hermes-agent/cron/jobs.py lines 350-370
```python
fd, tmp_path = tempfile.mkstemp(dir=str(file.parent), suffix='.tmp')
with os.fdopen(fd, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
    f.flush()
    os.fsync(f.fileno())
atomic_replace(tmp_path, target_file)  # From utils module
```

### 4. Schedule Parsing
**From**: hermes-agent/cron/jobs.py lines 100-220
```python
def parse_schedule(schedule: str) -> dict:
    # "30m" → {"kind": "once", "run_at": <30min from now>}
    # "every 30m" → {"kind": "interval", "minutes": 30}
    # "0 9 * * *" → {"kind": "cron", "expr": "0 9 * * *"}  # requires croniter
```

### 5. Process-Local State Management
**From**: hermes-agent/cron/scheduler.py lines 140-180
```python
_running_job_ids: set = set()
_running_lock = threading.Lock()

def get_running_job_ids() -> frozenset[str]:
    """Thread-safe snapshot of in-flight cron jobs."""
    with _running_lock:
        return frozenset(_running_job_ids)
```

---

## Dependencies to Add

**requirements.txt additions**:
```txt
# Cron scheduler
croniter>=1.3.0  # Cron expression parsing (optional, for "0 9 * * *" syntax)

# Already present (verify):
# duckduckgo_search>=3.8.0  # For proactive topic monitoring
```

---

## Testing Strategy

### Task #8 (Proactive Engine)
```python
# tests/test_proactive_engine.py
def test_topic_monitor_add_blocked():
    """Verify crypto topics are rejected."""
    monitor = TopicMonitor(storage_path=tmp_path)
    result = monitor.add_topic("bitcoin price")
    assert "don't monitor crypto" in result.lower()

def test_change_detection():
    """Verify hash-based change detection."""
    monitor = TopicMonitor(storage_path=tmp_path)
    monitor.add_topic("python news")
    # First check: no alert (first run)
    alerts = monitor.check_all()
    assert len(alerts) == 0
    # Mock new headline: should alert
```

### Task #9 (Cron)
```python
# tests/test_cron_scheduler.py
def test_file_lock_windows():
    """Verify msvcrt file locking works."""
    with _jobs_lock():
        # Try to acquire in another thread → should block
        
def test_schedule_parsing():
    assert parse_schedule("30m")["kind"] == "once"
    assert parse_schedule("every 2h")["kind"] == "interval"
```

### Task #10 (Marketplace)
```python
# tests/test_marketplace.py
def test_dependency_extraction():
    code = "from tools.http_tool import fetch\nimport json"
    deps = _extract_dependencies(code)
    assert "http_tool" in deps
```

---

## Rollout Plan

### Week 1: Task #8 (Proactive Engine)
- Day 1-2: Implement TopicMonitor with DDG integration
- Day 3: Add memory persistence + blocked categories
- Day 4: Integration tests + controller hookup
- Day 5: User testing + refinement

### Week 2: Task #9 (Cron Core)
- Day 1-2: Implement jobs.py (CRUD, schedule parsing)
- Day 3-4: Implement scheduler.py (tick, run_job, file locking)
- Day 5: Integration tests + Windows testing

### Week 3: Task #9 (Cron Polish) + Task #10 Start
- Day 1-2: Cron delivery integration (TTS/notifications)
- Day 3: Marketplace enhanced export/import
- Day 4-5: Remote marketplace discovery

### Week 4: Task #10 (Marketplace Finish)
- Day 1-2: Ratings & reviews system
- Day 3-4: Integration tests
- Day 5: Documentation + user guide

---

## Risk Mitigation

### Windows File Locking
**Risk**: `msvcrt.locking()` behavior differs from fcntl  
**Mitigation**: Extensive testing on Windows 10/11, fallback to in-process lock only

### Cron Job Conflicts
**Risk**: Multiple Raphael instances on same machine  
**Mitigation**: Use machine ID + PID in lock file, heartbeat detection

### DDG Rate Limiting
**Risk**: Too many proactive checks trigger rate limit  
**Mitigation**: 24-hour check interval per topic, max 5 topics default

---

## Future Enhancements (Post-MVP)

1. **Cron UI**: Visual job editor in Raphael UI
2. **Proactive ML**: Learn user patterns for check-in timing
3. **Marketplace Search**: Full-text search across remote skills
4. **Skill Bundles**: Package multiple related skills together
5. **Calendar Integration**: Google Calendar / Outlook sync for reminders

---

## Files Created/Modified Summary

### New Files (9 total)
```
cron/__init__.py
cron/scheduler.py
cron/jobs.py
orchestrator/proactive_engine.py
tools_meta/remote_marketplace.py
tests/test_cron_scheduler.py
tests/test_proactive_engine.py
tests/test_marketplace.py
_user_settings/cron/jobs.json (generated at runtime)
```

### Modified Files (4 total)
```
config.py                           # Add CRON_* and PROACTIVE_* settings
main.py                             # Initialize cron ticker thread
controller/raphael_controller.py    # Hook proactive_engine.check_monitors()
tools_meta/marketplace.py           # Enhanced export/import
```

---

## References from Workspace

1. **hermes-agent/cron/scheduler.py**
   - Lines 24-42: File locking (fcntl + msvcrt)
   - Lines 400-550: Job execution with workdir handling
   - Lines 600-650: Tick loop with cross-process lock

2. **hermes-agent/cron/jobs.py**
   - Lines 100-220: Schedule parsing (interval/cron/once)
   - Lines 550-750: CRUD operations with advisory lock
   - Lines 900-1100: Due job detection with grace window

3. **Mark-XLVII/actions/background_monitor.py**
   - Lines 30-34: Title hashing for change detection
   - Lines 50-75: DDG news checking per topic
   - Lines 40-58: Memory persistence with lock

4. **hermes-agent/cron/executions.py**
   - Entire file: SQLite audit ledger pattern (Phase 2)

---

**End of Implementation Plan**
