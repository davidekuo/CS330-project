import argparse
import random
import time
import numpy as np
import torch
from torch.utils.tensorboard import SummaryWriter
from data_loader import DataGenerator
from tqdm import tqdm
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Union, Tuple
from transformers import BertConfig
from transformers.models.bert.modeling_bert import (
    BertEncoder,
    BertPreTrainedModel,
)


class SmilesBertModel(BertPreTrainedModel):
    """Multi-headed BERT-based model for SMILES sequences."""
    def __init__(self, config):
        super().__init__(config)
        self.config = config
        self.k = config.k
        self.batch_size = config.batch_size

        self.encoder = BertEncoder(config)
        self.linear = nn.Linear(config.hidden_size, 2)

        # Initialize weights and apply final processing
        self.post_init()

    def forward(
        self,
        input_images: torch.Tensor,
        raw_input_labels: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> Tuple[torch.Tensor]:
        # We can provide a self-attention mask of dimensions [batch_size, from_seq_length, to_seq_length]
        # ourselves in which case we just need to make it broadcastable to all heads.
        extended_attention_mask: torch.Tensor = self.get_extended_attention_mask(attention_mask, (input_images.shape[0], input_images.shape[-1]))

        input_labels = raw_input_labels.clone()
        input_labels[:, -1, :, :] = 0
        input_images_and_labels = torch.cat((input_images, input_labels), -1)
        B, K_1, N, D = input_images_and_labels.shape
        input_images_and_labels = input_images_and_labels.reshape((B, -1, D))

        encoder_outputs = self.encoder(
            input_images_and_labels,  # (batch, seq, dim)
            attention_mask=extended_attention_mask,
            head_mask=None,
            encoder_hidden_states=None,
            encoder_attention_mask=None,
            past_key_values=None,
            use_cache=self.config.use_cache,
            output_attentions=False,
            output_hidden_states=False,
            return_dict=False,
        )
        sequence_output = encoder_outputs[0]

        sequence_output = torch.reshape(sequence_output,[self.batch_size, self.k + 1, 2, -1])
        query_embeddings = sequence_output[:, -1, :, :]
        query_labels = raw_input_labels[:, -1, :, :]

        pred = self.linear(query_embeddings)
        pred = F.sigmoid(pred)

        loss = F.binary_cross_entropy(pred, query_labels)

        return loss, pred