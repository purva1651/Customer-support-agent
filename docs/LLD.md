# Low-Level Design

The service is organized in dependency direction: frontend adapters call REST; REST and MCP
adapters call the shared agent; the agent uses retrieval, tools, LLM wrappers, and guardrails;
the tools access the mock CRM over HTTP. Configuration lives in `config/` and secrets in the
environment.
