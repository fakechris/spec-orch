# Parallel Wave Execution for spec-orch

## Goal

Enable spec-orch to execute independent WorkPackets within the same Wave concurrently, using asyncio with configurable concurrency limits, while maintaining fail-fast semantics at wave boundaries.

## Scope

### In scope

- **ParallelConfig**: Configurable max concurrency (default 3, capped at CPU cores)
- **AsyncioWaveExecutor**: Wave-level execution with semaphore-based concurrency control
- **Fail-fast behavior**: First packet failure cancels remaining in wave, aborts execution
- **Process cleanup**: SIGTERM then abort on cancellation (Ctrl-C)
- **Structured JSON logging**: Log aggregation and TUI display support with wave/packet correlation

### Out of scope

- Rate limiting (deferred to v2)
- Partial wave success / best-effort continuation
- Cross-wave parallelism
- Retry logic

## Acceptance Criteria

- [ ] `ParallelConfig` defaults to max 3 concurrency, auto-capped to CPU cores
- [ ] Packets within a wave execute concurrently up to config limit
- [ ] First packet failure cancels remaining in wave via `asyncio.gather` exception
- [ ] Failed wave aborts entire execution (no subsequent waves)
- [ ] Ctrl-C sends SIGTERM to all running `codex exec` processes, then aborts
- [ ] All log messages include `wave_id` and `packet_id` fields
- [ ] Result objects include duration timing for each packet
- [ ] Unit tests cover: concurrency limiting, fail-fast behavior, cancellation

## Constraints

- WorkPackets in same wave are guaranteed independent by ScoperAdapter
- `codex exec` runs as local CLI subprocess (no remote API rate limits)
- Max concurrency capped at `os.cpu_count()`
- Execution uses asyncio with subprocess (I/O-bound workload)

## Interface Contracts

```python
@dataclass
class ParallelConfig:
    max_concurrency: int = 3
    max_concurrency_cap: int = 0  # 0 = auto-detect CPU cores
    
    def effective_limit(self) -> int:
        cap = self.max_concurrency_cap or os.cpu_count() or 4
        return min(self.max_concurrency, cap)

@dataclass
class PacketResult:
    packet_id: str
    wave_id: int
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float

@dataclass
class WaveResult:
    wave_id: int
    packet_results: list[PacketResult]
    all_succeeded: bool
    
    @property
    def failed_packets(self) -> list[PacketResult]:
        return [r for r in self.packet_results if r.exit_code != 0]

@dataclass  
class ExecutionPlanResult:
    wave_results: list[WaveResult]
    total_duration: float
    
    def is_success(self) -> bool:
        return all(w.all_succeeded for w in self.wave_results)

class PacketExecutor(ABC):
    @abstractmethod
    async def execute_packet(
        self,
        packet: WorkPacket,
        wave_id: int,
        cancel_event: asyncio.Event,
    ) -> PacketResult: ...

class WaveExecutor(ABC):
    @abstractmethod
    async def execute_wave(
        self,
        wave: list[WorkPacket],
        wave_id: int,
        config: ParallelConfig,
        cancel_event: asyncio.Event,
    ) -> WaveResult: ...
```

**Cancellation behavior:**
- On Ctrl-C (SIGINT): Set cancel_event, send SIGTERM to all running subprocesses, wait 5s, SIGKILL if needed, abort remaining waves

**Logging format:** Structured JSON with events: `wave_started`, `wave_completed`, `wave_failed`, `packet_started`, `packet_completed`, `packet_failed`, `execution_started`, `execution_completed`, `execution_cancelled`