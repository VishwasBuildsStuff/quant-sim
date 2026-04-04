"""
Historical Stress Scenarios
Pre-configured market scenarios based on real historical events

Includes:
- 2010 Flash Crash
- 2008 Global Financial Crisis
- 2020 Pandemic Market Crash
- Commodity shocks (energy crises, supply chain disruptions)
- Geopolitical events
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path

from stochastic_processes import (
    JumpDiffusionParams,
    MertonJumpDiffusion,
    GARCHParams,
    GARCHProcess,
    MarketRegimeSimulator
)


class ScenarioType(Enum):
    FLASH_CRASH = "flash_crash"
    FINANCIAL_CRISIS = "financial_crisis"
    PANDEMIC_CRASH = "pandemic_crash"
    COMMODITY_SHOCK = "commodity_shock"
    GEOPOLITICAL_CRISIS = "geopolitical_crisis"
    CURRENCY_CRISIS = "currency_crisis"
    DOTCOM_BUBBLE = "dotcom_bubble"
    CUSTOM = "custom"


@dataclass
class ScenarioPhase:
    """A phase within a stress scenario"""
    name: str
    duration_days: int
    drift: float
    volatility: float
    jump_intensity: float
    jump_mean: float
    jump_std: float
    liquidity_factor: float  # 0-1, lower = less liquid
    correlation_shift: float  # How much correlations increase


@dataclass
class HistoricalScenario:
    """Complete historical stress scenario definition"""
    name: str
    scenario_type: ScenarioType
    description: str
    date_range: Tuple[str, str]  # (start_date, end_date)
    phases: List[ScenarioPhase]
    affected_assets: List[str]
    max_drawdown: float  # Maximum peak-to-trough decline
    recovery_days: int  # Days to recover to pre-crisis level
    volatility_spike: float  # Peak volatility / normal volatility
    correlation_breakdown: bool  # Do normal correlations break down?

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'type': self.scenario_type.value,
            'description': self.description,
            'date_range': list(self.date_range),
            'phases': [
                {
                    'name': p.name,
                    'duration_days': p.duration_days,
                    'drift': p.drift,
                    'volatility': p.volatility,
                    'jump_intensity': p.jump_intensity,
                    'jump_mean': p.jump_mean,
                    'jump_std': p.jump_std,
                    'liquidity_factor': p.liquidity_factor,
                    'correlation_shift': p.correlation_shift
                }
                for p in self.phases
            ],
            'affected_assets': self.affected_assets,
            'max_drawdown': self.max_drawdown,
            'recovery_days': self.recovery_days,
            'volatility_spike': self.volatility_spike,
            'correlation_breakdown': self.correlation_breakdown
        }


class HistoricalScenarioLibrary:
    """Library of pre-configured historical stress scenarios"""

    # =====================================================================
    # 2010 FLASH CRASH (May 6, 2010)
    # =====================================================================
    FLASH_CRASH_2010 = HistoricalScenario(
        name="2010 Flash Crash",
        scenario_type=ScenarioType.FLASH_CRASH,
        description=(
            "On May 6, 2010, US equity markets experienced a rapid and severe decline. "
            "The Dow Jones dropped nearly 1,000 points (~9%) within minutes before recovering. "
            "Caused by algorithmic trading cascades, liquidity evaporation, and a large sell order. "
            "Key characteristics: extreme intraday volatility, temporary liquidity disappearance, "
            "some stocks traded at penny prices, rapid recovery."
        ),
        date_range=("2010-05-06", "2010-05-07"),
        phases=[
            ScenarioPhase(
                name="Pre-crash normal",
                duration_days=1,
                drift=0.0002,
                volatility=0.20,
                jump_intensity=1.0,
                jump_mean=0.0,
                jump_std=0.02,
                liquidity_factor=0.9,
                correlation_shift=0.0
            ),
            ScenarioPhase(
                name="Initial decline",
                duration_days=0,  # Intraday
                drift=-0.05,
                volatility=0.80,
                jump_intensity=15.0,
                jump_mean=-0.02,
                jump_std=0.03,
                liquidity_factor=0.5,
                correlation_shift=0.3
            ),
            ScenarioPhase(
                name="Flash crash",
                duration_days=0,  # ~36 minutes
                drift=-0.30,
                volatility=1.50,
                jump_intensity=50.0,
                jump_mean=-0.05,
                jump_std=0.05,
                liquidity_factor=0.1,  # Near-total evaporation
                correlation_shift=0.8  # Everything correlated
            ),
            ScenarioPhase(
                name="Partial recovery",
                duration_days=0,  # Intraday
                drift=0.15,
                volatility=0.60,
                jump_intensity=10.0,
                jump_mean=0.01,
                jump_std=0.02,
                liquidity_factor=0.6,
                correlation_shift=0.4
            ),
            ScenarioPhase(
                name="Post-crash normalization",
                duration_days=5,
                drift=0.001,
                volatility=0.35,
                jump_intensity=3.0,
                jump_mean=0.0,
                jump_std=0.02,
                liquidity_factor=0.8,
                correlation_shift=0.2
            )
        ],
        affected_assets=["SPY", "QQQ", "IWM", "ES", "NQ"],
        max_drawdown=-0.09,
        recovery_days=1,
        volatility_spike=7.5,
        correlation_breakdown=True
    )

    # =====================================================================
    # 2008 GLOBAL FINANCIAL CRISIS
    # =====================================================================
    FINANCIAL_CRISIS_2008 = HistoricalScenario(
        name="2008 Global Financial Crisis",
        scenario_type=ScenarioType.FINANCIAL_CRISIS,
        description=(
            "Triggered by the collapse of the US subprime mortgage market and excessive "
            "leverage in the financial system. Lehman Brothers bankruptcy (Sept 15, 2008) "
            "marked the peak of the crisis. Credit markets froze, volatility spiked to "
            "unprecedented levels, and global equity markets lost ~50% of value. "
            "Key characteristics: prolonged downturn, credit crunch, systemic risk, "
            "flight to quality, volatility clustering."
        ),
        date_range=("2007-10-01", "2009-03-09"),
        phases=[
            ScenarioPhase(
                name="Early warning (subprime concerns)",
                duration_days=180,
                drift=-0.05,
                volatility=0.25,
                jump_intensity=2.0,
                jump_mean=-0.01,
                jump_std=0.02,
                liquidity_factor=0.8,
                correlation_shift=0.1
            ),
            ScenarioPhase(
                name="Bear Stearns collapse",
                duration_days=30,
                drift=-0.10,
                volatility=0.40,
                jump_intensity=5.0,
                jump_mean=-0.02,
                jump_std=0.03,
                liquidity_factor=0.6,
                correlation_shift=0.3
            ),
            ScenarioPhase(
                name="Relative calm (false recovery)",
                duration_days=120,
                drift=0.05,
                volatility=0.20,
                jump_intensity=1.5,
                jump_mean=0.0,
                jump_std=0.02,
                liquidity_factor=0.7,
                correlation_shift=0.2
            ),
            ScenarioPhase(
                name="Lehman crisis (credit freeze)",
                duration_days=60,
                drift=-0.20,
                volatility=0.70,
                jump_intensity=12.0,
                jump_mean=-0.03,
                jump_std=0.04,
                liquidity_factor=0.2,
                correlation_shift=0.6
            ),
            ScenarioPhase(
                name="Capitulation (TARP panic)",
                duration_days=45,
                drift=-0.30,
                volatility=0.90,
                jump_intensity=15.0,
                jump_mean=-0.04,
                jump_std=0.05,
                liquidity_factor=0.15,
                correlation_shift=0.7
            ),
            ScenarioPhase(
                name="Bottoming process",
                duration_days=90,
                drift=-0.05,
                volatility=0.50,
                jump_intensity=5.0,
                jump_mean=-0.01,
                jump_std=0.03,
                liquidity_factor=0.4,
                correlation_shift=0.4
            ),
            ScenarioPhase(
                name="Recovery begins",
                duration_days=180,
                drift=0.15,
                volatility=0.35,
                jump_intensity=3.0,
                jump_mean=0.01,
                jump_std=0.02,
                liquidity_factor=0.6,
                correlation_shift=0.2
            )
        ],
        affected_assets=["SPY", "XLF", "LEH", "BAC", "C", "HYG", "LQD", "TLT"],
        max_drawdown=-0.57,
        recovery_days=1460,  # ~4 years to recover
        volatility_spike=4.5,
        correlation_breakdown=True
    )

    # =====================================================================
    # 2020 PANDEMIC MARKET CRASH
    # =====================================================================
    PANDEMIC_CRASH_2020 = HistoricalScenario(
        name="2020 Pandemic Market Crash",
        scenario_type=ScenarioType.PANDEMIC_CRASH,
        description=(
            "The fastest bear market in history. From Feb 19 to March 23, 2020, "
            "S&P 500 fell 34% as COVID-19 spread globally. Unprecedented Fed intervention "
            "and fiscal stimulus led to a V-shaped recovery. Volatility exceeded 2008 levels. "
            "Key characteristics: extremely rapid decline, sector rotation (tech up, energy down), "
            "volatility spikes, massive policy response."
        ),
        date_range=("2020-02-19", "2020-04-30"),
        phases=[
            ScenarioPhase(
                name="Denial (initial spread)",
                duration_days=15,
                drift=-0.02,
                volatility=0.25,
                jump_intensity=3.0,
                jump_mean=-0.01,
                jump_std=0.02,
                liquidity_factor=0.8,
                correlation_shift=0.2
            ),
            ScenarioPhase(
                name="Realization (WHO pandemic declaration)",
                duration_days=15,
                drift=-0.08,
                volatility=0.50,
                jump_intensity=8.0,
                jump_mean=-0.03,
                jump_std=0.04,
                liquidity_factor=0.5,
                correlation_shift=0.5
            ),
            ScenarioPhase(
                name="Panic (lockdowns begin)",
                duration_days=10,
                drift=-0.25,
                volatility=0.85,
                jump_intensity=15.0,
                jump_mean=-0.04,
                jump_std=0.05,
                liquidity_factor=0.2,
                correlation_shift=0.7
            ),
            ScenarioPhase(
                name="Capitulation (circuit breakers)",
                duration_days=5,
                drift=-0.35,
                volatility=1.10,
                jump_intensity=20.0,
                jump_mean=-0.05,
                jump_std=0.06,
                liquidity_factor=0.15,
                correlation_shift=0.8
            ),
            ScenarioPhase(
                name="Fed intervention (V-shaped recovery)",
                duration_days=25,
                drift=0.20,
                volatility=0.60,
                jump_intensity=8.0,
                jump_mean=0.02,
                jump_std=0.04,
                liquidity_factor=0.5,
                correlation_shift=0.4
            ),
            ScenarioPhase(
                name="Stimulus-fueled rally",
                duration_days=30,
                drift=0.15,
                volatility=0.40,
                jump_intensity=5.0,
                jump_mean=0.01,
                jump_std=0.03,
                liquidity_factor=0.7,
                correlation_shift=0.3
            )
        ],
        affected_assets=["SPY", "QQQ", "XLF", "XLE", "TLT", "VIX", "GLD", "BTC"],
        max_drawdown=-0.34,
        recovery_days=148,  # Remarkably fast recovery
        volatility_spike=5.5,
        correlation_breakdown=True
    )

    # =====================================================================
    # COMMODITY SHOCK - 2022 ENERGY CRISIS (Russia-Ukraine)
    # =====================================================================
    ENERGY_CRISIS_2022 = HistoricalScenario(
        name="2022 Energy Crisis (Russia-Ukraine)",
        scenario_type=ScenarioType.COMMODITY_SHOCK,
        description=(
            "Russia's invasion of Ukraine (Feb 2022) triggered massive commodity market "
            "disruptions. Natural gas prices surged 10x in Europe, oil hit $130, wheat "
            "spiked 40%. Sanctions created supply chain chaos. Energy stocks rallied while "
            "consumer-facing sectors suffered. Key characteristics: commodity-specific "
            "volatility, sector divergence, geographic variation, inflation impact."
        ),
        date_range=("2022-02-24", "2022-06-30"),
        phases=[
            ScenarioPhase(
                name="Invasion shock",
                duration_days=7,
                drift=-0.05,
                volatility=0.45,
                jump_intensity=10.0,
                jump_mean=-0.02,
                jump_std=0.03,
                liquidity_factor=0.6,
                correlation_shift=0.4
            ),
            ScenarioPhase(
                name="Sanctions escalation",
                duration_days=30,
                drift=-0.08,
                volatility=0.50,
                jump_intensity=8.0,
                jump_mean=-0.01,
                jump_std=0.03,
                liquidity_factor=0.5,
                correlation_shift=0.5
            ),
            ScenarioPhase(
                name="Energy panic",
                duration_days=20,
                drift=-0.10,
                volatility=0.65,
                jump_intensity=12.0,
                jump_mean=-0.02,
                jump_std=0.04,
                liquidity_factor=0.4,
                correlation_shift=0.6
            ),
            ScenarioPhase(
                name="Inflation concerns & rate hikes",
                duration_days=60,
                drift=-0.12,
                volatility=0.45,
                jump_intensity=6.0,
                jump_mean=-0.01,
                jump_std=0.03,
                liquidity_factor=0.5,
                correlation_shift=0.5
            ),
            ScenarioPhase(
                name="Partial stabilization",
                duration_days=30,
                drift=0.02,
                volatility=0.35,
                jump_intensity=4.0,
                jump_mean=0.0,
                jump_std=0.02,
                liquidity_factor=0.6,
                correlation_shift=0.3
            )
        ],
        affected_assets=["CL", "NG", "BZ", "XLE", "XOP", "DBA", "WEAT", "EUR", "RUB"],
        max_drawdown=-0.20,
        recovery_days=365,
        volatility_spike=3.2,
        correlation_breakdown=False
    )

    # =====================================================================
    # GEOPOLITICAL CRISIS - BREXIT VOTE 2016
    # =====================================================================
    BREXIT_2016 = HistoricalScenario(
        name="2016 Brexit Vote",
        scenario_type=ScenarioType.GEOPOLITICAL_CRISIS,
        description=(
            "The unexpected result of the UK EU referendum on June 23, 2016 caused "
            "immediate market shock. GBP fell 10% overnight, global equities dropped, "
            "and volatility surged. UK property funds suspended redemptions. "
            "Markets recovered within weeks as reality set in. Key characteristics: "
            "binary event, currency impact, regional variation, quick recovery."
        ),
        date_range=("2016-06-23", "2016-08-31"),
        phases=[
            ScenarioPhase(
                name="Pre-vote uncertainty",
                duration_days=14,
                drift=-0.01,
                volatility=0.22,
                jump_intensity=3.0,
                jump_mean=-0.005,
                jump_std=0.02,
                liquidity_factor=0.7,
                correlation_shift=0.2
            ),
            ScenarioPhase(
                name="Leave shock (overnight)",
                duration_days=1,
                drift=-0.10,
                volatility=0.70,
                jump_intensity=20.0,
                jump_mean=-0.03,
                jump_std=0.04,
                liquidity_factor=0.3,
                correlation_shift=0.6
            ),
            ScenarioPhase(
                name="Flight to safety",
                duration_days=7,
                drift=-0.05,
                volatility=0.45,
                jump_intensity=8.0,
                jump_mean=-0.01,
                jump_std=0.03,
                liquidity_factor=0.5,
                correlation_shift=0.4
            ),
            ScenarioPhase(
                name="Realization & recovery",
                duration_days=30,
                drift=0.08,
                volatility=0.30,
                jump_intensity=3.0,
                jump_mean=0.01,
                jump_std=0.02,
                liquidity_factor=0.7,
                correlation_shift=0.2
            ),
            ScenarioPhase(
                name="New normal",
                duration_days=30,
                drift=0.02,
                volatility=0.20,
                jump_intensity=2.0,
                jump_mean=0.0,
                jump_std=0.02,
                liquidity_factor=0.8,
                correlation_shift=0.1
            )
        ],
        affected_assets=["GBPUSD", "EURGBP", "FTSE", "SPY", "EWU", "GBP"],
        max_drawdown=-0.11,
        recovery_days=21,
        volatility_spike=3.5,
        correlation_breakdown=False
    )

    # =====================================================================
    # DOTCOM BUBBLE BURST 2000-2002
    # =====================================================================
    DOTCOM_BUBBLE = HistoricalScenario(
        name="Dot-com Bubble Burst (2000-2002)",
        scenario_type=ScenarioType.DOTCOM_BUBBLE,
        description=(
            "The collapse of the internet/tech bubble after years of speculative excess. "
            "NASDAQ lost 78% from peak to trough. Valuations became disconnected from "
            "fundamentals. The decline was prolonged with intermittent rallies. "
            "Key characteristics: sector-specific, prolonged decline, valuation mean reversion, "
            "multiple false bottoms."
        ),
        date_range=("2000-03-10", "2002-10-09"),
        phases=[
            ScenarioPhase(
                name="Peak euphoria",
                duration_days=10,
                drift=0.05,
                volatility=0.30,
                jump_intensity=4.0,
                jump_mean=0.02,
                jump_std=0.03,
                liquidity_factor=0.8,
                correlation_shift=0.2
            ),
            ScenarioPhase(
                name="Initial selling",
                duration_days=30,
                drift=-0.08,
                volatility=0.40,
                jump_intensity=6.0,
                jump_mean=-0.02,
                jump_std=0.03,
                liquidity_factor=0.6,
                correlation_shift=0.4
            ),
            ScenarioPhase(
                name="Bear market rally",
                duration_days=60,
                drift=0.10,
                volatility=0.35,
                jump_intensity=5.0,
                jump_mean=0.02,
                jump_std=0.03,
                liquidity_factor=0.7,
                correlation_shift=0.3
            ),
            ScenarioPhase(
                name="Second decline (recession)",
                duration_days=180,
                drift=-0.15,
                volatility=0.50,
                jump_intensity=8.0,
                jump_mean=-0.02,
                jump_std=0.04,
                liquidity_factor=0.4,
                correlation_shift=0.5
            ),
            ScenarioPhase(
                name="Post-9/11 decline",
                duration_days=30,
                drift=-0.20,
                volatility=0.70,
                jump_intensity=12.0,
                jump_mean=-0.03,
                jump_std=0.05,
                liquidity_factor=0.3,
                correlation_shift=0.6
            ),
            ScenarioPhase(
                name="Capitulation & bottom",
                duration_days=90,
                drift=-0.10,
                volatility=0.45,
                jump_intensity=6.0,
                jump_mean=-0.01,
                jump_std=0.03,
                liquidity_factor=0.5,
                correlation_shift=0.4
            )
        ],
        affected_assets=["QQQ", "MSFT", "CSCO", "INTC", "AMZN", "SPY"],
        max_drawdown=-0.78,
        recovery_days=3850,  # ~15 years for NASDAQ to recover
        volatility_spike=3.0,
        correlation_breakdown=False
    )

    @classmethod
    def get_all_scenarios(cls) -> Dict[str, HistoricalScenario]:
        return {
            "flash_crash_2010": cls.FLASH_CRASH_2010,
            "financial_crisis_2008": cls.FINANCIAL_CRISIS_2008,
            "pandemic_2020": cls.PANDEMIC_CRASH_2020,
            "energy_crisis_2022": cls.ENERGY_CRISIS_2022,
            "brexit_2016": cls.BREXIT_2016,
            "dotcom_bubble": cls.DOTCOM_BUBBLE
        }

    @classmethod
    def get_scenario(cls, name: str) -> HistoricalScenario:
        scenarios = cls.get_all_scenarios()
        if name not in scenarios:
            raise ValueError(f"Unknown scenario: {name}. Available: {list(scenarios.keys())}")
        return scenarios[name]

    @classmethod
    def get_scenario_names(cls) -> List[str]:
        return list(cls.get_all_scenarios().keys())
