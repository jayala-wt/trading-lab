"""
Crash Predictor - Real-time ML inference for loss avoidance.

Loads trained crash prediction model and provides probability estimates
for crashes during live trading.

Usage:
    from core.ml.crash_predictor import CrashPredictor
    
    predictor = CrashPredictor()
    crash_prob = predictor.predict_crash_probability(dimension_snapshot)
    
    if crash_prob > 0.70:
        # DANGER! Skip this trade
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


class CrashPredictor:
    """ML model for predicting crash probability in real-time."""
    
    def __init__(self, model_dir: Optional[Path] = None):
        """
        Initialize crash predictor.
        
        Args:
            model_dir: Directory containing trained model. 
                      Default: trading-lab/models/crash_predictor/
        """
        if model_dir is None:
            model_dir = repo_root() / "models" / "crash_predictor"
        
        self.model_dir = Path(model_dir)
        self.model = None
        self.encoders = None
        self.metadata = None
        self.optimal_threshold = 0.70  # Default, loaded from metadata
        
        self._load_model()
    
    def _load_model(self) -> None:
        """Load model, encoders, and metadata from disk."""
        model_path = self.model_dir / "crash_predictor.joblib"
        encoders_path = self.model_dir / "encoders.joblib"
        metadata_path = self.model_dir / "metadata.json"
        
        if not model_path.exists():
            logger.warning(
                f"Crash predictor model not found at {model_path}. "
                "Run training first: python -m core.ml.crash_predictor_trainer --train"
            )
            return
        
        try:
            self.model = joblib.load(model_path)
            self.encoders = joblib.load(encoders_path)
            
            with open(metadata_path) as f:
                self.metadata = json.load(f)
            
            self.optimal_threshold = self.metadata.get("metrics", {}).get(
                "optimal_threshold", 0.70
            )
            
            logger.info(
                f"Crash predictor loaded. Trained: {self.metadata.get('trained_at')}. "
                f"Threshold: {self.optimal_threshold:.2f}"
            )
            
        except Exception as e:
            logger.error(f"Failed to load crash predictor: {e}")
            self.model = None
    
    def is_loaded(self) -> bool:
        """Check if model is loaded and ready."""
        return self.model is not None
    
    def _extract_features(self, dimension_snapshot: Dict[str, Any], symbol: str = "unknown") -> Optional[pd.DataFrame]:
        """
        Extract features from dimension snapshot for model input.
        
        Args:
            dimension_snapshot: Dict with 'states' and 'raw' keys
            symbol: Trading symbol (BTC/USD, ETH/USD, etc.)
        
        Returns:
            DataFrame with encoded features, or None if extraction fails
        """
        try:
            states = dimension_snapshot.get("states", {})
            raw = dimension_snapshot.get("raw", {})
            
            # Extract dimension states
            features = {
                "dim_momentum": states.get("momentum", "unknown"),
                "dim_trend": states.get("trend", "unknown"),
                "dim_volatility": states.get("volatility", "unknown"),
                "dim_participation": states.get("participation", "unknown"),
                "dim_location": states.get("location", "unknown"),
                "dim_structure": states.get("structure", "unknown"),
            }
            
            # Add categorical metadata features
            categorical_features = {
                "symbol": symbol,  # Each symbol has unique volatility characteristics
            }
            
            # Flatten nested raw dict (raw.momentum.rsi -> rsi, raw.trend.ema_9 -> ema_9, etc.)
            # Matches the same flattening done in sync_signals_to_ml_table (db.py)
            raw_flat: Dict[str, Any] = {}
            for dim_name, dim_values in raw.items():
                if isinstance(dim_values, dict):
                    for key, val in dim_values.items():
                        raw_flat[key] = val
                else:
                    raw_flat[dim_name] = dim_values

            # Extract raw indicator values
            raw_features = {
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
            }
            
            features.update(raw_features)
            features.update(categorical_features)
            
            # Create DataFrame
            df = pd.DataFrame([features])
            
            # Encode categorical features
            for col, encoder in self.encoders.items():
                if col in df.columns:
                    # Handle unknown categories
                    value = df[col].iloc[0]
                    if value not in encoder.classes_:
                        # Use most common class as fallback
                        value = encoder.classes_[0]
                        df[col] = value
                    
                    df[col] = encoder.transform(df[col])
            
            return df
            
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            return None
    
    def predict_crash_probability(
        self,
        dimension_snapshot: Dict[str, Any],
        symbol: str = "unknown",
    ) -> float:
        """
        Predict probability of crash for given market conditions.
        
        Args:
            dimension_snapshot: Current dimension states and raw indicators
            symbol: Trading symbol (BTC/USD, ETH/USD, etc.)
        
        Returns:
            Probability of crash (0.0 to 1.0), or 0.0 if model not loaded
        """
        if not self.is_loaded():
            return 0.0
        
        features = self._extract_features(dimension_snapshot, symbol)
        if features is None:
            return 0.0
        
        try:
            # Get probability of crash (class 1)
            proba = self.model.predict_proba(features)[0, 1]
            return float(proba)
            
        except Exception as e:
            logger.error(f"Crash prediction failed: {e}")
            return 0.0
    
    def should_block_trade(
        self,
        dimension_snapshot: Dict[str, Any],
        symbol: str = "unknown",
        threshold: Optional[float] = None,
    ) -> Tuple[bool, float, str]:
        """
        Determine if a trade should be blocked based on crash risk.
        
        Args:
            dimension_snapshot: Current dimension states and raw indicators
            symbol: Trading symbol (BTC/USD, ETH/USD, etc.)
            threshold: Custom threshold (default: use optimal from training)
        
        Returns:
            (should_block, crash_probability, reason)
        """
        if not self.is_loaded():
            return False, 0.0, "model_not_loaded"
        
        crash_prob = self.predict_crash_probability(dimension_snapshot, symbol)
        
        if threshold is None:
            threshold = self.optimal_threshold
        
        if crash_prob >= threshold:
            reason = f"crash_risk_high (P={crash_prob:.2%})"
            return True, crash_prob, reason
        
        # Also check for crash signature pattern
        states = dimension_snapshot.get("states", {})
        if self._is_crash_signature(states):
            reason = f"crash_signature_detected (P={crash_prob:.2%})"
            return True, crash_prob, reason
        
        return False, crash_prob, "safe"
    
    def _is_crash_signature(self, states: Dict[str, str]) -> bool:
        """
        Check if states match known crash signature:
        compressed + weak_trend + neutral_momentum = DANGER
        """
        volatility = states.get("volatility", "")
        trend = states.get("trend", "")
        momentum = states.get("momentum", "")
        
        return (
            volatility == "compressed"
            and trend in ["up_weak", "down_weak"]
            and momentum == "neutral"
        )
    
    def should_force_exit(
        self,
        dimension_snapshot: Dict[str, Any],
        symbol: str = "unknown",
        time_in_position_minutes: float = 0.0,
        unrealized_pnl_pct: float = 0.0,
    ) -> Tuple[bool, str]:
        """
        Determine if an open position should be force-exited during a crash.
        
        Args:
            dimension_snapshot: Current dimension states
            symbol: Trading symbol (BTC/USD, ETH/USD, etc.)
            time_in_position_minutes: How long position has been held
            unrealized_pnl_pct: Current P/L percentage
        
        Returns:
            (should_exit, reason)
        """
        if not self.is_loaded():
            return False, "model_not_loaded"
        
        crash_prob = self.predict_crash_probability(dimension_snapshot, symbol)
        
        # Crash exit rule: If losing AND crash probability high, exit fast
        if unrealized_pnl_pct < -2.0 and time_in_position_minutes > 15:
            if crash_prob >= 0.60:  # Lower threshold for exits
                return True, f"crash_protection (P={crash_prob:.2%})"
        
        # Very high crash risk = exit immediately regardless of P/L
        if crash_prob >= 0.85:
            return True, f"extreme_crash_risk (P={crash_prob:.2%})"
        
        return False, "holding"
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model."""
        if not self.is_loaded():
            return {"status": "not_loaded"}
        
        return {
            "status": "loaded",
            "trained_at": self.metadata.get("trained_at"),
            "optimal_threshold": self.optimal_threshold,
            "metrics": self.metadata.get("metrics", {}),
            "model_path": str(self.model_dir),
        }


# Global singleton instance
_crash_predictor: Optional[CrashPredictor] = None


def get_crash_predictor() -> CrashPredictor:
    """Get or create global crash predictor instance."""
    global _crash_predictor
    
    if _crash_predictor is None:
        _crash_predictor = CrashPredictor()
    
    return _crash_predictor
