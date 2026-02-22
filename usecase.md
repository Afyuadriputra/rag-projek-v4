
**Gambaran Besar**

* Stack: Django + Inertia + React/Vite + LangChain + Chroma local.
* Pola arsitektur backend: **views -> service facade -> domain services -> ai_engine**.
* RAG kamu sudah mature: ada ingestion modular, intent router, hybrid retrieval, rerank, structured analytics, guardrails, metrics.
* Planner ada 2 mode: flow lama via **chat_api(mode="planner")** dan flow baru v3 via endpoint khusus.

**Backend Inti**

* Routing global dan app: [urls.py (line 8)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [urls.py (line 4)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Settings utama: SQLite lokal, Django-Vite, Inertia, Axes, middleware observability/presence/maintenance di [settings.py (line 73)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Model domain cukup lengkap:
  * Dokumen/chat/planner: [models.py (line 8)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [models.py (line 21)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [models.py (line 33)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [models.py (line 50)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [models.py (line 82)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
  * Operasional sistem: [models.py (line 163)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [models.py (line 244)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [models.py (line 275)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [models.py (line 298)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Service facade menyatukan modul dan menjaga patch-compat lama: [service.py (line 1)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).

**RAG Engine**

* Embedding + vectorstore:
  * Chroma persist di **chroma_db**, collection **academic_rag**, metadata filter by **user_id**: [config.py (line 11)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [config.py (line 105)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
  * Embedding default **multilingual-e5-large** + prefix **query:/passage:** untuk E5: [config.py (line 23)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Ingestion:
  * Facade kompatibilitas: [ingest.py (line 323)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
  * Orchestrator modular extract/parse/chunk/write: [orchestrator.py (line 34)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
  * Parser chain: deterministic dulu (transcript rules), lalu LLM fallback: [parser_chain.py (line 43)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
  * Metadata chunk kaya (**user_id**, **doc_id**, **doc_type**, **chunk_kind**, dll): [metadata_builder.py (line 7)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Retrieval:
  * Entry utama **ask_bot**: [main.py (line 439)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
  * Fitur penting:
    * Query safety/guard (**crime**, **political persuasion**, weird query): [main.py (line 332)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
    * Mention file via **@nama_file** + resolusi dokumen user: [main.py (line 89)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
    * Intent routing (**analytical_tabular**, **semantic_policy**, **out_of_domain**): [intent_router.py (line 53)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
    * Structured analytics deterministic (transcript/schedule) + post-polish LLM tervalidasi: [structured_analytics.py (line 438)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
    * Dense/hybrid(BM25+RRF)/rerank parametrik via env: [main.py (line 747)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
    * Multi-model fallback OpenRouter + metrics per request: [llm.py (line 24)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [monitoring.py (line 95)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).

**Planner System**

* Legacy planner state-machine: [planner.py (line 1)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Planner v3 adaptif (run state, branching, execute/cancel):
  * Start: [service.py (line 842)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#)
  * Next step: [service.py (line 935)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#)
  * Execute: [service.py (line 1038)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#)
  * Cancel: [service.py (line 1119)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#)
* Persist state v3 di **PlannerRun** (snapshot blueprint, answers, path, depth, expiry): [models.py (line 82)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).

**Frontend**

* Inertia bootstrapping dan CSRF axios: [main.tsx (line 1)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Halaman utama sangat stateful untuk chat + planner v3 lifecycle: [Index.tsx (line 180)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* API client typed lengkap untuk chat/docs/session/planner: [api.ts (line 1)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Komponen onboarding planner (file aktif kamu):
  * Menampilkan error relevansi + kandidat jurusan + opsi reuse/upload dokumen: [PlannerOnboardingCard.tsx (line 8)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Renderer panel planner in-chat:
  * State **onboarding/uploading/ready/reviewing/executing/done**: [PlannerPanelRenderer.tsx (line 7)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Integrasi build ke Django static (**core/static/dist**): [vite.config.ts (line 49)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).

**Alur End-to-End**

* Upload dokumen: frontend **uploadDocuments** -> **POST /api/upload/** -> ingest -> embed -> dokumen **is_embedded=true**.
* Chat RAG: frontend **sendChat** -> **POST /api/chat/** -> **service.chat_and_save** -> **ask_bot** -> simpan **ChatHistory**.
* Planner v3:
  * Start (**/api/planner/start/**) validasi relevansi dokumen + buat **PlannerRun**.
  * Next (**/api/planner/next-step/**) validasi sequence + branching adaptif.
  * Execute (**/api/planner/execute/**) kirim prompt ringkasan ke RAG dengan grounding policy.

**Temuan Penting (Risk/Tech Debt)**

* Ada redefinisi fungsi planner dua kali (termasuk versi teks “mojibake”), sehingga function awal jadi dead code:
  * **_build_planner_markdown** ganda: [service.py (line 115)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#) dan [service.py (line 175)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
  * **_ensure_planner_required_sections** ganda: [service.py (line 154)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#) dan [service.py (line 214)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Label opsi fallback planner masih karakter rusak di payload **planner_generate**:
  * [service.py (line 399)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Endpoint API banyak pakai **@csrf_exempt** walau session auth:
  * contoh [views.py (line 489)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [views.py (line 549)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [views.py (line 604)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* **DEBUG** default **True** dan **ALLOWED_HOSTS** hardcoded minimal:
  * [settings.py (line 19)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [settings.py (line 21)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#).
* Maintenance middleware untuk anonymous non-API pada akhirnya tetap **get_response**:
  * [middleware.py (line 213)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [middleware.py (line 216)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#) (kemungkinan intentional, tapi worth review policy).

**Kualitas & Testing**

* Backend test suite sangat besar (terdeteksi ~279 test function di **core/test**).
* Frontend ada unit test planner/chat ([Index.phase4.test.tsx (line 1)](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#)) dan e2e Playwright ([phase4-planner.spec.ts](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#), [security.spec.ts](https://file+.vscode-resource.vscode-cdn.net/c%3A/Users/M-SI/.vscode/extensions/openai.chatgpt-0.4.76-win32-x64/webview/#)).
* Saya belum menjalankan test; ini audit statik kode.
