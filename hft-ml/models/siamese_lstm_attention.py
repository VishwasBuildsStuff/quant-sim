"""
Siamese LSTM + Multi-Head Attention for LOB Prediction
Architecture:
  - Two parallel LSTM branches (bid side & ask side) with shared weights
  - Concatenate -> Multi-Head Attention -> Dense output
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Tuple


class SiameseLSTMAttention(nn.Module):
    """
    Siamese LSTM with attention for LOB-based prediction
    
    Bid and Ask sides processed separately with shared LSTM weights
    """
    
    def __init__(self,
                 n_levels: int = 10,
                 lstm_hidden: int = 128,
                 lstm_layers: int = 2,
                 n_attention_heads: int = 8,
                 attention_dim: int = 256,
                 dropout: float = 0.2,
                 n_classes: int = 3):
        super().__init__()
        
        self.n_levels = n_levels
        self.lstm_hidden = lstm_hidden
        
        # Shared LSTM for bid and ask sides
        self.bid_lstm = nn.LSTM(
            input_size=n_levels * 2,  # prices + volumes
            hidden_size=lstm_hidden,
            num_layers=lstm_layers,
            batch_first=True,
            dropout=dropout if lstm_layers > 1 else 0,
            bidirectional=True
        )
        
        # Ask side uses same weights (siamese)
        self.ask_lstm = self.bid_lstm  # Weight sharing
        
        # Multi-Head Attention
        self.attention = nn.MultiheadAttention(
            embed_dim=lstm_hidden * 2,  # bidirectional
            num_heads=n_attention_heads,
            dropout=0.1,
            batch_first=True
        )
        self.attention_norm = nn.LayerNorm(lstm_hidden * 2)
        
        # Projection layers
        self.bid_projection = nn.Linear(lstm_hidden * 2, attention_dim)
        self.ask_projection = nn.Linear(lstm_hidden * 2, attention_dim)
        
        # Output layers
        combined_dim = attention_dim * 2
        self.output_network = nn.Sequential(
            nn.Linear(combined_dim, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(dropout * 0.5)
        )
        
        # Multi-task heads
        self.class_head = nn.Linear(128, n_classes)
        self.reg_head = nn.Linear(128, 1)
        self.vol_head = nn.Sequential(
            nn.Linear(128, 1),
            nn.Softplus()
        )
        
        self._init_weights()
    
    def _init_weights(self):
        """Initialize weights using Xavier uniform for Linear layers"""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.LSTM):
                for name, param in module.named_parameters():
                    if 'weight' in name:
                        nn.init.orthogonal_(param)
                    elif 'bias' in name:
                        nn.init.zeros_(param)
    
    def forward(self, bid_input: torch.Tensor, ask_input: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Args:
            bid_input: (batch, seq_len, n_levels*2) - bid prices + volumes
            ask_input: (batch, seq_len, n_levels*2) - ask prices + volumes
        
        Returns:
            Dict with classification, regression, volatility outputs and intermediate features
        """
        batch_size = bid_input.shape[0]
        
        # === SIAMESE LSTM ===
        bid_out, _ = self.bid_lstm(bid_input)  # (batch, seq_len, lstm_hidden*2)
        ask_out, _ = self.ask_lstm(ask_input)  # Shared weights
        
        # === CROSS-ATTENTION ===
        # Bid attends to Ask and vice versa
        bid_attended, _ = self.attention(
            query=bid_out,
            key=ask_out,
            value=ask_out
        )
        ask_attended, _ = self.attention(
            query=ask_out,
            key=bid_out,
            value=bid_out
        )
        
        # Residual connections
        bid_attended = self.attention_norm(bid_out + bid_attended)
        ask_attended = self.attention_norm(ask_out + ask_attended)
        
        # Use last timestep
        bid_final = bid_attended[:, -1, :]  # (batch, lstm_hidden*2)
        ask_final = ask_attended[:, -1, :]
        
        # Project to common space
        bid_proj = self.bid_projection(bid_final)
        ask_proj = self.ask_projection(ask_final)
        
        # Combine
        combined = torch.cat([bid_proj, ask_proj], dim=1)
        
        # Output network
        features = self.output_network(combined)
        
        # Multi-task outputs
        class_logits = self.class_head(features)
        reg_output = self.reg_head(features).squeeze(-1)
        vol_output = self.vol_head(features).squeeze(-1)
        
        return {
            'classification': class_logits,
            'regression': reg_output,
            'volatility': vol_output,
            'bid_features': bid_final,
            'ask_features': ask_final
        }
