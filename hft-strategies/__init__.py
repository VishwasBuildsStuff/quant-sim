"""
HFT Strategies Package
Complete trading strategy framework

Includes:
- Base agent framework
- Technical indicators library
- Retail trader (behavioral finance)
- Semi-professional trader
- Institutional algorithms (TWAP, VWAP, IS)
- HFT strategies (Market Making, Arbitrage, Stat Arb)
"""

try:
    from .base_agent import (
        BaseAgent,
        AgentConfig,
        AgentType,
        AgentState,
        OrderRequest,
        Fill,
        Position,
        AgentPerformance
    )
    from .indicators import (
        MovingAverage,
        MomentumIndicators,
        VolatilityIndicators,
        VolumeIndicators,
        PatternDetection,
        TechnicalAnalysis
    )
    from .agents import (
        RetailTraderAgent,
        SemiProfessionalTraderAgent,
        InstitutionalTraderAgent,
        HFTMarketMakerAgent,
        HFTLatencyArbAgent,
        HFTStatArbAgent
    )
except ImportError:
    # Fallback for direct module loading (e.g., pytest collection in hyphenated dirs)
    from base_agent import (
        BaseAgent,
        AgentConfig,
        AgentType,
        AgentState,
        OrderRequest,
        Fill,
        Position,
        AgentPerformance
    )
    from indicators import (
        MovingAverage,
        MomentumIndicators,
        VolatilityIndicators,
        VolumeIndicators,
        PatternDetection,
        TechnicalAnalysis
    )
    from agents import (
        RetailTraderAgent,
        SemiProfessionalTraderAgent,
        InstitutionalTraderAgent,
        HFTMarketMakerAgent,
        HFTLatencyArbAgent,
        HFTStatArbAgent
    )

__all__ = [
    'BaseAgent',
    'AgentConfig',
    'AgentType',
    'AgentState',
    'OrderRequest',
    'Fill',
    'Position',
    'AgentPerformance',
    'MovingAverage',
    'MomentumIndicators',
    'VolatilityIndicators',
    'VolumeIndicators',
    'PatternDetection',
    'TechnicalAnalysis',
    'RetailTraderAgent',
    'SemiProfessionalTraderAgent',
    'InstitutionalTraderAgent',
    'HFTMarketMakerAgent',
    'HFTLatencyArbAgent',
    'HFTStatArbAgent'
]
