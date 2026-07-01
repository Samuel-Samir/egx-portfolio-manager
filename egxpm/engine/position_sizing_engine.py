"""Position Sizing Engine — Stage 9 of the canonical pipeline (swing pipeline only).

Pure function: ATR-based stop/target/size, with a portfolio-heat guard.
Entry price comes from TechnicalSnapshotResult.latest_close (see
technical_engine.py) — this Engine runs later in the same Job as the
Technical Engine, consuming its in-memory result directly rather than a
separately-supplied price.
"""

from __future__ import annotations

from pydantic import BaseModel

from egxpm.engine.technical_engine import TechnicalSnapshotResult
from egxpm.persistence.models import AllocationReport, ConfigurationSnapshot
from egxpm.shared.exceptions import InsufficientVolatilityDataError, PortfolioHeatExceededError

DEFAULT_ATR_MULTIPLIER = 1.5
DEFAULT_RISK_REWARD_RATIO = 2.0


class PositionSizing(BaseModel):
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_distance: float
    position_size: float  # shares
    risk_reward_ratio: float
    new_risk_egp: float


def calculate_position_size(
    technical_snapshot: TechnicalSnapshotResult,
    risk_config: ConfigurationSnapshot,
    portfolio: AllocationReport,
) -> PositionSizing:
    """Pure.

    Raises:
        InsufficientVolatilityDataError: ATR is unavailable or zero.
        PortfolioHeatExceededError: this trade's risk would push total open
            risk past max_portfolio_heat_pct of the portfolio.
    """
    atr = technical_snapshot.indicators.atr
    if atr is None or atr <= 0:
        raise InsufficientVolatilityDataError("ATR is unavailable or zero — cannot size a position")

    entry_price = technical_snapshot.latest_close
    atr_multiplier = risk_config.risk_settings.get("atr_multiplier", DEFAULT_ATR_MULTIPLIER)
    risk_reward_ratio = risk_config.risk_settings.get("risk_reward_ratio", DEFAULT_RISK_REWARD_RATIO)
    risk_per_trade_pct = risk_config.risk_settings.get("risk_per_trade_pct", 0.0)
    max_position_pct = risk_config.risk_settings.get("max_position_pct", 0.0)
    max_portfolio_heat_pct = risk_config.risk_settings.get("max_portfolio_heat_pct")

    stop_distance = atr * atr_multiplier
    stop_loss = entry_price - stop_distance
    take_profit = entry_price + (stop_distance * risk_reward_ratio)

    risk_based_size = (portfolio.total_value * risk_per_trade_pct) / stop_distance
    cap_based_size = (portfolio.total_value * max_position_pct) / entry_price if entry_price > 0 else 0.0
    position_size = min(risk_based_size, cap_based_size)

    new_risk_egp = position_size * stop_distance

    if max_portfolio_heat_pct is not None and portfolio.total_value > 0:
        if portfolio.open_risk_egp + new_risk_egp > max_portfolio_heat_pct * portfolio.total_value:
            raise PortfolioHeatExceededError(
                f"open_risk={portfolio.open_risk_egp:.2f} + new_risk={new_risk_egp:.2f} "
                f"exceeds max_portfolio_heat_pct={max_portfolio_heat_pct} of "
                f"portfolio_value={portfolio.total_value:.2f}"
            )

    return PositionSizing(
        entry_price=entry_price, stop_loss=stop_loss, take_profit=take_profit,
        stop_distance=stop_distance, position_size=position_size,
        risk_reward_ratio=risk_reward_ratio, new_risk_egp=new_risk_egp,
    )
