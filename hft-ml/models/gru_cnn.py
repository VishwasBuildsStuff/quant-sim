"""
GRU-CNN Hybrid Model for LOB-based Price Prediction
Architecture:
  - 1D CNN layers for local LOB pattern extraction
  - Stacked GRU layers for sequential dependencies
  - Multi-task output: classification + regression + volatility
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Optional, Dict


class GRUCNNModel(nn.Module):
    """
    Hybrid GRU-CNN for HFT prediction
    
    Input: (batch, seq_len, n_features)
    Output: 
      - classification: (batch, 3) probabilities for down/unchanged/up
      - regression: (batch,) predicted mid-price change
      - volatility: (batch,) predicted realized vol
    """
    
    def __init__(self, 
                 n_features: int = 40,
                 seq_len: int = 100,
                 n_levels: int = 10,
                 cnn_channels: list = [32, 64, 128],
                 cnn_kernel_sizes: list = [3, 3, 3],
                 gru_hidden: int = 128,
                 gru_layers: int = 2,
                 gru_dropout: float = 0.2,
                 n_classes: int = 3,
                 use_attention: bool = True,
                 n_attention_heads: int = 4):
        super().__init__()
        
        self.n_features = n_features
        self.seq_len = seq_len
        self.gru_hidden = gru_hidden
        self.use_attention = use_attention
        
        # === CNN BRANCH (Local pattern extraction) ===
        cnn_layers = []
        
        for i, (out_ch, ksize) in enumerate(zip(cnn_channels, cnn_kernel_sizes)):
            cnn_layers.extend([
                nn.Conv1d(
                    in_channels=n_features if i == 0 else cnn_channels[i-1],
                    out_channels=out_ch,
                    kernel_size=ksize,
                    padding=ksize // 2
                ),
                nn.BatchNorm1d(out_ch),
                nn.ReLU(),
                nn.MaxPool1d(2)
            ])
        
        self.cnn = nn.Sequential(*cnn_layers)
        # Calculate CNN output dimension after pooling
        cnn_output_dim = self.seq_len
        for _ in cnn_channels:
            cnn_output_dim = cnn_output_dim // 2
        cnn_output_dim = max(1, cnn_output_dim)
        cnn_flat_dim = cnn_channels[-1] * cnn_output_dim
        
        # === GRU BRANCH (Sequential dependencies) ===
        self.gru = nn.GRU(
            input_size=n_features,
            hidden_size=gru_hidden,
            num_layers=gru_layers,
            batch_first=True,
            dropout=gru_dropout if gru_layers > 1 else 0,
            bidirectional=True
        )
        
        # === MULTI-HEAD ATTENTION ===
        if use_attention:
            self.attention = nn.MultiheadAttention(
                embed_dim=gru_hidden * 2,  # bidirectional
                num_heads=n_attention_heads,
                dropout=0.1,
                batch_first=True
            )
            self.attention_norm = nn.LayerNorm(gru_hidden * 2)
        
        # === FUSION LAYER ===
        fusion_dim = cnn_flat_dim + gru_hidden * 2
        self.fusion = nn.Sequential(
            nn.Linear(fusion_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(0.2)
        )
        
        # === MULTI-TASK OUTPUTS ===
        # Classification head (price direction)
        self.classifier = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, n_classes)
        )
        
        # Regression head (price change magnitude)
        self.regressor = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1)
        )
        
        # Volatility head
        self.vol_predictor = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1),
            nn.Softplus()  # Ensure positive volatility
        )
        
        # Initialize weights
        self._init_weights()
    
    def _init_weights(self):
        """Xavier initialization for better convergence"""
        for module in self.modules():
            if isinstance(module, (nn.Linear, nn.Conv1d)):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.GRU):
                for name, param in module.named_parameters():
                    if 'weight' in name:
                        nn.init.orthogonal_(param)
                    elif 'bias' in name:
                        nn.init.zeros_(param)
    
    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, n_features)
        Returns:
            dict with classification, regression, volatility outputs
        """
        batch_size, seq_len, n_features = x.shape
        
        # === CNN FORWARD ===
        # Conv1d expects (batch, channels, seq_len)
        x_cnn = x.permute(0, 2, 1)  # (batch, n_features, seq_len)
        
        # Apply CNN - treat all features as channels
        cnn_out = self.cnn(x_cnn)  # (batch, cnn_channels[-1], reduced_seq_len)
        cnn_flat = cnn_out.view(batch_size, -1)  # Flatten all CNN outputs
        
        # === GRU FORWARD ===
        x_gru, _ = self.gru(x)  # (batch, seq_len, gru_hidden*2)
        
        # === ATTENTION ===
        if self.use_attention:
            attn_output, _ = self.attention(x_gru, x_gru, x_gru)
            x_gru = self.attention_norm(x_gru + attn_output)
        
        # Use last hidden state
        gru_out = x_gru[:, -1, :]  # (batch, gru_hidden*2)
        
        # === FUSION ===
        combined = torch.cat([cnn_flat, gru_out], dim=1)
        fused = self.fusion(combined)
        
        # === MULTI-TASK OUTPUT ===
        class_logits = self.classifier(fused)  # (batch, n_classes)
        reg_output = self.regressor(fused).squeeze(-1)  # (batch,)
        vol_output = self.vol_predictor(fused).squeeze(-1)  # (batch,)
        
        return {
            'classification': class_logits,
            'regression': reg_output,
            'volatility': vol_output,
            'fused_features': fused
        }


class FocalLoss(nn.Module):
    """
    Focal Loss for handling class imbalance
    Focuses learning on hard examples
    """
    
    def __init__(self, alpha: float = 0.25, gamma: float = 2.0, reduction: str = 'mean'):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction
    
    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """
        Args:
            inputs: (batch, n_classes) logits
            targets: (batch,) class indices
        """
        ce_loss = F.cross_entropy(inputs, targets, reduction='none')
        pt = torch.exp(-ce_loss)
        focal_loss = self.alpha * (1 - pt) ** self.gamma * ce_loss
        
        if self.reduction == 'mean':
            return focal_loss.mean()
        elif self.reduction == 'sum':
            return focal_loss.sum()
        return focal_loss


class HuberLoss(nn.Module):
    """Huber loss for robust regression"""
    
    def __init__(self, delta: float = 1.0):
        super().__init__()
        self.delta = delta
    
    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        return F.huber_loss(inputs, targets, delta=self.delta, reduction='mean')


class MultiTaskLoss(nn.Module):
    """
    Combined loss for multi-task learning
    Dynamically weights each task
    """
    
    def __init__(self, 
                 class_weight: float = 1.0,
                 reg_weight: float = 0.5,
                 vol_weight: float = 0.3,
                 focal_alpha: float = 0.25,
                 focal_gamma: float = 2.0,
                 huber_delta: float = 1.0):
        super().__init__()
        
        self.class_weight = class_weight
        self.reg_weight = reg_weight
        self.vol_weight = vol_weight
        
        self.focal_loss = FocalLoss(alpha=focal_alpha, gamma=focal_gamma)
        self.huber_loss = HuberLoss(delta=huber_delta)
        self.mse_loss = nn.MSELoss()
        
        # Learnable uncertainty weights (Kendall et al. 2018)
        self.log_var_class = nn.Parameter(torch.zeros(1))
        self.log_var_reg = nn.Parameter(torch.zeros(1))
        self.log_var_vol = nn.Parameter(torch.zeros(1))
    
    def forward(self, 
                outputs: Dict[str, torch.Tensor],
                targets: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Compute multi-task loss with uncertainty weighting
        """
        # Classification loss
        loss_class = self.focal_loss(outputs['classification'], targets['classification'])
        loss_class = torch.exp(-self.log_var_class) * loss_class + self.log_var_class
        
        # Regression loss
        loss_reg = self.huber_loss(outputs['regression'], targets['regression'])
        loss_reg = torch.exp(-self.log_var_reg) * loss_reg + self.log_var_reg
        
        # Volatility loss
        loss_vol = self.mse_loss(outputs['volatility'], targets['volatility'])
        loss_vol = torch.exp(-self.log_var_vol) * loss_vol + self.log_var_vol
        
        total_loss = (self.class_weight * loss_class + 
                     self.reg_weight * loss_reg + 
                     self.vol_weight * loss_vol)
        
        return total_loss


def count_parameters(model: nn.Module) -> int:
    """Count trainable parameters"""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
