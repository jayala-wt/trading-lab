from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BotDefinition(BaseModel):
    class Config:
        extra = "allow"

    id: str
    market: str
    timeframe: str
    enabled: bool = True


class UniverseConfig(BaseModel):
    class Config:
        extra = "allow"

    mode: str = "list"
    symbols: List[str] = Field(default_factory=list)


class DataScheduleConfig(BaseModel):
    class Config:
        extra = "allow"

    interval_seconds: int = 60
    market_hours_only: bool = True


class DataBarsConfig(BaseModel):
    class Config:
        extra = "allow"

    lookback_bars: int = 500


class DataConfig(BaseModel):
    class Config:
        extra = "allow"

    provider: str = "alpaca"
    bars: DataBarsConfig = Field(default_factory=DataBarsConfig)
    schedule: DataScheduleConfig = Field(default_factory=DataScheduleConfig)


class PatternRef(BaseModel):
    class Config:
        extra = "allow"

    id: str
    config: str


class StrategyRef(BaseModel):
    class Config:
        extra = "allow"

    id: str
    config: str


class PipelineConfig(BaseModel):
    class Config:
        extra = "allow"

    patterns: List[PatternRef] = Field(default_factory=list)
    strategies: List[StrategyRef] = Field(default_factory=list)


class ExecutionConfig(BaseModel):
    class Config:
        extra = "allow"

    mode: str = "off"
    gated: bool = True
    risk_defaults: Optional[str] = None


class VisualsConfig(BaseModel):
    class Config:
        extra = "allow"

    generate_on: List[str] = Field(default_factory=list)
    chart_style: str = "minimal_dark"
    overlay_template: Optional[str] = None


class ContentConfig(BaseModel):
    class Config:
        extra = "allow"

    enabled: bool = True
    caption_templates: List[str] = Field(default_factory=list)


class BotConfig(BaseModel):
    class Config:
        extra = "allow"

    bot: BotDefinition
    universe: UniverseConfig
    data: DataConfig = Field(default_factory=DataConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    visuals: VisualsConfig = Field(default_factory=VisualsConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)


class PatternConfig(BaseModel):
    class Config:
        extra = "allow"

    id: str
    name: str
    implementation: str = "primitives"
    description: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    logic: Dict[str, Any] = Field(default_factory=dict)
    plugin_class: Optional[str] = None


class StrategyConfig(BaseModel):
    class Config:
        extra = "allow"

    id: str
    name: str
    description: Optional[str] = None
    required_patterns: List[str] = Field(default_factory=list)
    entry: Dict[str, Any] = Field(default_factory=dict)
    exit: Dict[str, Any] = Field(default_factory=dict)
    risk: Dict[str, Any] = Field(default_factory=dict)
    scoring: Dict[str, Any] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)


class RiskDefaults(BaseModel):
    class Config:
        extra = "allow"

    arm_required: bool = False
    max_trades_per_day: int = 5
    max_daily_loss_usd: float = 25.0
    max_position_usd: float = 150.0
    allow_short: bool = False
    api_error_kill_switch_threshold: int = 5

