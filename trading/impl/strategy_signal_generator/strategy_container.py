from typing import Callable

from trading.base.strategy_params import StrategyParams

from ...base.strategy import Strategy, StrategySignalGenerator
from ...events import BarBundleEvent, Event, StrategyBundleEvent, SignalEvent, TickEvent


def _bar_freq_to_minutes(bar_freq: str) -> int:
    """Convert a bar_freq string to its minute equivalent.

    "1d" → 390  (6.5-hour trading day)
    "Xm" → X    (e.g. "5m" → 5)
    """
    if bar_freq == "1d":
        return 390
    return int(bar_freq.rstrip("m"))


def _aggregate_bars(bars: list[TickEvent], steps: int) -> list[TickEvent]:
    """Aggregate fine-grained bars into coarser bars by grouping into chunks of `steps`.

    Partial leading group is discarded. Returns up to len(bars)//steps bars.

    Time: O(n)  Space: O(n/steps)
    """
    n_full = len(bars) // steps
    if n_full == 0:
        return []
    offset = len(bars) - n_full * steps
    result = []
    for i in range(n_full):
        start = offset + i * steps
        end   = start + steps
        group = bars[start:end]
        result.append(TickEvent(
            symbol=group[0].symbol,
            timestamp=group[-1].timestamp,
            open=group[0].open,
            high=max(b.high for b in group),
            low=min(b.low for b in group),
            close=group[-1].close,
            volume=sum(b.volume for b in group),
            is_synthetic=all(b.is_synthetic for b in group),
            is_delisted=group[-1].is_delisted,
        ))
    return result


class StrategyContainer(StrategySignalGenerator):
    """
    Holds multiple strategies, dispatches BarBundleEvents to each via calculate_signals,
    then aggregates their results into a single weighted StrategyBundleEvent.

    Each strategy's contribution is proportional to its nominal.  Signals are
    carried forward from the last bar on which a strategy fired, so a strategy
    that returns None this bar still contributes its previous target weights.
    One combined StrategyBundleEvent is emitted per bar whenever at least one
    strategy has fired at least once.

    Important: a strategy that has *never* fired (e.g. still warming up) has an
    empty carry-forward and therefore contributes zero signal, but its nominal is
    still included in total_nominal.  This means it dilutes all other strategies'
    effective weight until it fires for the first time.  Register strategies only
    when they are ready to produce signals, or accept this warm-up dilution.
    """

    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        super().__init__(get_bars=get_bars)
        self._emit_fn    = emit
        self._strategies: list[tuple[Strategy, float]] = []   # (strategy, nominal)
        self._carried:    list[dict[str, float]]        = []   # parallel; symbol → last signal
        self._ids:        list[str]                     = []   # parallel; strategy id
        self._bar_count: int        = 0
        self._steps:     list[int]  = []
        self._is_eod_gated: list[bool] = []

    @property
    def symbols(self) -> list[str]:
        """Union of symbols across all contained strategies (order-preserving, deduplicated)."""
        seen: set[str] = set()
        result: list[str] = []
        for strategy, _ in self._strategies:
            for sym in getattr(strategy, "symbols", []):
                if sym not in seen:
                    seen.add(sym)
                    result.append(sym)
        return result

    @property
    def required_freq(self) -> str:
        """The finest bar_freq declared across all registered strategies.

        Mixed daily+intraday containers return the finest intraday freq; daily
        strategies in such containers are dispatched via the EOD gate instead.
        Returns "1d" when no strategies are registered.
        """
        if not self._strategies:
            return "1d"
        freqs = [s.strategy_params.bar_freq for s, _ in self._strategies]
        intraday = [f for f in freqs if f != "1d"]
        if not intraday:
            return "1d"
        minutes = [_bar_freq_to_minutes(f) for f in intraday]
        return f"{min(minutes)}m"

    def _recompute_steps(self) -> None:
        """Recompute the per-strategy bar step counts and EOD-gate flags based on required_freq.

        For mixed daily+intraday containers:
        - _steps[i] for a daily strategy is computed as 390 // req_minutes (used by
          _make_freq_adapter for get_bars aggregation — do NOT zero it out).
        - _is_eod_gated[i] = True for daily strategies; dispatch is controlled by the
          is_end_of_day flag on BarBundleEvent rather than the step count.
        For all-daily or all-intraday containers, _is_eod_gated is all-False and the
        step count alone controls dispatch.
        """
        if not self._strategies:
            self._steps = []
            self._is_eod_gated = []
            return
        req_freq = self.required_freq
        if req_freq == "1d":
            self._steps = [1] * len(self._strategies)
            self._is_eod_gated = [False] * len(self._strategies)
            return
        req_minutes = _bar_freq_to_minutes(req_freq)
        self._steps = [
            _bar_freq_to_minutes(s.strategy_params.bar_freq) // req_minutes
            for s, _ in self._strategies
        ]
        self._is_eod_gated = [
            s.strategy_params.bar_freq == "1d"
            for s, _ in self._strategies
        ]

    def _make_freq_adapter(
        self,
        idx: int,
        get_bars_fn: Callable[[str, int], list[TickEvent]],
    ) -> Callable[[str, int], list[TickEvent]]:
        """Wrap get_bars_fn so it returns n bars at the strategy's own bar_freq.

        Reads self._steps[idx] lazily at call time so the step is always correct
        after all strategies have been registered and _recompute_steps() has run.
        """
        def adapted(symbol: str, n: int) -> list[TickEvent]:
            steps = self._steps[idx] if idx < len(self._steps) else 1
            if steps == 1:
                return get_bars_fn(symbol, n)
            return _aggregate_bars(get_bars_fn(symbol, n * steps), steps)
        return adapted

    def emit(self, event: Event) -> None:
        self._emit_fn(event)

    def add(
        self,
        strategy_class:  type[Strategy],
        strategy_params: StrategyParams,
        *,
        get_bars: Callable[[str, int], list[TickEvent]] | None = None,
    ) -> None:
        """Factory: construct a strategy and register it with its nominal."""
        strategy_id = strategy_params.name or f"{strategy_class.__name__}_{len(self._strategies)}"
        if strategy_id in self._ids:
            raise ValueError(f"Strategy id {strategy_id!r} is already registered")
        idx = len(self._strategies)
        raw_get_bars = get_bars if get_bars is not None else self._get_bars
        instance = strategy_class(
            get_bars=self._make_freq_adapter(idx, raw_get_bars),
            strategy_params=strategy_params,
        )
        self._strategies.append((instance, strategy_params.nominal))
        self._carried.append({})
        self._ids.append(strategy_id)
        self._recompute_steps()

    def add_strategy(self, strategy: Strategy, nominal: float = 1.0) -> None:
        """Add a pre-constructed strategy instance with an explicit nominal.

        Note: the strategy ID is always auto-generated as ClassName_index.
        To use a custom name, register via add() with StrategyParams.name instead.
        """
        if any(s is strategy for s, _ in self._strategies):
            raise ValueError("Strategy instance is already registered in this container")
        strategy_id = f"{strategy.__class__.__name__}_{len(self._strategies)}"
        if strategy_id in self._ids:
            raise ValueError(f"Strategy id {strategy_id!r} is already registered")
        idx = len(self._strategies)
        self._strategies.append((strategy, nominal))
        self._carried.append({})
        self._ids.append(strategy_id)
        self._recompute_steps()
        strategy._get_bars = self._make_freq_adapter(idx, strategy._get_bars)

    def get_signals(self, event: BarBundleEvent) -> None:
        # Snapshot carries before updating — needed for full-exit attribution
        prev_carried = [{**c} for c in self._carried]

        self._bar_count += 1
        any_new = False
        for i, (strategy, _) in enumerate(self._strategies):
            steps = self._steps[i] if self._steps else 1
            eod_gated = self._is_eod_gated[i] if self._is_eod_gated else False
            if eod_gated:
                if not event.is_end_of_day:
                    continue   # daily strategy in intraday container — skip until EOD
            elif self._bar_count % steps != 0:
                continue   # carry-forward unchanged; strategy not called this bar
            result = strategy.calculate_signals(event)
            strategy.on_get_signal(result)
            if result is not None:
                any_new = True
                for symbol, sig in result.signals.items():
                    self._carried[i][symbol] = sig.signal

        if not any_new:
            return

        total_nominal = sum(n for _, n in self._strategies) or 1.0
        weights = [n / total_nominal for _, n in self._strategies]

        # Weighted sum across all carried signals
        combined: dict[str, float] = {}
        for i, weight in enumerate(weights):
            for symbol, signal_val in self._carried[i].items():
                combined[symbol] = combined.get(symbol, 0.0) + signal_val * weight

        if not combined:
            return

        # Delta-based attribution: buys go to strategies that raised their signal,
        # sells go to strategies that lowered their signal.  This keeps
        # _strategy_qty in the portfolio accurate so unrealized PnL reconciles.
        per_strategy: dict[str, dict[str, float]] = {}
        for symbol, combined_val in combined.items():
            prev_combined = sum(prev_carried[i].get(symbol, 0.0) * w for i, w in enumerate(weights))
            delta = combined_val - prev_combined

            if combined_val == 0.0:
                # Full exit: split equally among strategies that were long last bar
                prev_nonzero = [i for i in range(len(self._strategies))
                                if prev_carried[i].get(symbol, 0.0) != 0.0]
                if prev_nonzero:
                    share = 1.0 / len(prev_nonzero)
                    for i in prev_nonzero:
                        per_strategy.setdefault(self._ids[i], {})[symbol] = share
            elif delta != 0:
                # Net entry/increase (delta > 0): attribute to strategies that raised signal.
                # Net exit/decrease (delta < 0): attribute to strategies that lowered signal.
                wdeltas = {
                    i: (self._carried[i].get(symbol, 0.0) - prev_carried[i].get(symbol, 0.0)) * weights[i]
                    for i in range(len(self._strategies))
                }
                if delta > 0:
                    contributors = {i: d for i, d in wdeltas.items() if d > 0}
                else:
                    contributors = {i: -d for i, d in wdeltas.items() if d < 0}
                total = sum(contributors.values())
                if total > 0:
                    for i, d in contributors.items():
                        per_strategy.setdefault(self._ids[i], {})[symbol] = d / total
            else:
                # delta == 0: signal unchanged, but prices may cause rebalancing
                # fills — use current signal fractions so those fills are attributed
                for i, weight in enumerate(weights):
                    frac = weight * self._carried[i].get(symbol, 0.0) / combined_val
                    if frac != 0.0:
                        per_strategy.setdefault(self._ids[i], {})[symbol] = frac

        self.emit(StrategyBundleEvent(
            timestamp=event.timestamp,
            combined={
                symbol: SignalEvent(symbol=symbol, timestamp=event.timestamp, signal=val)
                for symbol, val in combined.items()
            },
            per_strategy=per_strategy,
        ))
