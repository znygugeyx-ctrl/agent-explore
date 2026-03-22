# configs - Configuration Files

## Purpose

Shared model definitions and example configs.
Experiment-specific configs live in each experiment's directory.

## Model Definition Example

```yaml
# configs/models/bedrock_claude_sonnet.yaml
id: us.anthropic.claude-sonnet-4-20250514
name: Claude Sonnet 4
provider: bedrock
context_window: 200000
max_tokens: 8192
```

## Convention

- Configs are YAML files
- Each experiment has its own config (not shared)
- This directory holds reusable templates only
