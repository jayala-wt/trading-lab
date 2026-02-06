"""
Buy Entry Classifier - Real-time ML gate for buy signal quality.

Predicts whether a buy entry is 'good' (strong reversal) or 'bad' (too early).
Used in executor.py to filter buy orders before submission.

Usage:
    from core.ml.buy_entry_classifier import get_buy_entry_classifier

    classifier = get_buy_entry_classifier()
    allow, prob, reason = classifier.should_allow_buy(dimension_snapshot, symbol)

    if not allow:
        # Skip this buy — bad entry timing
        pass
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from core.common.paths import repo_root


logger = logging.getLogger(__name__)


class BuyEntryClassifier:
    """ML model for predicting buy entry quality in real-time."""

    def __init__(self, model_dir: Optional[Path] = None):
        if model_dir is None:
            model_dir = repo_root() / "models" / "buy_entry_classifier"

        self.model_dir = Path(model_dir)
        self.model = None
        self.encoders = None
        self.metadata = None
        self.optimal_threshold = 0.60  # Default, overridden from metadata

        self._load_model()

    def _load_model(self) -> None:
        model_path = self.model_dir / "buy_entry_classifier.joblib"
        encoders_path = self.model_dir / "encoders.joblib"
        metadata_path = self.model_dir / "metadata.json"

        if not model_path.exists():
            logger.warning(
                f"Buy entry classifier not found at {model_path}. "
                "Run: python scripts/train_buy_entry_classifier.py"
            )
            return

        try:
            self.model = joblib.load(model_path)
            self.encoders = joblib.load(encoders_path)

            with open(metadata_path) as f:
                self.metadata = json.load(f)

            self.optimal_threshold = self.metadata.get("metrics", {}).get(
                "optimal_threshold", 0.60
            )

            logger.info(
                f"Buy entry classifier loaded. Trained: {self.metadata.get('trained_at')}. "
                f"Threshold: {self.optimal_threshold:.2f}"
            )
        except Exception as e:
            logger.error(f"Failed to load buy entry classifier: {e}")
            self.model = None

    def is_loaded(self) -> bool:
        return self.model is not None

    def _extract_features(
        self, dimension_snapshot: Dict[str, Any], symbol: str = "unknown"
    ) -> Optional[pd.DataFrame]:
        try:
            states = dimension_snapshot.get("states", {})
            raw = dimension_snapshot.get("raw", {})

            features = {
                "dim_momentum": states.get("momentum", "unknown"),
                "dim_trend": states.get("trend", "unknown"),
                "dim_volatility": states.get("volatility", "unknown"),
                "dim_participation": states.get("participation", "unknown"),
                "dim_location": states.get("location", "unknown"),
                "dim_structure": states.get("structure", "unknown"),
            }

            # Flatten nested raw dict (same logic as crash_predictor)
            raw_flat: Dict[str, Any] = {}
            for dim_name, dim_values in raw.items():
                if isinstance(dim_values, dict):
                    for key, val in dim_values.items():
                        raw_flat[key] = val
                else:
                    raw_flat[dim_name] = dim_values

            features.update({
                "raw_rsi": raw_flat.get("rsi", 50.0),
                "raw_stoch_k": raw_flat.get("stoch_k", 50.0),
                "raw_macd_histogram": raw_flat.get("macd_histogram", 0.0),
                "raw_ema_9": raw_flat.get("ema_9", 0.0),
                "raw_ema_21": raw_flat.get("ema_21", 0.0),
                "raw_ema_50": raw_flat.get("ema_50", 0.0),
                "raw_slope_20": raw_flat.get("slope_20", 0.0),
                "raw_atr_pct": raw_flat.get("atr_pct", 1.0),
                "raw_bb_bandwidth": raw_flat.get("bb_bandwidth", 0.02),
                "raw_bb_pct": raw_flat.get("bb_pct", 0.5),
                "raw_volume_ratio": raw_flat.get("volume_ratio", 1.0),
                "raw_vwap_distance_pct": raw_flat.get("vwap_distance_pct", 0.0),
                "symbol": symbol,
            })

            df = pd.DataFrame([features])

            for col, encoder in self.encoders.items():
                if col in df.columns:
                    value = df[col].iloc[0]
                    if value not in encoder.classes_:
                        value = encoder.classes_[0]
                        df[col] = value
                    df[col] = encoder.transform(df[col])

            return df

        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            return None

    def predict_good_probability(
        self,
        dimension_snapshot: Dict[str, Any],
        symbol: str = "unknown",
    ) -> float:
        """Return probability that this buy entry is 'good' (0.0 to 1.0)."""
        if not self.is_loaded():
            return 1.0  # Fail open: if model not loaded, allow the trade

        features = self._extract_features(dimension_snapshot, symbol)
        if features is None:
            return 1.0

        try:
            # Class 1 = good entry
            proba = self.model.predict_proba(features)[0, 1]
            return float(proba)
        except Exception as e:
            logger.error(f"Buy entry prediction failed: {e}")
            return 1.0

    def should_allow_buy(
        self,
        dimension_snapshot: Dict[str, Any],
        symbol: str = "unknown",
        threshold: Optional[float] = None,
    ) -> Tuple[bool, float, str]:
        """
        Decide if a buy should be allowed.

        Returns:
            (allow, good_probability, reason)
        """
        if not self.is_loaded():
            return True, 1.0, "model_not_loaded"

        if threshold is None:
            threshold = self.optimal_threshold

        good_prob = self.predict_good_probability(dimension_snapshot, symbol)

        if good_prob >= threshold:
            return True, good_prob, f"good_entry (P={good_prob:.2%})"
        else:
            return False, good_prob, f"bad_entry_timing (P={good_prob:.2%}, need≥{threshold:.0%})"

    def get_model_info(self) -> Dict[str, Any]:
        if not self.is_loaded():
            return {"status": "not_loaded"}
        return {
            "status": "loaded",
            "trained_at": self.metadata.get("trained_at"),
            "optimal_threshold": self.optimal_threshold,
            "metrics": self.metadata.get("metrics", {}),
            "model_path": str(self.model_dir),
        }


# Global singleton
_buy_entry_classifier: Optional[BuyEntryClassifier] = None


def get_buy_entry_classifier() -> BuyEntryClassifier:
    global _buy_entry_classifier
    if _buy_entry_classifier is None:
        _buy_entry_classifier = BuyEntryClassifier()
    return _buy_entry_classifier
