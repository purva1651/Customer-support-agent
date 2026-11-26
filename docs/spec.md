# Ticket Support Agent: Product Specification

## 1. Purpose

TicketBuddy is a demo support assistant for customers with bus, movie, and event tickets. It
answers policy questions from indexed documents, looks up bookings, records support requests, and
hands uncertain or complaint cases to an admin. The repository contains a React/Vite interface, a
FastAPI service, a mock CRM, and an optional Streamable HTTP MCP server.

This document describes the system as it is currently implemented. It distinguishes working
features from optional or deferred work; it is not a promise that unfinished features exist.

## 2. Users and operating assumptions

| User/system | Purpose | Current access model |
| --- | --- | --- |
| Customer | Ask policy questions, view booking details, request supported account changes, upload a document, or contact support. | Demo customer IDs such as `C001` and `C002`; passwords and production identity verification are not configured. |
| Admin | Manage knowledge, review escalations, reply to accepted cases, and view analytics/red-team checks. | Admin API key supplied in the admin interface and sent as `X-Admin-Key`. |
| MCP client | Call the shared agent or specific support tools. | `X-API-Key`; customer tools also use `X-Customer-ID` and `X-Session-ID` headers. |
| Mock CRM | Store seeded customer/booking data and demo support actions. | Local HTTP service backed by SQLite; not connected to a real ticket, booking, or payment provider. |

Customer IDs identify demo records; they are not authentication credentials. Do not use this demo
to process real customer data or payments.

## 3. Functional requirements implemented

### 3.1 Customer chat and policy answers

- The customer can start a chat using a demo customer ID and select English, Hindi, or Gujarati as
  the desired language.
- Chat requests contain a customer ID, session ID, message (up to 2,000 characters), and language.
- The backend binds each session to its first customer and rejects attempts to reuse the session
  under a different customer ID.
- Policy answers use the indexed knowledge base. Retrieval combines BM25 keyword search, Chroma
  vector search, reciprocal-rank fusion, and a local BGE reranker.
- Answers cite selected source titles and links. Local citations open the indexed file through the
  API; public web sources retain their source URL.
- If no sufficiently relevant source is found, or an answer cannot be generated, the assistant
  says it cannot verify the answer and escalates instead of making up policy terms.

### 3.2 Booking and account actions

- **Booking lookup:** retrieve route, departure, seat, amount, and status for a booking owned by the
  current demo customer. A booking belonging to someone else is returned as not found.
- **Cancellation:** prepare a cancellation action and wait for explicit customer approval. Approval
  tokens are customer- and booking-bound, expire after 10 minutes by default, and can be used only
  once. The mock CRM applies a 10% cancellation fee and returns the remaining amount as a refund. A second
  cancellation of an already-cancelled booking conflicts.
- **Refund request:** record a pending refund request for an owned booking. Repeating the request
  while one is pending returns the existing request. This records a request only; no refund is
  issued or approved, and there is no dedicated admin review panel for these records yet.
- **Contact update:** update the customer's email, phone number, and/or postal address. Email,
  phone, address, and non-empty update fields are validated by the CRM request schema.
- **Support ticket:** create a ticket for the current demo customer. Complaint and escalation flows
  also attempt to create a support ticket automatically.

Customer identity is injected into backend-created CRM tools. The language model must not provide
the customer ID as a tool argument.

### 3.3 Human escalation

- The agent escalates complaints, high-confidence negative sentiment, unsafe or failed actions,
  timeouts, and questions that cannot be answered from reliable policy sources.
- The customer can close an open handoff by sending the exact message `close`.
- Admins can list pending handoffs, accept or reject a case, read its saved thread, and reply to a
  customer after accepting it. Replies are added to the saved conversation and appear in the
  customer's chat.
- Escalation statuses are `pending`, `accepted`, `rejected`, and `closed`.

### 3.4 Admin workspace

- Add policy text, upload `.md`, `.txt`, `.pdf`, or `.docx` files, or index a public HTTP(S) URL.
- Re-index the knowledge base, list source status, open citations, and remove an indexed source by
  title. Ambiguous duplicate titles are not removed arbitrarily.
- View chat, resolution, escalation, intent, daily-volume, top-question, and unresolved-query
  analytics.
- Run the built-in red-team examples in the admin interface.

### 3.5 Document extraction

- The customer can upload PDF, DOCX, JPG, JPEG, or PNG files up to the configured 10 MiB default
  limit.
- The API forwards the file to the configured `extract_fields` MCP tool. The local tool reads PDF
  and DOCX text, uses Tesseract OCR for images and scanned PDFs, and parses recognizable labeled
  fields locally. When that finds too few fields, extracted text is sent to the configured LLM for
  structured extraction. The original file is not sent to a separate document service.
- Tesseract must be installed separately for image and scanned-PDF OCR. Digital text PDFs and DOCX
  files do not require OCR.

### 3.6 MCP interface and integrations

The Streamable HTTP MCP server exposes `answer_question`, `create_ticket`, `get_order_status`, and
`extract_fields`. The first three use authenticated customer/session headers; document extraction
requires the MCP API key. `answer_question` invokes the same agent graph used by the REST chat.

The chat model can be selected from the configured providers (xAI, Groq, Anthropic, OpenAI, or
Ollama). Langfuse tracing is optional. IndicTrans2 translation is optional, disabled by default,
and has not been validated as an enabled feature in the current environment.

## 4. Quality and safety requirements

- Validate request bodies and reject unsupported fields on strict API schemas.
- Apply input length limits and configured prompt-injection checks before agent routing.
- Bind sessions and CRM tools to the current demo customer; do not trust model-supplied identity.
- Require one-time explicit approval before a cancellation reaches the CRM.
- Do not treat a refund request as a payment operation or claim that money was issued.
- Protect `/admin/*` routes with `X-Admin-Key`; protect MCP requests with `X-API-Key`.
- Keep secrets in `.env`, which must not be committed. Customer/admin login is demo-only and is not
  a production authentication system.
- Store demo conversations, approvals, analytics, CRM records, and the vector index locally.
- Keep model calls and tool calls subject to configured timeouts; retry tool calls only according
  to their configured retry count.

## 5. Evaluation and acceptance checks

- `make test` runs the CI-safe pytest suite and enforces the configured 70% `app/` coverage floor.
- `make eval-retrieval` checks whether the expected source appears in the hybrid search and
  reranking top five for 30 policy questions.
- `make eval` sends 25 router/tool cases to the configured LLM. These current cases do not cover
  refund requests or address changes.
- These commands print test results; they do not create a separate report file. A RAGAS
  faithfulness/relevance report is not part of the project.
- The document extraction sample invoice has been manually exercised. Hindi/Gujarati translation
  with IndicTrans2 enabled has not been validated.

## 6. Deferred and out-of-scope work

- Real customer authentication, production authorization, or deployment hardening.
- Real booking provider, payment processor, refund issuance, or refund adjudication.
- A dedicated admin queue for reviewing and resolving pending refund-request records.
- General IT/HR helpdesk configuration and workflows; the agent remains focused on ticket/booking
  support.
- WhatsApp or embeddable website widget, voice input/output, and automatic FAQ generation from
  resolved tickets.
- IndicTrans2 installation/validation in the current Windows environment.
- RAGAS report generation, removed at the project owner's request.
