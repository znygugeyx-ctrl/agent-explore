"""D2L 推理封装：internalize → generate → reset。

Usage:
    from d2l_wrapper import D2LModel
    model = D2LModel("checkpoints/qwen_4b_d2l/checkpoint-20000/pytorch_model.bin")
    answer = model.ask("document text here", "What is the answer?")

Long-context handling:
- 46GB L40S can fit the 4B model + one chunk of up to ~4K tokens through the
  context encoder. Longer contexts are split into chunks ≤max_ctx_chunk_len and
  processed **one chunk at a time** through the ctx_encoder; the per-chunk
  features are concatenated along the batch dim and then the aggregator
  processes them (iterative_mode=True, so one layer at a time).
- This matches the paper's chunking philosophy but trades throughput for memory.
"""
from math import ceil

import torch
from ctx_to_lora.data.processing import tokenize_ctx_text
from ctx_to_lora.model_loading import get_tokenizer
from ctx_to_lora.modeling.hypernet import ModulatedPretrainedModel


class D2LModel:
    def __init__(
        self,
        checkpoint_path: str,
        max_new_tokens: int = 256,
        max_ctx_chunk_len: int = 4096,
    ):
        state_dict = torch.load(checkpoint_path, weights_only=False)
        self.model = ModulatedPretrainedModel.from_state_dict(
            state_dict, train=False, use_sequence_packing=False
        )
        # Iterative mode: process aggregator one layer at a time (36x less peak).
        self.model.enable_iterative_mode(True)
        self.tokenizer = get_tokenizer(self.model.base_model.name_or_path)
        self.ctx_tokenizer = get_tokenizer(
            self.model.ctx_encoder.base_model.name_or_path
        )
        if self.ctx_tokenizer.pad_token_id is None:
            self.ctx_tokenizer.pad_token_id = self.ctx_tokenizer.eos_token_id
        self.max_new_tokens = max_new_tokens
        self.max_ctx_chunk_len = max_ctx_chunk_len
        self.base_model_name = self.model.base_model.name_or_path

    @torch.no_grad()
    def _encode_chunks(self, chunk_ids: list[list[int]]):
        """Process chunks one at a time through ctx_encoder, then concatenate
        along the sequence dim (bs=1) so the aggregator sees one long sequence.
        Returns features [1, num_layers, total_len, feature_dim] and a matching
        attn_mask [1, total_len]."""
        device = self.model.device
        features_list = []  # each: [1, num_layers, chunk_len, feature_dim]
        for c in chunk_ids:
            ids = torch.tensor([list(c)], device=device)
            mask = torch.ones_like(ids)
            feats = self.model.ctx_encoder(input_ids=ids, attention_mask=mask)
            # Move to CPU to free GPU memory before next chunk
            features_list.append(feats.cpu())
            torch.cuda.empty_cache()
        # Concatenate along seq dim, move back to GPU
        features = torch.cat(features_list, dim=2).to(device)
        total_len = features.shape[2]
        attn_mask = torch.ones((1, total_len), device=device, dtype=torch.long)
        return features, attn_mask

    def _internalize_chunked(self, context: str):
        """Split context into chunks <= max_ctx_chunk_len tokens, then internalize."""
        full_ids = tokenize_ctx_text(
            dict(context=[context]), self.ctx_tokenizer
        )["ctx_ids"][0]
        total_len = len(full_ids)

        if total_len <= self.max_ctx_chunk_len:
            # Short enough: use simple path (single chunk, no splitting)
            return self.model._internalize_from_ids(
                torch.tensor([full_ids], device=self.model.device)
            )

        # Chunk into roughly equal pieces, each <= max_ctx_chunk_len
        n_chunks = ceil(total_len / self.max_ctx_chunk_len)
        avg_len = ceil(total_len / n_chunks)
        chunks = [
            full_ids[i : i + avg_len] for i in range(0, total_len, avg_len)
        ]

        # Encode chunks sequentially (keeps peak memory low)
        features, attn_mask = self._encode_chunks(chunks)

        # Call hypernet directly with pre-computed features, bypassing ctx_encoder
        self.model.patch_lora_forward()
        with torch.no_grad():
            flat_loras, flat_layernorms = self.model.hypernet.forward(
                features, attn_mask, position_ids=None
            )
        generated_loras = self.model.hypernet._to_lora_dict(flat_loras)
        self.model.generated_loras = generated_loras

    def ask(self, context: str, question: str) -> str:
        self._internalize_chunked(context)
        try:
            chat_ids = self.tokenizer.apply_chat_template(
                [{"role": "user", "content": question}],
                add_generation_prompt=True,
                return_tensors="pt",
            ).to(self.model.device)
            output = self.model.generate(
                input_ids=chat_ids,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )
            answer = self.tokenizer.decode(
                output[0][chat_ids.shape[1]:], skip_special_tokens=True
            )
        finally:
            self.model.reset()
            torch.cuda.empty_cache()
        return answer.strip()

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))
