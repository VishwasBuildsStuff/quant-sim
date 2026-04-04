"""
HFT Simulation Package
Market simulation, stochastic processes, and scenario generation
"""

from .stochastic_processes import (
    GeometricBrownianMotion,
    MertonJumpDiffusion,
    GARCHProcess,
    OrnsteinUhlenbeck,
    HestonModel,
    MarketMicrostructureNoise,
    MultiAssetCorrelator,
    MarketRegimeSimulator
)

from .historical_scenarios import (
    HistoricalScenarioLibrary,
    HistoricalScenario,
    ScenarioType
)

from .macro_events import (
    MarketSimulationEngine,
    SimulationConfig,
    MacroEventScheduler,
    MacroEvent
)

__all__ = [
    'GeometricBrownianMotion',
    'MertonJumpDiffusion',
    'GARCHProcess',
    'OrnsteinUhlenbeck',
    'HestonModel',
    'MarketMicrostructureNoise',
    'MultiAssetCorrelator',
    'MarketRegimeSimulator',
    'HistoricalScenarioLibrary',
    'HistoricalScenario',
    'ScenarioType',
    'MarketSimulationEngine',
    'SimulationConfig',
    'MacroEventScheduler',
    'MacroEvent'
]
