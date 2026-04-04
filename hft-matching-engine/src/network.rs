/// Network module - FIX protocol simulation
/// Emulates Financial Information eXchange protocol messaging

use crate::types::*;
use serde::{Deserialize, Serialize};

/// FIX Protocol message types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FIXMessageType {
    Heartbeat,
    TestRequest,
    ResendRequest,
    Reject,
    SequenceReset,
    Logout,
    ExecutionReport,
    OrderCancelReject,
    OrderCancelAck,
    NewOrderSingle,
    MarketDataSnapshotFull,
    MarketDataIncremental,
}

/// FIX Message wrapper
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FIXMessage {
    pub msg_type: FIXMessageType,
    pub msg_seq_num: u64,
    pub sender_comp_id: String,
    pub target_comp_id: String,
    pub sending_time: u64,
    pub payload: FIXPayload,
}

/// FIX Message payload variants
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FIXPayload {
    NewOrderSingle {
        cl_ord_id: String,
        symbol: String,
        side: Side,
        transact_time: u64,
        order_qty: Quantity,
        ord_type: OrderType,
        price: Option<Price>,
        time_in_force: Option<TimeInForce>,
    },
    ExecutionReport {
        order_id: OrderId,
        exec_type: ExecutionType,
        ord_status: OrderStatus,
        symbol: String,
        side: Side,
        leaves_qty: Quantity,
        cum_qty: Quantity,
        avg_px: Option<Price>,
        last_qty: Option<Quantity>,
        last_px: Option<Price>,
    },
    OrderCancelRequest {
        orig_cl_ord_id: String,
        symbol: String,
        side: Side,
        cancel_transact_time: u64,
    },
    MarketData {
        symbol: String,
        bids: Vec<(Price, Quantity)>,
        asks: Vec<(Price, Quantity)>,
        trades: Vec<Trade>,
    },
    Empty,
}

/// Execution type for FIX messages
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ExecutionType {
    New,
    PartialFill,
    Fill,
    DoneForDay,
    Canceled,
    Replaced,
    Rejected,
}

/// FIX Session manager
pub struct FIXSession {
    sender_comp_id: String,
    target_comp_id: String,
    outgoing_seq_num: u64,
    incoming_seq_num: u64,
    heartbeat_interval_ms: u64,
    last_heartbeat: u64,
}

impl FIXSession {
    pub fn new(sender_comp_id: String, target_comp_id: String, heartbeat_interval_ms: u64) -> Self {
        Self {
            sender_comp_id,
            target_comp_id,
            outgoing_seq_num: 1,
            incoming_seq_num: 1,
            heartbeat_interval_ms,
            last_heartbeat: current_timestamp_ns(),
        }
    }

    /// Create a new order single message
    pub fn create_new_order_single(
        &mut self,
        order: &Order,
    ) -> FIXMessage {
        let msg = FIXMessage {
            msg_type: FIXMessageType::NewOrderSingle,
            msg_seq_num: self.outgoing_seq_num,
            sender_comp_id: self.sender_comp_id.clone(),
            target_comp_id: self.target_comp_id.clone(),
            sending_time: current_timestamp_ns(),
            payload: FIXPayload::NewOrderSingle {
                cl_ord_id: order.order_id.to_string(),
                symbol: "TEST".to_string(), // Would come from instrument
                side: order.side,
                transact_time: order.timestamp,
                order_qty: order.quantity,
                ord_type: order.order_type,
                price: Some(order.price),
                time_in_force: Some(order.time_in_force),
            },
        };

        self.outgoing_seq_num += 1;
        msg
    }

    /// Create execution report
    pub fn create_execution_report(
        &mut self,
        order: &Order,
        exec_type: ExecutionType,
        filled_qty: Quantity,
        avg_px: Option<Price>,
        last_qty: Option<Quantity>,
        last_px: Option<Price>,
    ) -> FIXMessage {
        let msg = FIXMessage {
            msg_type: FIXMessageType::ExecutionReport,
            msg_seq_num: self.outgoing_seq_num,
            sender_comp_id: self.sender_comp_id.clone(),
            target_comp_id: self.target_comp_id.clone(),
            sending_time: current_timestamp_ns(),
            payload: FIXPayload::ExecutionReport {
                order_id: order.order_id,
                exec_type,
                ord_status: order.status,
                symbol: "TEST".to_string(),
                side: order.side,
                leaves_qty: order.remaining_qty,
                cum_qty: order.quantity - order.remaining_qty,
                avg_px,
                last_qty,
                last_px,
            },
        };

        self.outgoing_seq_num += 1;
        msg
    }

    /// Create market data snapshot
    pub fn create_market_data_snapshot(
        &mut self,
        snapshot: &OrderBookSnapshot,
    ) -> FIXMessage {
        let msg = FIXMessage {
            msg_type: FIXMessageType::MarketDataSnapshotFull,
            msg_seq_num: self.outgoing_seq_num,
            sender_comp_id: self.sender_comp_id.clone(),
            target_comp_id: self.target_comp_id.clone(),
            sending_time: current_timestamp_ns(),
            payload: FIXPayload::MarketData {
                symbol: "TEST".to_string(),
                bids: snapshot.bids.clone(),
                asks: snapshot.asks.clone(),
                trades: Vec::new(),
            },
        };

        self.outgoing_seq_num += 1;
        msg
    }

    /// Validate incoming message sequence
    pub fn validate_sequence(&mut self, expected_seq: u64) -> Result<bool, String> {
        if expected_seq == self.incoming_seq_num {
            self.incoming_seq_num += 1;
            Ok(true)
        } else if expected_seq < self.incoming_seq_num {
            Err(format!(
                "Duplicate message: expected {}, got {}",
                self.incoming_seq_num, expected_seq
            ))
        } else {
            Err(format!(
                "Gap in sequence: expected {}, got {}",
                self.incoming_seq_num, expected_seq
            ))
        }
    }

    /// Check if heartbeat is required
    pub fn heartbeat_required(&self) -> bool {
        current_timestamp_ns() - self.last_heartbeat > self.heartbeat_interval_ms * 1_000_000
    }

    /// Send heartbeat
    pub fn create_heartbeat(&mut self) -> FIXMessage {
        self.last_heartbeat = current_timestamp_ns();
        FIXMessage {
            msg_type: FIXMessageType::Heartbeat,
            msg_seq_num: self.outgoing_seq_num,
            sender_comp_id: self.sender_comp_id.clone(),
            target_comp_id: self.target_comp_id.clone(),
            sending_time: current_timestamp_ns(),
            payload: FIXPayload::Empty,
        }
    }
}

/// FIX Protocol server simulation
pub struct FIXServer {
    sessions: std::collections::HashMap<String, FIXSession>,
}

impl FIXServer {
    pub fn new() -> Self {
        Self {
            sessions: std::collections::HashMap::new(),
        }
    }

    /// Create new session
    pub fn create_session(
        &mut self,
        sender_comp_id: String,
        target_comp_id: String,
        heartbeat_interval_ms: u64,
    ) {
        let session = FIXSession::new(sender_comp_id.clone(), target_comp_id.clone(), heartbeat_interval_ms);
        self.sessions.insert(sender_comp_id, session);
    }

    /// Get session
    pub fn get_session(&mut self, sender_comp_id: &str) -> Option<&mut FIXSession> {
        self.sessions.get_mut(sender_comp_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fix_session_creation() {
        let session = FIXSession::new("SENDER".to_string(), "TARGET".to_string(), 30000);
        assert_eq!(session.outgoing_seq_num, 1);
        assert_eq!(session.incoming_seq_num, 1);
    }

    #[test]
    fn test_fix_message_sequence() {
        let mut session = FIXSession::new("SENDER".to_string(), "TARGET".to_string(), 30000);
        let order = Order::new(1, 1, 1, Side::Buy, OrderType::Limit, 10000, 100, TimeInForce::GTC);

        let msg = session.create_new_order_single(&order);
        assert_eq!(msg.msg_seq_num, 1);
        assert_eq!(session.outgoing_seq_num, 2);
    }
}
