from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class YFinanceAdapter:
    """Read-only historical OHLCV adapter."""

    period: str = "1mo"
    interval: str = "1d"

    def history(self, symbol: str) -> pd.DataFrame:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        data = ticker.history(period=self.period, interval=self.interval)
        if data.empty:
            msg = f"no yfinance history returned for {symbol}"
            raise RuntimeError(msg)
        return data
