# AI Agent Interaction Modalities: Research Report

**Date**: 2026-03-26
**Scope**: How AI agents interact with external environments -- modalities, debates, and tradeoffs

---

## 1. Tool Calling / Function Calling (Structured JSON Schema)

### How It Works

The model receives tool definitions as JSON Schema objects alongside the conversation. When the model decides to use a tool, it outputs a structured JSON object specifying the tool name and arguments. The host application executes the tool and returns the result, continuing the conversation loop.

**Key implementations:**
- **Anthropic Tool Use**: Tools defined with `name`, `description`, `input_schema` (JSON Schema). Supports `auto`, `any`, and `tool` choice modes. New `strict: true` option guarantees schema conformance via constrained decoding. [Source: platform.claude.com/docs]
- **OpenAI Function Calling**: Similar JSON Schema approach. Introduced `parallel_tool_use` and structured outputs.
- **Native vs Prompt-based**: The Berkeley Function Calling Leaderboard (BFCL) distinguishes "FC" models (native tool calling support) from "Prompt" models (text generation workaround). Native support is significantly more reliable. [Source: gorilla.cs.berkeley.edu]

### Frameworks Using It
- **LangChain/LangGraph**: Standardizes tool calling across providers via `bind_tools()` and unified `AIMessage.tool_calls`. Works with Anthropic, OpenAI, Gemini, Mistral, Groq, Cohere. [Source: blog.langchain.com]
- **Anthropic Agent SDK**: Provides tools as first-class primitives for custom agent development.
- **OpenAI Assistants API**: Built around function calling as the primary interaction mechanism.
- **smolagents (Hugging Face)**: Supports both JSON tool calling and code-based agents. [Source: huggingface.co/blog/smolagents]

### Strengths
- **Type safety**: JSON Schema validation ensures well-formed inputs
- **Predictable interface**: Clear contract between model and tool
- **Easy to audit**: Every tool call is a discrete, logged event
- **Provider-native**: Major LLM providers train specifically for this pattern
- **Composable with MCP**: Standard tool definitions map directly to MCP tools

### Weaknesses
- **Constrained action space**: Each action is a single function call; complex multi-step operations require many round trips
- **Rigid**: Cannot express arbitrary computation; limited to predefined tool signatures
- **Schema overhead**: Tool definitions consume context tokens (Manus reports system prompt + tools = ~3800 tokens for 20+ tools)
- **Multi-turn fragility**: BFCL V3 found models struggle with state tracking across turns, "implicit action failure" (not inferring exploratory steps), and "overthinking" (redundant authentication attempts) [Source: gorilla.cs.berkeley.edu, BFCL V3]

### Real-World Examples
- Most chatbot integrations (weather, search, calculators)
- Claude.ai with tools, ChatGPT with plugins/functions
- Enterprise integrations where audit trails matter

---

## 2. MCP (Model Context Protocol)

### How It Works

MCP is an open protocol (JSON-RPC 2.0 based) that standardizes how AI applications connect to external data and tools. It defines a client-server architecture:

- **MCP Host**: The AI application (e.g., Claude Code, VS Code, ChatGPT)
- **MCP Client**: Component within the host that maintains a connection to one MCP server
- **MCP Server**: A program exposing tools, resources, and prompts

**Three core server primitives:**
1. **Tools**: Executable functions (e.g., file operations, API calls, database queries)
2. **Resources**: Data sources providing context (e.g., file contents, database records)
3. **Prompts**: Reusable interaction templates

**Two client primitives:**
1. **Sampling**: Servers can request LLM completions from the client (model-agnostic)
2. **Elicitation**: Servers can request user input

**Transport mechanisms:**
- **Stdio**: Local process communication, no network overhead
- **Streamable HTTP**: Remote servers, SSE streaming, OAuth authentication

**Lifecycle**: Stateful protocol with capability negotiation handshake. Supports real-time notifications (e.g., `tools/list_changed`). [Source: modelcontextprotocol.io/docs/learn/architecture]

### Adoption (as of March 2026)
- **Clients**: Claude Code, Claude Desktop, ChatGPT, VS Code (Copilot), Cursor, JetBrains IDEs, Windsurf, Replit, Sourcegraph, Zed
- **Servers**: GitHub, Slack, Google Drive, Postgres, Puppeteer, Sentry, filesystem, and hundreds of community-built servers
- **Enterprise**: Block, Apollo among early adopters [Source: anthropic.com/news/model-context-protocol]

### Strengths
- **Universal standard**: "USB-C for AI" -- build once, integrate everywhere
- **Ecosystem effects**: Growing library of pre-built servers
- **Separation of concerns**: Tool implementation decoupled from AI application
- **Dynamic discovery**: Clients discover available tools at runtime
- **Security model**: Capability negotiation, transport-level auth

### Weaknesses
- **Complexity**: Full protocol stack (JSON-RPC, lifecycle, capability negotiation) is heavier than simple function calling
- **Latency**: Extra protocol layer adds overhead vs direct tool calls
- **Security concerns**: MCP servers can be vectors for prompt injection (tools return untrusted content that enters the model context)
- **Still maturing**: Specification versioned 2025-06-18; breaking changes still possible
- **Overhead for simple cases**: If you only need one tool, MCP is overengineered

### Real-World Examples
- Claude Code connecting to Jira, Slack, Google Drive via MCP
- Cursor accessing Sentry error data through MCP
- VS Code Copilot using filesystem and database MCP servers

---

## 3. CLI / Shell Execution

### How It Works

The agent has access to a shell (bash/zsh) tool that executes arbitrary commands. The model generates a command string, the host runs it in a shell subprocess, and stdout/stderr are returned to the model.

**Key design decisions from Anthropic's SWE-bench agent:**
- Bash tool accepts a single `command` parameter
- Tool description carries heavy instructional weight: network limitations, output management, background processes
- Absolute paths required to prevent navigation errors
- Philosophy: "give as much control as possible to the language model, keep scaffolding minimal" [Source: anthropic.com/research/swe-bench-sonnet]

### Frameworks Using It
- **Claude Code**: Primary interaction modality. Executes shell commands, reads/writes files, runs tests, manages git. [Source: code.claude.com/docs]
- **OpenAI Codex**: Cloud-based sandboxed shell execution (each task gets an isolated environment)
- **SWE-agent (Princeton)**: Custom Agent-Computer Interface (ACI) with specialized shell commands. Demonstrated that "ACI design directly influences agent behavior and performance." [Source: arxiv.org/abs/2405.15793]
- **OpenHands**: Five core tools including bash execution and Jupyter notebooks
- **Magentic-One (Microsoft)**: Dedicated ComputerTerminal agent for shell access [Source: microsoft.com/research]

### Strengths
- **Maximum flexibility**: Any program, any language, any workflow
- **Real environment**: Tests actually run, builds actually compile, errors are real
- **Ground truth feedback**: "During execution, it's crucial for agents to gain 'ground truth' from the environment at each step" (Anthropic) [Source: anthropic.com/research/building-effective-agents]
- **Composable**: Unix philosophy -- pipe, chain, script
- **No abstraction overhead**: Direct access to the full computing environment

### Weaknesses
- **Security risk**: Arbitrary command execution is inherently dangerous
- **Non-deterministic output**: Shell output varies, can be noisy or enormous
- **State management**: Working directory, environment variables, background processes create hidden state
- **Error-prone**: Models frequently make mistakes with relative paths, quoting, escaping
- **Sandboxing required**: Must run in containers/VMs for safety (adds infrastructure complexity)

### Real-World Examples
- **Claude Code**: Runs in user's terminal with permission system (allow/deny per command)
- **OpenAI Codex**: Each task in an isolated cloud sandbox with network restrictions
- **Devin**: Shell access within sandboxed VM environment
- **Manus**: Full VM sandbox with root access, persistent file system [Source: manus.im/blog/manus-sandbox]

---

## 4. Code Execution / Code Interpreter

### How It Works

Instead of selecting from predefined tools, the agent writes and executes code (typically Python) to accomplish tasks. The code runs in an interpreter, and output (including errors) is returned to the model for iteration.

**The CodeAct paradigm** (Wang et al., 2024): Uses executable Python code as the unified action space instead of JSON tool calls. Achieved "up to 20% higher success rate" compared to JSON/text-based methods across 17 LLMs. [Source: arxiv.org/abs/2402.01030]

### Frameworks Using It
- **smolagents (Hugging Face)**: First-class CodeAgent support. "Writing actions in code is significantly better than JSON-based tool calling." [Source: huggingface.co/blog/smolagents]
- **OpenHands/OpenDevin**: CodeAct framework -- agents write executable code rather than selecting from predefined actions. Five tools: bash, Jupyter, file edit, search, web browse. [Source: latent.space, 2024 agents review]
- **DynaSaur (Adobe Research)**: Agents "dynamically create and compose actions" via code generation. Published at COLM 2025. [Source: arxiv.org/abs/2411.01747]
- **ChatGPT Code Interpreter**: Python sandbox for data analysis, visualization, file processing
- **LangGraph code execution**: Iterative code generation with validation -- 81% success vs 55% for single-pass [Source: blog.langchain.com]

### Strengths
- **Composability**: Naturally nest actions, define functions, use loops/conditionals
- **Object management**: Handle complex outputs (images, dataframes, models)
- **Generality**: "Code expresses any computational action simply" (smolagents)
- **Training alignment**: LLMs have extensive code in training data
- **Self-debugging**: Agents can catch exceptions and iterate
- **Fewer round trips**: Multiple operations in one code block vs one-tool-call-per-turn

### Weaknesses
- **Security**: Arbitrary code execution requires sandboxing
- **Unpredictability**: Generated code may have bugs, infinite loops, resource exhaustion
- **Harder to audit**: Free-form code is harder to review than discrete tool calls
- **Inconsistent quality**: Code quality varies with model capability
- **Dependency management**: Need the right libraries installed in the execution environment

### Real-World Examples
- **ChatGPT Code Interpreter**: Data analysis, chart generation, file conversion
- **OpenHands**: SWE-bench #1, uses CodeAct framework with Jupyter notebooks
- **Devin**: Full development environment with code execution
- **Manus**: Writes and executes code in sandbox VM

---

## 5. Browser / Computer Use

### How It Works

Two main approaches:

**A. Computer Use (Vision-based)**: The model receives screenshots, reasons about the visual interface, and outputs mouse/keyboard actions.
- Anthropic's Computer Use: "Claude counts how many pixels vertically or horizontally it needs to move a cursor to click accurately." Provides screenshot capture, mouse control (click, drag, move), keyboard input, and desktop automation. [Source: anthropic.com/news/developing-computer-use, platform.claude.com/docs]
- Performance: 14.9% on OSWorld (vs 7.7% for competitors, 70-75% human baseline)

**B. Structured Browser Actions**: The agent uses predefined browser tools (navigate, click, type, extract) operating on accessibility trees or DOM elements.
- Manus Browser Operator: Combines cloud browser (sandbox) with local browser (authenticated sessions). Uses structured tools prefixed with `browser_*`. [Source: manus.im/blog]
- Magentic-One WebSurfer: Chromium-based, uses accessibility trees and set-of-marks prompting [Source: microsoft.com/research]

### Frameworks Using It
- **Anthropic Computer Use**: Beta API feature for Claude models (screenshot + mouse/keyboard)
- **Manus**: Browser Operator for both cloud and local browser automation
- **Magentic-One**: Dedicated WebSurfer agent
- **Playwright MCP**: Browser automation exposed as MCP tools
- **Browser Use (open source)**: Python library for LLM-driven browser automation

### Strengths
- **Universal interface**: Can interact with any web application or desktop software
- **Handles visual UIs**: Works with interfaces that have no API
- **"Make the model fit the tools"**: Reverses traditional approach of building custom environments (Anthropic) [Source: anthropic.com/news/developing-computer-use]
- **Authenticated access**: Can use existing user sessions and credentials

### Weaknesses
- **Slow**: Screenshot-based approaches are inherently slower than API calls
- **Error-prone**: Pixel-level interaction is fragile; misses transient UI elements
- **Token-expensive**: Screenshots consume many tokens
- **Low accuracy**: Still far below human performance (14.9% vs 70-75% on OSWorld)
- **Security**: Browser access to authenticated services creates risk

### Real-World Examples
- **Manus**: Primary interaction modality for web tasks; combines browser + code + shell
- **Anthropic Computer Use**: Desktop automation, form filling, web navigation
- **Google Project Mariner**: Browser-based agent (Gemini)
- **Magentic-One**: WebSurfer agent for web-based benchmarks (WebArena, GAIA)

---

## 6. API Calls Directly in Code

### How It Works

Rather than the host defining tools that wrap APIs, the agent writes code that directly calls APIs using standard HTTP libraries or SDKs. The agent decides which APIs to call, how to authenticate, and how to process responses -- all within generated code.

### Frameworks Using It
- **OpenHands**: "Rather than exposing individual APIs as tools, agents access Python libraries directly, enabling complex multi-step operations without excessive LLM calls" [Source: latent.space, Graham Neubig interview]
- **Devin**: Writes code that calls APIs as part of development workflows
- **DynaSaur**: Dynamically generates code that calls APIs not in the predefined tool set [Source: arxiv.org/abs/2411.01747]

### Strengths
- **Infinite API coverage**: Not limited to predefined tool wrappers
- **Complex orchestration**: Can handle auth flows, pagination, error handling, retries
- **Code reuse**: Generated API-calling code can be saved and reused (DynaSaur approach)
- **Natural for developers**: Mirrors how humans interact with APIs

### Weaknesses
- **Credential management**: Agent needs access to API keys/tokens (security risk)
- **No type safety**: No JSON Schema validation on API calls
- **Hallucination risk**: Model may hallucinate API endpoints or parameters
- **Harder to constrain**: Cannot easily limit which APIs the agent accesses
- **Documentation dependency**: Needs API docs in context or training data

### Real-World Examples
- **OpenHands**: Agents import Python libraries and call APIs directly
- **Devin**: Builds integrations by writing API-calling code
- **ChatGPT Code Interpreter**: Can make HTTP requests within sandbox

---

## Key Debates

### Debate 1: Tools vs Code ("Code Is the Universal Tool")

This is the central architectural debate in agent design.

**The "Code" Camp:**
- **CodeAct** (Wang et al., 2024): Executable Python code achieves "up to 20% higher success rate" than JSON tool calls across 17 LLMs. Advantages: composability, object management, generality, training data alignment. [Source: arxiv.org/abs/2402.01030]
- **smolagents/Hugging Face**: "Writing actions in code is significantly better than JSON-based tool calling." Code naturally handles nesting, variables, conditionals -- things JSON tool calls cannot express. [Source: huggingface.co/blog/smolagents]
- **OpenHands/Graham Neubig**: "Rather than exposing individual APIs as tools, agents access Python libraries directly." Single-agent systems with light prompting beat multi-agent architectures. [Source: latent.space]
- **DynaSaur**: Fixed action sets "restrict planning capabilities and demand extensive human effort." Dynamic code generation "significantly improves flexibility." [Source: arxiv.org/abs/2411.01747, COLM 2025]

**The "Tools" Camp:**
- **Anthropic (Building Effective Agents)**: Invests heavily in tool interface design. "Much more attention should go into designing tool interfaces for models." Their SWE-bench agent uses just two tools (bash + edit) with carefully crafted descriptions. [Source: anthropic.com]
- **Manus**: Uses structured tool calling with logit masking for tool selection. Prefixes tools consistently (`browser_*`, `shell_*`). [Source: manus.im/blog]
- **Enterprise requirements**: Audit trails, access control, rate limiting all easier with structured tools
- **BFCL benchmark**: Evaluates structured function calling as the primary agent capability [Source: gorilla.cs.berkeley.edu]

**The emerging synthesis**: The distinction is blurring. Claude Code uses structured tools (Read, Edit, Bash, Glob, Grep) but those tools execute arbitrary code/commands. The "bash" tool IS code execution. The real question is the granularity of the action interface -- not whether code is involved.

### Debate 2: MCP Standardization vs Custom Tool Implementations

**Pro-MCP:**
- Ecosystem effects: build once, integrate everywhere (Claude, ChatGPT, VS Code, Cursor all support MCP)
- Reduces N*M integration problem to N+M
- Dynamic tool discovery and capability negotiation
- Growing ecosystem: hundreds of pre-built servers

**Anti-MCP / Skeptics:**
- Adds protocol complexity for simple use cases
- Security concerns: MCP servers return content that enters model context (prompt injection vector)
- Still maturing (spec version 2025-06-18); churn risk
- For code-native agents, importing a Python library is simpler than running an MCP server
- Not all AI applications need external tools; MCP adds unnecessary abstraction

**Current state**: MCP has achieved broad adoption. ChatGPT adopting MCP (2025) was a turning point -- it's becoming the de facto standard despite concerns.

### Debate 3: Sandboxed vs Unsandboxed Execution

**Sandboxed (Manus, Codex, Devin):**
- Each task gets isolated VM/container
- Full root access within sandbox; zero risk to host
- Can run 24/7 without local resources
- Manus: "Zero Trust" security -- "any operations inside a Sandbox only affect that Sandbox" [Source: manus.im/blog/manus-sandbox]
- OpenAI Codex: Cloud sandbox with network restrictions

**Unsandboxed (Claude Code, Cursor, Windsurf):**
- Runs directly in user's development environment
- Access to real files, real git, real test infrastructure
- Permission-based: user approves each shell command
- Faster iteration (no VM startup, no file sync)
- Risk: mistakes affect real environment

**Hybrid emerging**: Claude Code on the web runs in cloud sandboxes; locally it runs unsandboxed with permissions. Cursor offers both local and cloud agents. The trend is toward offering both modes.

### Debate 4: Structured Tool Calling vs Free-Form Code Generation

This maps to a spectrum of agent autonomy:

| Level | Approach | Example | Control | Flexibility |
|-------|----------|---------|---------|-------------|
| 1 | Strict tools only | ChatGPT plugins | Maximum | Minimum |
| 2 | Tools + code interpreter | ChatGPT + Code Interpreter | High | Moderate |
| 3 | Code agent with tool library | smolagents CodeAgent | Moderate | High |
| 4 | Unrestricted code execution | OpenHands, Devin | Minimum | Maximum |

smolagents defines a similar "agency spectrum" from no LLM impact to multi-step iterative agents. [Source: huggingface.co/blog/smolagents]

### Debate 5: Agent-Computer Interface Design

A key finding from research is that **interface design matters as much as model capability**.

- **SWE-agent (Princeton)**: Introduced the term "Agent-Computer Interface" (ACI). Custom interfaces "significantly enhance an agent's ability to create and edit code files, navigate entire repositories, and execute tests." [Source: arxiv.org/abs/2405.15793]
- **Anthropic**: "Much more attention should go into designing tool interfaces for models, in the same way that a large amount of attention goes into designing tool interfaces for humans." Simple changes (absolute paths, clear error messages) dramatically improve reliability. [Source: anthropic.com/research/swe-bench-sonnet]
- **Cursor**: Invests in custom tool infrastructure (regex search indexing) because "latency matters a lot for this functionality" -- agents use search constantly and in parallel. [Source: cursor.com/blog]
- **Manus**: Context-aware state machine for tool availability. Uses logit masking to control tool selection without modifying tool definitions (preserves KV cache). [Source: manus.im/blog]

---

## Comparative Summary: Real-World Agent Architectures

| Agent | Primary Modalities | Execution Model | Key Innovation |
|-------|-------------------|-----------------|----------------|
| **Claude Code** | CLI/shell + structured tools + MCP | Local (unsandboxed, permission-based) or cloud sandbox | Minimal scaffolding; bash + edit tools; MCP ecosystem |
| **OpenAI Codex** | Sandboxed shell + code execution | Cloud sandbox per task | Fully isolated cloud execution |
| **Manus** | Browser + code + shell | Cloud VM sandbox per task | Context engineering; logit masking for tool selection |
| **Devin** | Code + shell + browser | Cloud sandbox | Autonomous multi-hour sessions; Slack integration |
| **Cursor** | Structured tools + shell | Local IDE + cloud agents | Custom tool infrastructure (indexed search); Agent Client Protocol |
| **OpenHands** | Code (CodeAct) + bash + browser | Docker containers | CodeAct framework; SWE-bench #1 |
| **Magentic-One** | Browser + code + shell + files | Multi-agent with Orchestrator | Specialized agents per modality |
| **smolagents** | Code agent (Python) | Local/sandboxed | Code-first; Hub tool sharing |

---

## Key Benchmarks

| Benchmark | What It Measures | Relevant Modality |
|-----------|-----------------|-------------------|
| **BFCL V1-V4** | Function calling accuracy (single/multi-turn, agentic) | Structured tool calling |
| **SWE-bench** | Real-world software engineering (bug fixing) | Shell + code + file edit |
| **WebArena** | Web navigation and task completion | Browser use |
| **OSWorld** | Desktop GUI interaction | Computer use |
| **GAIA** | Multi-step reasoning with tools | Mixed (search, code, files) |
| **HumanEvalFix** | Code repair | Code execution |

---

## Key References

1. Anthropic, "Building Effective Agents" (2024) -- https://www.anthropic.com/research/building-effective-agents
2. Wang et al., "Executable Code Actions Elicit Better LLM Agents" (CodeAct, 2024) -- https://arxiv.org/abs/2402.01030
3. Yang et al., "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering" (2024) -- https://arxiv.org/abs/2405.15793
4. Manus, "Context Engineering for AI Agents" (2025) -- https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
5. Anthropic, "Claude's SWE-bench Verified Score" (2024) -- https://www.anthropic.com/research/swe-bench-sonnet
6. Hugging Face, "smolagents" (2025) -- https://huggingface.co/blog/smolagents
7. MCP Specification -- https://modelcontextprotocol.io/docs/learn/architecture
8. BFCL V3 Multi-Turn -- https://gorilla.cs.berkeley.edu (Berkeley Function Calling Leaderboard)
9. DynaSaur, "Large Language Agents Beyond Predefined Actions" (COLM 2025) -- https://arxiv.org/abs/2411.01747
10. Microsoft, "Magentic-One: A Generalist Multi-Agent System" (2024) -- https://www.microsoft.com/en-us/research/blog/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/
11. Anthropic, "Developing Computer Use" (2024) -- https://www.anthropic.com/news/developing-computer-use
12. Latent Space, "2024 in AI Agents" (Graham Neubig interview) -- https://www.latent.space/p/2024-agents
13. Anthropic, MCP announcement (2024) -- https://www.anthropic.com/news/model-context-protocol
14. Manus Sandbox documentation -- https://manus.im/blog/manus-sandbox
15. Cursor, "Fast regex search: indexing text for agent tools" (2026) -- https://www.cursor.com/blog/fast-regex-search
