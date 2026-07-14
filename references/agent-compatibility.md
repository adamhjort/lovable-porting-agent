# Agent compatibility

The core skill follows the open [Agent Skills specification](https://agentskills.io/specification): a `SKILL.md` file with YAML frontmatter, Markdown instructions, optional scripts, and on-demand references.

## Supported clients

### Codex

Install the repository as a directory named `port-lovable-app` under a personal or project Agent Skills location:

- personal: `~/.agents/skills/port-lovable-app/`
- project: `.agents/skills/port-lovable-app/`

Invoke it with `$port-lovable-app` or let Codex match the description. `agents/openai.yaml` is optional Codex/ChatGPT UI metadata and is not part of the workflow contract.

### Claude Code

Install the repository as:

- personal: `~/.claude/skills/port-lovable-app/`
- project: `.claude/skills/port-lovable-app/`

Invoke it with `/port-lovable-app` or let Claude match the description. Claude ignores `agents/openai.yaml` and uses the same `SKILL.md`, scripts, and references.

### Other agents

Use any client that implements Agent Skills directly. For clients without automatic skill discovery, load `SKILL.md` as task instructions and preserve its relative access to `scripts/` and `references/`.

## Tool mapping

Interpret tool names by capability, not vendor:

- use the available read-only GitHub or Lovable connector when one exists;
- use the agent's normal file-reading and smallest safe patch/edit operation;
- use the local shell only for the bundled deterministic scripts and reviewed build commands;
- request approval through the client's native approval mechanism before external mutations;
- stop if the client cannot keep secrets out of prompts, logs, command arguments, and evidence files.

Do not add client-specific frontmatter such as tool allowlists to the shared `SKILL.md`; support varies between implementations. Keep product-specific metadata optional and outside the core instructions.
