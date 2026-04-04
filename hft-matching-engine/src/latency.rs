/// Latency simulation module
/// Models network jitter, packet loss, and transmission delays
/// Differentiates latency profiles between agent types

use rand::Rng;
use rand_distr::{Distribution, Normal, Uniform};
use std::time::Duration;

/// Latency profile for different agent types
#[derive(Debug, Clone)]
pub struct LatencyProfile {
    /// Mean latency in microseconds
    pub mean_latency_us: f64,

    /// Standard deviation in microseconds
    pub std_dev_us: f64,

    /// Packet loss probability
    pub packet_loss_prob: f64,

    /// Jitter in microseconds
    pub jitter_us: f64,

    /// Maximum latency cap in microseconds
    pub max_latency_us: f64,
}

impl LatencyProfile {
    /// HFT agent profile (nanosecond to microsecond latency)
    pub fn hft_profile() -> Self {
        Self {
            mean_latency_us: 1.0,        // 1 microsecond
            std_dev_us: 0.1,             // Low variance
            packet_loss_prob: 0.0001,    // Very low packet loss
            jitter_us: 0.05,             // Minimal jitter
            max_latency_us: 5.0,
        }
    }

    /// Institutional agent profile
    pub fn institutional_profile() -> Self {
        Self {
            mean_latency_us: 100.0,      // 100 microseconds
            std_dev_us: 10.0,
            packet_loss_prob: 0.001,
            jitter_us: 5.0,
            max_latency_us: 500.0,
        }
    }

    /// Semi-professional trader profile
    pub fn semi_pro_profile() -> Self {
        Self {
            mean_latency_us: 1000.0,     // 1 millisecond
            std_dev_us: 100.0,
            packet_loss_prob: 0.01,
            jitter_us: 50.0,
            max_latency_us: 5000.0,
        }
    }

    /// Retail trader profile (high latency)
    pub fn retail_profile() -> Self {
        Self {
            mean_latency_us: 100000.0,   // 100 milliseconds
            std_dev_us: 50000.0,         // High variance
            packet_loss_prob: 0.05,
            jitter_us: 10000.0,          // Significant jitter
            max_latency_us: 500000.0,    // 500ms cap
        }
    }

    /// Simulate network delay, returns actual latency in microseconds
    pub fn simulate_latency(&self) -> f64 {
        let mut rng = rand::thread_rng();

        // Check for packet loss
        if rng.gen::<f64>() < self.packet_loss_prob {
            return f64::INFINITY; // Packet lost
        }

        // Sample from normal distribution
        let normal = Normal::new(self.mean_latency_us, self.std_dev_us)
            .unwrap_or_else(|_| Normal::new(self.mean_latency_us, 1.0).unwrap());

        let mut latency = normal.sample(&mut rng);

        // Add jitter
        let jitter_dist = Uniform::new(-self.jitter_us, self.jitter_us);
        latency += jitter_dist.sample(&mut rng);

        // Clamp to valid range
        latency = latency.max(0.0).min(self.max_latency_us);

        latency
    }

    /// Convert latency to Duration
    pub fn to_duration(&self, latency_us: f64) -> Duration {
        Duration::from_micros(latency_us as u64)
    }
}

/// Latency simulator for the entire system
pub struct LatencySimulator {
    /// Profiles for different agent types
    profiles: std::collections::HashMap<u32, LatencyProfile>,

    /// Network congestion model
    congestion_factor: f64,

    /// Time series of latencies for monitoring
    latency_history: Vec<(u64, f64)>, // (timestamp, latency_us)
}

impl LatencySimulator {
    pub fn new() -> Self {
        Self {
            profiles: std::collections::HashMap::new(),
            congestion_factor: 1.0,
            latency_history: Vec::with_capacity(10000),
        }
    }

    /// Register an agent with a specific latency profile
    pub fn register_agent(&mut self, agent_id: u32, profile: LatencyProfile) {
        self.profiles.insert(agent_id, profile);
    }

    /// Simulate latency for a specific agent
    pub fn simulate_agent_latency(&mut self, agent_id: u32) -> Option<f64> {
        if let Some(profile) = self.profiles.get(&agent_id) {
            let latency = profile.simulate_latency() * self.congestion_factor;

            // Record in history
            self.latency_history.push((current_timestamp_ns(), latency));

            // Keep limited history
            if self.latency_history.len() > 10000 {
                self.latency_history.remove(0);
            }

            Some(latency)
        } else {
            None
        }
    }

    /// Update network congestion factor
    pub fn update_congestion(&mut self, congestion_factor: f64) {
        self.congestion_factor = congestion_factor.clamp(0.5, 5.0);
    }

    /// Get latency statistics
    pub fn latency_stats(&self) -> LatencyStatistics {
        if self.latency_history.is_empty() {
            return LatencyStatistics::default();
        }

        let latencies: Vec<f64> = self.latency_history.iter().map(|(_, l)| *l).collect();

        let mean = latencies.iter().sum::<f64>() / latencies.len() as f64;

        let mut sorted = latencies.clone();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());

        let p50 = sorted[sorted.len() * 50 / 100];
        let p95 = sorted[sorted.len() * 95 / 100];
        let p99 = sorted[sorted.len() * 99 / 100];
        let min = sorted.first().copied().unwrap_or(0.0);
        let max = sorted.last().copied().unwrap_or(0.0);

        LatencyStatistics {
            mean,
            median: p50,
            p50,
            p95,
            p99,
            min,
            max,
            sample_count: latencies.len(),
        }
    }

    /// Clear latency history
    pub fn clear_history(&mut self) {
        self.latency_history.clear();
    }
}

/// Latency statistics
#[derive(Debug, Clone, Default)]
pub struct LatencyStatistics {
    pub mean: f64,
    pub median: f64,
    pub p50: f64,
    pub p95: f64,
    pub p99: f64,
    pub min: f64,
    pub max: f64,
    pub sample_count: usize,
}

/// Get current timestamp in nanoseconds
fn current_timestamp_ns() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_latency_profile_creation() {
        let hft = LatencyProfile::hft_profile();
        assert_eq!(hft.mean_latency_us, 1.0);
        assert!(hft.std_dev_us > 0.0);
    }

    #[test]
    fn test_latency_simulation() {
        let profile = LatencyProfile::hft_profile();
        let latency = profile.simulate_latency();
        assert!(latency >= 0.0);
        assert!(latency <= profile.max_latency_us);
    }

    #[test]
    fn test_latency_simulator() {
        let mut simulator = LatencySimulator::new();
        simulator.register_agent(1, LatencyProfile::hft_profile());

        let latency = simulator.simulate_agent_latency(1);
        assert!(latency.is_some());

        let stats = simulator.latency_stats();
        assert_eq!(stats.sample_count, 1);
    }
}
