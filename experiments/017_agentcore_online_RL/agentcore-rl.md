# 基于AWS agentcore的多轮在线强化学习实践

> 这篇文章是基于 AWS agentcore 的多轮在线强化学习训练实践。对于多轮强化学习，基础设施搭建是一个难点，需要满足以下条件：1.“隔离”：每一次rollout需要在隔离环境中操作，并且保证一致性。2.“并行”：通常会对一条数据并行进行多次rollout，并在执行完毕后干净地关闭它们。3.“Token保真”：需要获取Agent推理时产生的token ID以及对应的logprobs，否则trainer在重新分词时可能会偏移，造成推理与训练不一致。除此之外，“稳定性”“可观测性”等也是关键指标。AWS Agentcore的生产级能力正好能满足以上需求。

# 1. 基础设施结构

整个训练框架如下

![Screenshot 2026-06-27 at 21.52.36](/Users/zny/Library/Application Support/typora-user-images/Screenshot 2026-06-27 at 21.52.36.png)

主要包含以下组件：

## **Agentcore Runtime**: 

AWS提供的生产级serverless Agent运行时，每一次调用都会获得专属的 MicroVM，并且可以自动扩缩容，支持执行任意Agent框架和代码，能够访问外部网络以及AWS资源（如S3，Bedrock等）。Agentcore的设计与RL训练非常契合：

- **强扩缩能力**：支持同时启动数百个自定义Docker，rollout完毕后释放，不必为闲置资源付费 
- **强隔离**：每次rollout都可以确保环境一致且完全不影响其他rollout 
- **可观测性**：每个会话都会记录到AWS CloudWatch。在本文的训练中，Agentcore作为Agent的运行环境，加载运行环境与数据，执行工具调用，并执行程序化reward打分。

Agentcore具有的这些生产级属性，也正是RL rollout时所需的。

## **rllm-model-gateway**

rLLM库提供的一个FastAPI服务，agent 像调用普通 OpenAI 端点一样向它请求推理服务。gateway 在转发的同时捕获每次推理产生的 token ID 与对应 logprobs，按 session 记录成 trace。这样 trainer 可以直接复用这些 token，避免重新分词造成的推理与训练不一致。训练时 gateway 自动将 veRL 的 vLLM worker 注册为后端，无需手动管理。

## **S3存储**

AWS提供的存储服务，rollout的结果存放在这里。Agent 在 AgentCore 中执行完毕后，将对话轨迹、reward、状态码写入 S3。训练端通过轮询 S3 拿到结果。这种异步、解耦的设计让数百个并行 rollout 不必维持长连接，天然适配 AgentCore 的扩缩容与 RL 的大批量采样。

## **CloudWatch观测**

AgentCore 每个 session 的运行日志自动汇入 CloudWatch。当某次 rollout 异常（如工具调用报错、超时、输出截断），可直接定位到具体 session 排查，是大规模并行 rollout 下不可或缺的可观测手段。

## **EC2 (训练+推理)**

承载 rLLM trainer 的 GPU 实例（本文用 p4d.24xlarge，8×A100 40GB）。采用 collocated 模式：vLLM 推理引擎与 veRL FSDP 训练共享同一批 GPU，rollout 生成与策略更新交替进行，每步训练后将更新的 LoRA 权重同步回 vLLM。

## 运行过程

一次完整的 rollout 与训练过程如下：

- 训练端（EC2）发起 rollout 请求。
- AgentCore 为每条请求分配独立 MicroVM 并行执行 Agent，Agent 的每次推理都经 cloudflared tunnel 回流到 EC2 上的 gateway 与 vLLM。
- gateway 在转发途中捕获 token 与 logprob。
- Agent 执行完毕后程序化打分，并将结果写入 S3。
- 训练端轮询 S3 取回 rollout 与 reward，用 GRPO 更新 LoRA 权重并同步回 vLLM，进入下一轮。

![Screenshot 2026-06-30 at 21.46.45](/Users/zny/Library/Application Support/typora-user-images/Screenshot 2026-06-30 at 21.46.45.png)

# 2. 训练

参考文章：

> https://github.com/awslabs/agentcore-rl-toolkit/tree/main/examples
>
> https://rllm-project.com/post.html?post=agentcore_migrationbench.md
>
> https://github.com/rllm-org/rllm/tree/main/cookbooks/migrationbench

为了看看以上框架的实际运行效果，基于AWS搭建了完整的基础设施，基于p4d实例（8*A100 40GB），Qwen3-8B base model，分别跑了两个实验：

## 2.1 Math agent训练

**任务**：GSM8K 小学数学应用题，每题给一段文字描述，要求算出最终数值答案。Agent 在单轮内完成推理，可调用 calculator 工具做算术，最终输出答案。reward 为 exact-match 二值判定（答案正确得 1.0，否则 0.0），用代码进行验证。

**训练配置**：rollout TP=8、gpu_memory_utilization=0.6、LoRA rank=32、rollout.n=8、lr=5e-6。由于 Math 任务序列短，无需为显存做截断，因此放宽长度限制：max_prompt=1536、max_response=1024、max_model_len=4096。

**训练结果**：训练结果如下，reward 整体呈现上升收敛趋势，最终稳定在 1 左右。batch/solve_all 快速升到 1，clip_ratio 截断率均值小于 0.1，后期趋近于 0。advantage/fraction_zero（advantage 为 0 的样本占比）趋近于 1，这是因为训练后期每个样本的 8 次 rollout 结果基本都正确，组内优势为 0。

**总结**：Math 任务难度适中，8B 模型有足够的初始解题率，训练能起到效果。

![Screenshot 2026-06-30 at 18.03.00](/Users/zny/Library/Application Support/typora-user-images/Screenshot 2026-06-30 at 18.03.00.png)

## 2.2 OfficeBench agent训练

**任务**：OfficeBench包含300个自动化的办公任务，覆盖 calendar、email、Excel、Word、PDF、OCR 六类应用，难度按照需要协作的应用数量划分（single-app / two-app / three-app）。Agent需要根据任务多轮调用21个工具完成任务，直到完成。

**训练配置**：Agent在OfficeBench下的rollout长度明显增大，在 8*40GB 的显存配置下经常会出现OOM的情况。最终为了跑通训练，设置 rollout TP=8，将推理权重加载到全部 8 卡（每卡仅约 2GB），为权重同步节约出显存。并将 max_model_len设置为 7168（原12288），超出长度则截断。通过以上两个设置控制显存占用。另外，为了让模型逐渐适应难度，采用了课程学习的思想，先在简单的任务上训练，训练后期再切换到较难的任务。

**训练结果**：如下图所示，reward 曲线一直在震荡，没有明显的上升趋势。prompt_length/clip_ratio 显示，随着任务难度上升，整体对话长度上升，导致截断率持续上升，最大截断率能到 40%。batch/solve_none 表示一批题里“全错”的题占比，平均值在 70% 左右，多数题都做不出。advantage/fraction_zero 代表 advantage 为 0 的样本占比，约在 78% 左右，即大部分样本对策略更新的贡献为 0，这也与前面的数据吻合。

![Screenshot 2026-06-30 at 18.00.19](/Users/zny/Library/Application Support/typora-user-images/Screenshot 2026-06-30 at 18.00.19.png)

**为什么失败**：从指标中可以看出，由于显存容量限制，不得不设置较小的max_model_len，导致较难的样本的输出被频繁截断，再加上OfficeBench对8B size的model较难。以上这些因素导致GRPO组内相对优势在大部分样本上都为0，训练失败。

# 3. 总结

总的来说，AWS 提供了全面的服务：训练/推理（Bedrock, Sagemaker），Agent运行时环境（Agentcore，Browser），可观测性（CloudWatch），存储（S3），自定义环境（ECR），Agent框架（Strands SDK），代码pipeline（CodeArtifact，Codebuild, CodeDeploy）。对于agent训练，AWS是一个不错的选择。