# Project Requirements

## Environment
1. **PyCharm Pro** is the development environment
2. **Python 3.14** is the target version
3. **uv** is the package manager

## Architecture
4. **Chat-like UI** frontend
5. Built with the **PyView framework** (https://pyview.rocks) — new to us, learning as we build
6. Backend uses **http_stream_prj** mono repo (https://github.com/avilior/http_stream_prj)
7. Implement **both frontend and backend** application
8. Frontend is a package in the mono repo (`packages/frontend`)

## Design Principles
9. **Interaction layer first**, then concentrate on a specific application
10. **Frontend is application-agnostic** — a generic chat shell that sends user instructions to the backend and displays streamed output. No application-specific logic in the frontend.

## Communication
11. Uses **ACP** (Agent Client Protocol) — https://agentclientprotocol.com
12. Client sends **JSONRPC requests**, receives **JSONRPC responses**
13. Server may open an **SSE channel** to push notifications to the frontend — use PyView streaming capabilities for this

## Backend
14. Backend work is **application layer only** — the JRPC layer and server layer are already implemented in http_stream_prj. May need tweaks.

## MVP Application
15. Two **LLM Chat Agents debating** each other
16. User acts as a **moderator**
17. Chat Agents use **Ollama** to run the LLM locally

## Other
18. Authentication via backend's **mock tenant** approach (Bearer tokens: tok-acme-001, tok-globex-002, tok-initech-003)
19. **Chat history storage** — TBD (frontend and/or backend)
20. **MVP is single user**, local developer deployment. Multi-user deployment later but not current focus.
