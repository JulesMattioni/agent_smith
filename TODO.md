# Agent Smith — Reste à faire

État au 2026-06-22. Les **tools SWE-bench sont terminés** (`mcp_tools_swebench.py` :
socle Docker, tous les tools en `docker exec`, signatures conformes au §V.5, cleanup).

---

## 🔴 Priorité 1 — Brancher l'agent SWE-bench

Fichier : `student/agent_swebench.py`

- [x] Connecter un MCP client au sandbox (actuellement `Sandbox(config, None)` → aucun tool).
      Faire comme MBPP : `MCPClient(command="python mcp_tools_swebench.py")` puis
      `Sandbox(config, mcp_client)`.
- [x] Passer la tâche au serveur MCP **via l'environnement**, avant de lancer le client :
      ```python
      os.environ["SWE_DOCKER_IMAGE"] = task_input.docker_image
      os.environ["SWE_EVAL_SCRIPT"] = task_input.eval_script
      ```
- [x] Injecter `mcp_client.get_man()` dans le `system_prompt` (présent dans MBPP, absent ici)
      sinon le LLM ne connaît pas les tools disponibles.

---

## 🟠 Priorité 2 — Corrections transverses

- [ ] **Déplacer `mcp_tools_mbpp.py` et `mcp_tools_swebench.py` à la racine du repo** (§V.2/V.5)
      et ajuster les commandes de lancement (`python mcp_tools_*.py`).
- [ ] **Dé-câbler le provider en dur** : `provider_name="groq"` est figé dans
      `agent_mbpp.py` et `agent_swebench.py` → en faire un argument CLI ou le déduire de l'URL
      (abstraction multi-providers, §V.6).

---

## 🟡 Priorité 3 — Robustesse & limites (§VI)

- [x] **Appliquer les limites dures** :
      - MBPP : 10 itérations / 6 000 input / 1 500 output / 120 s
      - SWE-bench : 30 itérations / 300 000 input / 10 000 output / 900 s
- [x] Arrêter la boucle quand les **tokens cumulés** approchent la limite (pas seulement le
      nombre d'itérations). Tokens cumulés sur toute la tâche.
- [x] **Gestion gracieuse des erreurs** partout — un crash pendant l'éval = échec automatique (§IV.1).
- [x] Vérifier la propagation de `KeyboardInterrupt` / `SystemExit` dans le sandbox (§V.2 :
      ne doivent pas être avalés silencieusement).

---

## 🟢 Priorité 4 — Validation

- [ ] **Sandbox seul** (`exam_sandbox.sh`) : imports bloqués, builtins, réseau, restriction de
      chemin, timeout, limite mémoire, protocole MCP.
- [ ] **MBPP** : cycle complet `dump → run → validate`, viser ≥ 4/5.
- [ ] **SWE-bench** : sur les tâches faciles suggérées par le sujet
      (`sympy__sympy-14711`, `sympy__sympy-13480`, `pydata__xarray-4629`), viser ≥ 2/3.
- [ ] Tester avec un **MCP server inconnu** : vérifier que le manuel et les wrappers de tools
      se génèrent dynamiquement.

---

## 📄 Priorité 5 — Livrables

- [ ] **`BENCHMARK_REPORT.md`** à la racine (§V.7) :
      - Setup : modèles/providers comparés, tâches choisies et pourquoi
      - Table de résultats : pass/fail, itérations, tokens in/out, temps — pour ≥ 5 modèles × ≥ 3 tâches SWE-bench
      - Fiabilité provider : temps de réponse moyen, retries, disponibilité
      - ≥ 2 métriques intermédiaires (exploration, progrès partiel, discipline de soumission)
      - 1 étude d'ablation (avant/après un changement, mêmes tâches/modèle)
      - Conclusions : modèles retenus / écartés, justifiés par les données
      - Garder les `solution.json` correspondants dans le repo
- [ ] **`README.md`** (actuellement quasi vide) — en **anglais** (§VII) :
      - 1ʳᵉ ligne en italique : *This project has been created as part of the 42 curriculum by <login>.*
      - Description, Instructions, Resources (+ comment l'IA a été utilisée)
      - Architecture système, explication de la boucle agent, design du sandbox,
        détails des tools, résultats de benchmark
- [ ] **Hygiène de soumission** (§VIII) : pas d'images Docker / poids de modèles / outputs
      générés ; **aucune clé API en dur** (échec sécurité automatique, §VI.3).

---

## ✅ Déjà fait

- Boucle agent Thought → Code → Observation (`core/agent/agent.py`)
- Sandbox isolé en process séparé : imports/open/socket/exec bloqués, RAM (`setrlimit`),
  timeout, `final_answer` injecté, bridge MCP via Pipe (`core/sandbox/sandbox.py`)
- Config sandbox Pydantic (`core/sandbox/config.py`)
- Client LLM OpenRouter + rotation multi-clés (`core/llm/`)
- Extracteur de code (python / XML / JSON-Hermes / ReAct) (`core/extractor/`)
- Client MCP stdio + HTTP, manuel dynamique (`core/mcp/client.py`)
- CLI sandbox interactif (`sandbox_cli.py`)
- Tools MBPP (`run_tests`) (`mcp_tools_mbpp.py`)
- **Tools SWE-bench complets** (`mcp_tools_swebench.py`)
