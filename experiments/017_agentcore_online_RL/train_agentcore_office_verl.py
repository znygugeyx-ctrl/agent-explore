"""Train an office agent on OfficeBench using Verl backend + AgentCore remote runtime.

The agent runs inside an AgentCore container (strands_officebench_agent) with 21
office tools (calendar/email/excel/word/pdf/ocr) and calls back to the
rllm-model-gateway for model inference. The gateway captures all traces
(token IDs, logprobs) while the agent returns only the reward (binary: all
evaluation checks pass -> 1.0 else 0.0).

Usage:
    # First prepare data (after preprocess.py uploaded tasks to S3 and make_split.py ran):
    python -m examples.agentcore_office.prepare_officebench_data --split officebench_split.json

    # Then train:
    bash examples/agentcore_office/train_agentcore_office_fsdp.sh
"""

import hydra

from rllm.data.dataset import DatasetRegistry
from rllm.trainer import AgentTrainer


@hydra.main(config_path="pkg://rllm.trainer.config", config_name="unified", version_base=None)
def main(config):
    import os
    _sfx = os.environ.get("DATASET_SUFFIX", "")
    train_dataset = DatasetRegistry.load_dataset("officebench_train"+_sfx, "train")
    test_dataset = DatasetRegistry.load_dataset("officebench_test"+_sfx, "test")

    trainer = AgentTrainer(
        backend="verl",
        config=config,
        train_dataset=train_dataset,
        val_dataset=test_dataset,
    )
    trainer.train()


if __name__ == "__main__":
    main()
