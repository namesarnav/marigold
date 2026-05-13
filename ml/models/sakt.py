"""SAKT — Self-Attentive Knowledge Tracing (Pandey & Karypis, 2019).

Architecture, following the paper:

    keys/values <- embedding of past (skill, correctness) interactions + positional
    query       <- embedding of the skill being asked about
    multi-head self-attention with a causal mask
    residual + layer norm
    position-wise feedforward
    residual + layer norm
    linear -> sigmoid -> P(correct)

The query comes from the *exercise* embedding while keys and values come from
the *interaction* embedding. That asymmetry is the whole idea: "given that I am
being asked about skill S now, which of this student's past interactions are
relevant?"

Two properties that must hold or the model silently cheats — see
`ml/data/sequences.py` for how the tensors are laid out to guarantee them:

1. The queried skill's own correctness is never in the key/value sequence at a
   position the query can see.
2. The causal mask is strictly lower-triangular *inclusive of the diagonal*,
   because key position i holds the interaction at step i while query position i
   asks about step i+1. Attending to key i is attending to the past.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn

from ml.config import SAKT, SAKTConfig
from ml.data.sequences import PAD_ID


class SAKTModel(nn.Module):
    def __init__(self, n_skills: int, config: SAKTConfig = SAKT):
        super().__init__()
        self.n_skills = n_skills
        self.config = config

        # +1 on skills and 2*n+1 on interactions to reserve index 0 for padding.
        self.interaction_embedding = nn.Embedding(
            2 * n_skills + 1, config.d_model, padding_idx=PAD_ID
        )
        self.skill_embedding = nn.Embedding(
            n_skills + 1, config.d_model, padding_idx=PAD_ID
        )
        # Learned rather than sinusoidal, as in the paper: sequence positions
        # here mean "how many interactions ago", which has no reason to be
        # periodic.
        self.position_embedding = nn.Embedding(config.max_seq_len, config.d_model)

        self.attention = nn.MultiheadAttention(
            embed_dim=config.d_model,
            num_heads=config.n_heads,
            dropout=config.dropout,
            batch_first=True,
        )
        self.attn_norm = nn.LayerNorm(config.d_model)

        self.ffn = nn.Sequential(
            nn.Linear(config.d_model, config.ffn_hidden),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.ffn_hidden, config.d_model),
        )
        self.ffn_norm = nn.LayerNorm(config.d_model)
        self.dropout = nn.Dropout(config.dropout)

        self.output = nn.Linear(config.d_model, 1)

        self._init_weights()

    def _init_weights(self) -> None:
        for embedding in (
            self.interaction_embedding,
            self.skill_embedding,
            self.position_embedding,
        ):
            nn.init.normal_(embedding.weight, mean=0.0, std=0.02)
            if embedding.padding_idx is not None:
                with torch.no_grad():
                    embedding.weight[embedding.padding_idx].fill_(0.0)

    @staticmethod
    def causal_mask(seq_len: int, device: torch.device) -> torch.Tensor:
        """True where attention is *disallowed*.

        Position i may attend to key positions 0..i inclusive. Key i is the
        interaction at step i; query i asks about step i+1. So the diagonal is
        allowed — excluding it would throw away the single most informative
        interaction, the immediately preceding one.
        """
        return torch.triu(
            torch.ones(seq_len, seq_len, dtype=torch.bool, device=device), diagonal=1
        )

    def forward(
        self, past_interactions: torch.Tensor, query_skills: torch.Tensor
    ) -> torch.Tensor:
        """Return logits of shape (batch, seq_len).

        Sigmoid is applied by the loss (BCEWithLogits) or by the caller, not
        here, so training keeps the numerically stable fused path.
        """
        batch_size, seq_len = past_interactions.shape
        device = past_interactions.device

        positions = torch.arange(seq_len, device=device).unsqueeze(0)
        kv = self.interaction_embedding(past_interactions) + self.position_embedding(
            positions
        )
        kv = self.dropout(kv)
        query = self.dropout(self.skill_embedding(query_skills))

        # Padded key positions carry no information; masking them keeps their
        # (zeroed) embeddings from diluting the attention distribution.
        key_padding_mask = past_interactions == PAD_ID

        # A fully padded row would make every key invalid and produce NaNs from
        # the softmax. Windows are only emitted with at least one scored
        # position, so position 0 is always real — unmask it defensively.
        key_padding_mask = key_padding_mask.clone()
        key_padding_mask[:, 0] = False

        attended, _ = self.attention(
            query=query,
            key=kv,
            value=kv,
            attn_mask=self.causal_mask(seq_len, device),
            key_padding_mask=key_padding_mask,
            need_weights=False,
        )

        # Residual from the query: the paper's skip connection carries the
        # identity of the skill being asked about past the attention block, so
        # the output layer always knows which skill it is scoring.
        hidden = self.attn_norm(attended + query)
        hidden = self.ffn_norm(hidden + self.dropout(self.ffn(hidden)))

        return self.output(hidden).squeeze(-1)

    @torch.no_grad()
    def predict_proba(
        self, past_interactions: torch.Tensor, query_skills: torch.Tensor
    ) -> torch.Tensor:
        self.eval()
        return torch.sigmoid(self(past_interactions, query_skills))

    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


def positional_sanity_check(model: SAKTModel) -> None:
    """Assert the causal mask actually blocks the future.

    Runs a single forward pass twice, changing only interactions *after* the
    position of interest, and requires the prediction there to be unchanged.
    This catches an inverted or off-by-one mask, which is the failure that
    inflates AUC toward 0.99 while looking entirely plausible in the code.
    """
    model.eval()
    device = next(model.parameters()).device
    seq_len = min(16, model.config.max_seq_len)

    past = torch.randint(1, 2 * model.n_skills + 1, (1, seq_len), device=device)
    query = torch.randint(1, model.n_skills + 1, (1, seq_len), device=device)

    with torch.no_grad():
        baseline = model(past, query)

        tampered = past.clone()
        cut = seq_len // 2
        # Change everything strictly after `cut`.
        tampered[0, cut + 1 :] = torch.randint(
            1, 2 * model.n_skills + 1, (seq_len - cut - 1,), device=device
        )
        perturbed = model(tampered, query)

    if not torch.allclose(baseline[0, : cut + 1], perturbed[0, : cut + 1], atol=1e-5):
        raise AssertionError(
            "Causal mask is not blocking future interactions: predictions at "
            "positions <= cut changed when later inputs were modified."
        )
