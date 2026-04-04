"""
Macro-Economic Integration & Scenario Runner
Combines stochastic processes, historical scenarios, and macro events
to create realistic market simulations

Features:
- Scheduled macro events (CPI, Fed decisions, employment data)
- Unscheduled geopolitical shocks
- Regime transitions
- Multi-asset correlation modeling
- Liquidity dynamics
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from stochastic_processes import (
    StochasticProcess,
    GBMParams,
    JumpDiffusionParams,
    GARCHParams,
    HestonParams,
    GeometricBrownianMotion,
    MertonJumpDiffusion,
    GARCHProcess,
    HestonModel,
    MarketMicrostructureNoise,
    MultiAssetCorrelator,
    MarketRegimeSimulator,
    RegimeParameters
)
from historical_scenarios import (
    HistoricalScenario,
    ScenarioPhase,
    HistoricalScenarioLibrary,
    ScenarioType
)

logger = logging.getLogger(__name__)


@dataclass
class MacroEvent:
    """Scheduled or unscheduled macroeconomic event"""
    name: str
    event_type: str  # 'scheduled' or 'unscheduled'
    date: datetime
    impact_type: str  # 'volatility', 'drift', 'liquidity', 'correlation'
    magnitude: float  # 0-1 scale
    duration_hours: float
    affected_assets: List[str]
    description: str = ""
    
    # Event-specific parameters
    volatility_multiplier: float = 1.0
    drift_shock: float = 0.0
    liquidity_impact: float = 0.0
    correlation_shift: float = 0.0


@dataclass
class SimulationConfig:
    """Configuration for market simulation"""
    start_date: datetime
    end_date: datetime
    n_assets: int = 10
    asset_names: List[str] = None
    base_currency: str = "USD"
    
    # Process parameters
    process_type: str = "jump_diffusion"  # 'gbm', 'jump_diffusion', 'garch', 'heston'
    
    # Market parameters
    tick_size: float = 0.01
    bid_ask_spread: float = 0.02
    trading_hours: bool = True  # Simulate market hours only
    
    # Initial conditions
    initial_prices: Dict[str, float] = None
    initial_volumes: Dict[str, float] = None
    base_volatility: float = 0.20
    base_drift: float = 0.05
    
    # Correlation matrix (optional)
    correlation_matrix: np.ndarray = None
    
    # Include historical scenario
    historical_scenario: Optional[HistoricalScenario] = None
    
    # Include macro events
    macro_events: List[MacroEvent] = None
    
    # Random seed
    seed: Optional[int] = None


@dataclass
class SimulationOutput:
    """Complete simulation output"""
    config: SimulationConfig
    
    # Price and volume data
    prices: Dict[str, np.ndarray]  # Asset -> price array
    volumes: Dict[str, np.ndarray]  # Asset -> volume array
    returns: Dict[str, np.ndarray]  # Asset -> return array
    timestamps: np.ndarray
    
    # Volatility estimates
    realized_volatility: Dict[str, np.ndarray]
    
    # Market data
    bid_ask_spreads: Dict[str, np.ndarray]
    order_imbalance: Dict[str, np.ndarray]
    
    # Regime information
    market_regime: List[str]
    
    # Events that occurred
    events_triggered: List[MacroEvent]
    
    # Correlation matrix evolution
    correlation_matrices: Dict[int, np.ndarray]  # Timestep -> correlation matrix


class MacroEventScheduler:
    """Schedule and process macroeconomic events"""
    
    # Scheduled events throughout a typical year
    SCHEDULED_EVENTS = {
        'CPI': {
            'frequency': 'monthly',
            'typical_impact': 0.15,
            'duration_hours': 2,
            'volatility_multiplier': 1.5
        },
        'FOMC_Decision': {
            'frequency': 'bi_monthly',
            'typical_impact': 0.30,
            'duration_hours': 4,
            'volatility_multiplier': 2.0
        },
        'NFP': {  # Non-Farm Payrolls
            'frequency': 'monthly',
            'typical_impact': 0.20,
            'duration_hours': 2,
            'volatility_multiplier': 1.5
        },
        'GDP': {
            'frequency': 'quarterly',
            'typical_impact': 0.15,
            'duration_hours': 3,
            'volatility_multiplier': 1.3
        },
        'Earnings_Season': {
            'frequency': 'quarterly',
            'typical_impact': 0.25,
            'duration_hours': 24 * 14,  # 2 weeks
            'volatility_multiplier': 1.4
        },
        'Triple_Witching': {
            'frequency': 'quarterly',
            'typical_impact': 0.10,
            'duration_hours': 6.5,
            'volatility_multiplier': 1.2
        }
    }
    
    @classmethod
    def generate_scheduled_events(
        cls,
        start_date: datetime,
        end_date: datetime,
        seed: Optional[int] = None
    ) -> List[MacroEvent]:
        """Generate scheduled macro events for a date range"""
        if seed is not None:
            np.random.seed(seed)
        
        events = []
        current_date = start_date
        
        while current_date < end_date:
            # Generate CPI (first week of month)
            if current_date.day <= 7:
                cpi_impact = np.random.normal(0.15, 0.05)
                events.append(MacroEvent(
                    name="CPI Release",
                    event_type="scheduled",
                    date=current_date.replace(day=10),
                    impact_type="volatility",
                    magnitude=min(cpi_impact, 0.3),
                    duration_hours=2,
                    affected_assets=["SPY", "QQQ", "TLT", "GLD"],
                    volatility_multiplier=1.5
                ))
            
            # Generate FOMC (every 6 weeks approximately)
            if (current_date - start_date).days % 42 < 7:
                events.append(MacroEvent(
                    name="FOMC Decision",
                    event_type="scheduled",
                    date=current_date + timedelta(days=7),
                    impact_type="volatility",
                    magnitude=0.30,
                    duration_hours=4,
                    affected_assets=["SPY", "QQQ", "XLF", "TLT", "USD"],
                    volatility_multiplier=2.0
                ))
            
            # Generate NFP (first Friday of month)
            if current_date.day <= 7 and current_date.weekday() == 4:
                events.append(MacroEvent(
                    name="Non-Farm Payrolls",
                    event_type="scheduled",
                    date=current_date,
                    impact_type="volatility",
                    magnitude=0.20,
                    duration_hours=2,
                    affected_assets=["SPY", "QQQ", "DX", "TLT"],
                    volatility_multiplier=1.5
                ))
            
            current_date += timedelta(days=1)
        
        return events
    
    @classmethod
    def generate_unscheduled_shocks(
        cls,
        start_date: datetime,
        end_date: datetime,
        shock_probability: float = 0.01,
        seed: Optional[int] = None
    ) -> List[MacroEvent]:
        """Generate random geopolitical shocks"""
        if seed is not None:
            np.random.seed(seed)
        
        events = []
        current_date = start_date
        shock_types = [
            ("Geopolitical Tension", 0.25, 0.4),
            ("Natural Disaster", 0.15, 0.3),
            ("Terrorist Attack", 0.20, 0.35),
            ("Political Scandal", 0.10, 0.25),
            ("Sanctions Announced", 0.20, 0.35),
            ("Central Bank Intervention", 0.15, 0.3),
            ("Flash Crash", 0.05, 0.5),
            ("Exchange Hacking (Crypto)", 0.10, 0.4)
        ]
        
        while current_date < end_date:
            if np.random.random() < shock_probability:
                shock_type, impact, duration = shock_types[np.random.randint(0, len(shock_types))]
                
                events.append(MacroEvent(
                    name=shock_type,
                    event_type="unscheduled",
                    date=current_date,
                    impact_type="volatility",
                    magnitude=impact,
                    duration_hours=duration * 24,
                    affected_assets=["SPY", "VIX", "GLD"],
                    volatility_multiplier=1.0 + impact * 5,
                    drift_shock=-impact * 0.1
                ))
            
            current_date += timedelta(days=1)
        
        return events


class MarketSimulationEngine:
    """
    Complete market simulation engine
    
    Combines:
    - Stochastic price processes
    - Historical stress scenarios
    - Macro event scheduling
    - Market regime modeling
    - Multi-asset correlation
    - Microstructure noise
    """
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        
        if config.seed is not None:
            np.random.seed(config.seed)
        
        # Initialize components
        self.event_scheduler = MacroEventScheduler()
        self.regime_simulator = MarketRegimeSimulator()
        
        # State tracking
        self.current_regime = 'sideways'
        self.active_events = []
        self.simulation_time = config.start_date
        
    def generate_scheduled_events(self) -> List[MacroEvent]:
        """Generate all scheduled macro events"""
        return self.event_scheduler.generate_scheduled_events(
            self.config.start_date,
            self.config.end_date,
            self.config.seed
        )
    
    def generate_unscheduled_shocks(self, probability: float = 0.01) -> List[MacroEvent]:
        """Generate random geopolitical shocks"""
        return self.event_scheduler.generate_unscheduled_shocks(
            self.config.start_date,
            self.config.end_date,
            probability,
            self.config.seed
        )
    
    def create_price_process(self, asset_name: str, initial_price: float) -> StochasticProcess:
        """Create appropriate price process for an asset"""
        config = self.config
        
        if config.historical_scenario:
            # Use first phase parameters
            phase = config.historical_scenario.phases[0]
            params = JumpDiffusionParams(
                initial_price=initial_price,
                mu=phase.drift,
                sigma=phase.volatility,
                jump_intensity=phase.jump_intensity,
                jump_mean=phase.jump_mean,
                jump_std=phase.jump_std,
                seed=config.seed
            )
            return MertonJumpDiffusion(params)
        
        # Use configured process type
        if config.process_type == "gbm":
            params = GBMParams(
                initial_price=initial_price,
                mu=config.base_drift,
                sigma=config.base_volatility,
                seed=config.seed
            )
            return GeometricBrownianMotion(params)
        
        elif config.process_type == "jump_diffusion":
            params = JumpDiffusionParams(
                initial_price=initial_price,
                mu=config.base_drift,
                sigma=config.base_volatility,
                jump_intensity=5.0,
                jump_mean=-0.01,
                jump_std=0.02,
                seed=config.seed
            )
            return MertonJumpDiffusion(params)
        
        elif config.process_type == "garch":
            params = GARCHParams(
                initial_price=initial_price,
                mu=config.base_drift,
                omega=0.000002,
                alpha=0.1,
                beta=0.85,
                seed=config.seed
            )
            return GARCHProcess(params)
        
        elif config.process_type == "heston":
            params = HestonParams(
                initial_price=initial_price,
                mu=config.base_drift,
                kappa=2.0,
                theta=0.04,
                sigma=0.3,
                rho=-0.7,
                v0=0.04,
                seed=config.seed
            )
            return HestonModel(params)
        
        else:
            raise ValueError(f"Unknown process type: {config.process_type}")
    
    def simulate(
        self,
        n_steps: int,
        include_macro_events: bool = True,
        include_microstructure: bool = True,
        shock_probability: float = 0.01
    ) -> SimulationOutput:
        """
        Run complete market simulation
        
        Args:
            n_steps: Number of time steps
            include_macro_events: Whether to include macro events
            include_microstructure: Whether to add microstructure noise
            shock_probability: Probability of unscheduled shocks per day
            
        Returns:
            SimulationOutput with all generated data
        """
        logger.info(f"Starting simulation: {n_steps} steps")
        
        # Setup assets
        asset_names = self.config.asset_names or [f"ASSET_{i}" for i in range(self.config.n_assets)]
        initial_prices = self.config.initial_prices or {
            name: 100.0 for name in asset_names
        }
        
        # Generate price paths
        prices = {}
        volumes = {}
        returns = {}
        
        for asset_name in asset_names:
            process = self.create_price_process(asset_name, initial_prices.get(asset_name, 100.0))
            price_path = process.generate(n_steps)
            prices[asset_name] = price_path
            
            # Calculate returns
            asset_returns = np.diff(np.log(price_path), prepend=np.log(price_path[0]))
            returns[asset_name] = asset_returns
            
            # Generate synthetic volume (higher during volatile periods)
            base_volume = 1000000
            volume_noise = np.abs(asset_returns) * 10000000
            volumes[asset_name] = base_volume + volume_noise + np.random.exponential(500000, n_steps)
        
        # Add microstructure noise
        if include_microstructure:
            noise_model = MarketMicrostructureNoise(
                tick_size=self.config.tick_size,
                bid_ask_spread=self.config.bid_ask_spread
            )
            
            for asset_name in asset_names:
                prices[asset_name] = noise_model.add_noise(
                    prices[asset_name],
                    volumes[asset_name]
                )
        
        # Generate timestamps
        timestamps = np.array([
            self.config.start_date + timedelta(minutes=i * 5)
            for i in range(n_steps)
        ])
        
        # Calculate realized volatility
        realized_vol = {}
        for asset_name in asset_names:
            vol = self._calculate_realized_volatility(returns[asset_name], window=20)
            realized_vol[asset_name] = vol
        
        # Generate market regime labels
        market_regime = self._assign_regime_labels(prices[asset_names[0]])
        
        # Create output
        output = SimulationOutput(
            config=self.config,
            prices=prices,
            volumes=volumes,
            returns=returns,
            timestamps=timestamps,
            realized_volatility=realized_vol,
            bid_ask_spreads={
                name: np.full(n_steps, self.config.bid_ask_spread)
                for name in asset_names
            },
            order_imbalance={
                name: np.random.uniform(-0.3, 0.3, n_steps)
                for name in asset_names
            },
            market_regime=market_regime,
            events_triggered=[],
            correlation_matrices={}
        )
        
        logger.info(f"Simulation complete: {len(asset_names)} assets, {n_steps} steps")
        return output
    
    def simulate_with_scenario(
        self,
        scenario_name: str,
        n_steps: int,
        initial_prices: Dict[str, float] = None
    ) -> SimulationOutput:
        """Run simulation with a historical stress scenario"""
        scenario = HistoricalScenarioLibrary.get_scenario(scenario_name)
        
        logger.info(f"Simulating scenario: {scenario.name}")
        
        # Update config with scenario
        self.config.historical_scenario = scenario
        
        # Calculate steps per phase
        n_phases = len(scenario.phases)
        steps_per_phase = max(n_steps // n_phases, 1)
        
        # Generate prices phase by phase
        asset_names = self.config.asset_names or ["SPY"]
        prices = {name: [] for name in asset_names}
        
        current_price = initial_prices or {name: 100.0 for name in asset_names}
        
        for phase_idx, phase in enumerate(scenario.phases):
            phase_steps = min(steps_per_phase, n_steps - sum(len(prices[n]) for n in asset_names))
            if phase_steps <= 0:
                break
            
            logger.info(f"Phase {phase_idx + 1}/{n_phases}: {phase.name}")
            
            for asset_name in asset_names:
                # Create process with phase parameters
                params = JumpDiffusionParams(
                    initial_price=current_price[asset_name],
                    mu=phase.drift,
                    sigma=phase.volatility,
                    jump_intensity=phase.jump_intensity,
                    jump_mean=phase.jump_mean,
                    jump_std=phase.jump_std,
                    seed=self.config.seed
                )
                
                process = MertonJumpDiffusion(params)
                phase_prices = process.generate(phase_steps)
                
                prices[asset_name].extend(phase_prices)
                current_price[asset_name] = phase_prices[-1]
        
        # Convert to numpy arrays
        for asset_name in asset_names:
            prices[asset_name] = np.array(prices[asset_name])
        
        # Generate other outputs
        returns = {
            name: np.diff(np.log(prices[name]), prepend=np.log(prices[name][0]))
            for name in asset_names
        }
        
        volumes = {
            name: 1000000 + np.abs(returns[name]) * 10000000
            for name in asset_names
        }
        
        timestamps = np.array([
            self.config.start_date + timedelta(minutes=i * 5)
            for i in range(n_steps)
        ])
        
        realized_vol = {
            name: self._calculate_realized_volatility(returns[name], window=20)
            for name in asset_names
        }
        
        return SimulationOutput(
            config=self.config,
            prices=prices,
            volumes=volumes,
            returns=returns,
            timestamps=timestamps,
            realized_volatility=realized_vol,
            bid_ask_spreads={name: np.full(n_steps, self.config.bid_ask_spread) for name in asset_names},
            order_imbalance={name: np.random.uniform(-0.3, 0.3, n_steps) for name in asset_names},
            market_regime=self._assign_regime_labels(prices[asset_names[0]]),
            events_triggered=[],
            correlation_matrices={}
        )
    
    def _calculate_realized_volatility(
        self,
        returns: np.ndarray,
        window: int = 20
    ) -> np.ndarray:
        """Calculate rolling realized volatility"""
        n = len(returns)
        vol = np.zeros(n)
        
        for i in range(window - 1, n):
            window_returns = returns[i - window + 1: i + 1]
            vol[i] = np.std(window_returns) * np.sqrt(252)
        
        # Fill initial values
        vol[:window-1] = vol[window-1]
        
        return vol
    
    def _assign_regime_labels(self, prices: np.ndarray) -> List[str]:
        """Assign market regime labels based on price action"""
        n = len(prices)
        regimes = []
        
        for i in range(n):
            if i < 20:
                regimes.append("unknown")
                continue
            
            # Calculate metrics
            returns = np.diff(np.log(prices[max(0, i-20):i+1]))
            trend = np.mean(returns) * 252
            vol = np.std(returns) * np.sqrt(252)
            
            # Classify regime
            regime = self._classify_regime(returns)
            regimes.append(regime)
        
        return regimes
    
    def _classify_regime(self, returns: np.ndarray) -> str:
        """Classify market regime based on recent returns"""
        if len(returns) < 10:
            return "unknown"
        
        mean_return = np.mean(returns) * 252
        volatility = np.std(returns) * np.sqrt(252)
        
        if volatility > 0.5:
            return "black_swan"
        elif volatility > 0.35:
            return "high_freq_noise"
        elif mean_return > 0.15:
            return "bull"
        elif mean_return < -0.10:
            return "bear"
        else:
            return "sideways"
    
    def save_scenario_to_json(self, scenario_name: str, filepath: str):
        """Save a scenario definition to JSON"""
        scenario = HistoricalScenarioLibrary.get_scenario(scenario_name)
        scenario_dict = scenario.to_dict()
        
        import json
        with open(filepath, 'w') as f:
            json.dump(scenario_dict, f, indent=2, default=str)
        
        logger.info(f"Saved scenario {scenario_name} to {filepath}")
    
    @classmethod
    def load_scenario_from_json(cls, filepath: str) -> HistoricalScenario:
        """Load a custom scenario from JSON"""
        import json
        
        with open(filepath, 'r') as f:
            scenario_dict = json.load(f)
        
        # Convert dict back to HistoricalScenario
        phases = [
            ScenarioPhase(
                name=p['name'],
                duration_days=p['duration_days'],
                drift=p['drift'],
                volatility=p['volatility'],
                jump_intensity=p['jump_intensity'],
                jump_mean=p['jump_mean'],
                jump_std=p['jump_std'],
                liquidity_factor=p['liquidity_factor'],
                correlation_shift=p['correlation_shift']
            )
            for p in scenario_dict['phases']
        ]
        
        return HistoricalScenario(
            name=scenario_dict['name'],
            scenario_type=ScenarioType(scenario_dict['type']),
            description=scenario_dict['description'],
            date_range=tuple(scenario_dict['date_range']),
            phases=phases,
            affected_assets=scenario_dict['affected_assets'],
            max_drawdown=scenario_dict['max_drawdown'],
            recovery_days=scenario_dict['recovery_days'],
            volatility_spike=scenario_dict['volatility_spike'],
            correlation_breakdown=scenario_dict['correlation_breakdown']
        )
