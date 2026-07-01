#!/usr/bin/env bash
# FSDP OfficeBench training for 4x A10G (g5.24xlarge) — exp 017 Phase O.
# Derived from train_agentcore_math_fsdp.sh (verified Phase 3 stack).
# Changes vs math: dataset=officebench_*, office runtime ARN, larger context
# (21 tool schemas + multi-turn + file contents), longer session_timeout.
#
# Env knobs:
#   STEPS=1   -> smoke (single training step), default. STEPS=0 -> full epoch.
#   STEPS=N   -> N steps (e.g. STEPS=20 for short-train Phase O-3).
set -eux

set -a && source examples/agentcore_office/.env && set +a
export VLLM_ALLREDUCE_USE_SYMM_MEM=0
export VLLM_USE_V1=1
rm -f /tmp/rl-colocate-zmq-*.sock

MODEL_PATH=Qwen/Qwen3-4B-Instruct-2507
STEPS="${STEPS:-1}"

STEP_OVERRIDE=""
if [ "$STEPS" != "0" ]; then
  STEP_OVERRIDE="trainer.total_training_steps=${STEPS}"
fi

python -m examples.agentcore_office.train_agentcore_office_verl \
    rllm/backend=verl \
    algorithm.adv_estimator=grpo \
    algorithm.norm_adv_by_std_in_grpo=true \
    rllm.algorithm.rollout_correction.bypass_mode=true \
    data.train_batch_size=8 \
    data.val_batch_size=64 \
    data.max_prompt_length=8192 \
    data.max_response_length=2048 \
    +model.name=$MODEL_PATH \
    actor_rollout_ref.model.path=$MODEL_PATH \
    actor_rollout_ref.model.lora.rank=16 \
    actor_rollout_ref.model.lora.alpha=16 \
    actor_rollout_ref.model.lora.merge=true \
    actor_rollout_ref.model.enable_gradient_checkpointing=True \
    actor_rollout_ref.model.use_remove_padding=True \
    actor_rollout_ref.hybrid_engine=True \
    actor_rollout_ref.actor.optim.lr=2e-5 \
    actor_rollout_ref.actor.ppo_mini_batch_size=8 \
    actor_rollout_ref.actor.use_dynamic_bsz=True \
    actor_rollout_ref.actor.ppo_max_token_len_per_gpu=12288 \
    actor_rollout_ref.actor.fsdp_config.param_offload=True \
    actor_rollout_ref.actor.fsdp_config.optimizer_offload=True \
    actor_rollout_ref.actor.use_kl_loss=False \
    actor_rollout_ref.actor.loss_agg_mode=seq-mean-token-sum \
    actor_rollout_ref.rollout.tensor_model_parallel_size=2 \
    actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=1 \
    actor_rollout_ref.rollout.name=vllm \
    actor_rollout_ref.rollout.mode=async \
    +actor_rollout_ref.rollout.engine_kwargs.vllm.enable_auto_tool_choice=true \
    +actor_rollout_ref.rollout.engine_kwargs.vllm.tool_call_parser=hermes \
    +actor_rollout_ref.rollout.engine_kwargs.vllm.tokenizer_mode=slow \
    actor_rollout_ref.rollout.max_model_len=12288 \
    actor_rollout_ref.rollout.enforce_eager=True \
    actor_rollout_ref.rollout.temperature=1.0 \
    actor_rollout_ref.rollout.gpu_memory_utilization=0.6 \
    actor_rollout_ref.rollout.n=4 \
    actor_rollout_ref.rollout.val_kwargs.n=1 \
    actor_rollout_ref.rollout.val_kwargs.temperature=0.6 \
    actor_rollout_ref.rollout.val_kwargs.do_sample=True \
    actor_rollout_ref.ref.log_prob_micro_batch_size_per_gpu=1 \
    actor_rollout_ref.ref.fsdp_config.param_offload=True \
    trainer.logger="['console','wandb']" \
    trainer.project_name=agentcore-office \
    trainer.experiment_name=exp017-officebench-fsdp-4xa10g-4b \
    trainer.val_before_train=false \
    trainer.n_gpus_per_node=4 \
    trainer.nnodes=1 \
    trainer.save_freq=100 \
    trainer.test_freq=1000 \
    trainer.total_epochs=1 \
    trainer.default_hdfs_dir=null \
    trainer.resume_mode=disable \
    ${STEP_OVERRIDE} \
    rllm.remote_runtime.enabled=true \
    rllm.remote_runtime.backend=agentcore \
    rllm.remote_runtime.agentcore.agent_runtime_arn=$AGENTCORE_AGENT_ARN \
    rllm.remote_runtime.agentcore.s3_bucket=$AGENTCORE_S3_BUCKET \
    rllm.remote_runtime.agentcore.tps_limit=25 \
    rllm.remote_runtime.session_timeout=600 \
    rllm.gateway.tunnel=cloudflared
