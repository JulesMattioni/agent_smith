# Agent Smith — Reste à faire

État au 2026-06-24. **Les deux agents (MBPP + SWE-bench) résolvent réellement
des tâches en free tier** ; la validation forcée et les frictions
d'environnement sont réglées. Reste surtout : nettoyage transverse, validation
systématique et livrables.

---

## 🟠 Priorité 1 — Corrections transverses

- [ ] **Déplacer `mcp_tools_mbpp.py` et `mcp_tools_swebench.py` à la racine du repo** (§V.2/V.5)
      et ajuster les commandes de lancement (`python mcp_tools_*.py`).
- [ ] **retravailler sandbox cli** mettre le fonctionnement actuel de la sandbox cli sous un flag
      `--interactive` et remplacer le fonctionnement de base par un fonctionnement qui fonctionne
      avec cette commande: `<test code here> | uv run sandbox_cli.py --mcp-stdio <mcp command here>`
- [x] **Dé-câbler le provider en dur** : `provider_name="groq"` est figé dans
      `agent_mbpp.py` et `agent_swebench.py` → en faire un argument CLI ou le déduire de l'URL
      (abstraction multi-providers, §V.6).
- [x] **Plafonner l'attente sur rate-limit** (`core/llm/clients.py`) : `RATE_LIMIT_MAX_WAIT`
      (120 s) → au-delà, abandon propre. Rotation de clé d'abord (balayage des clés vivantes
      via `KeyManager.live_count`), back-off plafonné seulement quand toutes sont throttlées.
- [x] **Try/Except partout** Ajouter les try/except autour des main pour eviter tout crash.

---

## 🟢 Priorité 2 — Validation

- [ ] **Sandbox seul** (`exam_sandbox.sh`) : imports bloqués, builtins, réseau, restriction de
      chemin, timeout, limite mémoire, protocole MCP.
- [ ] **MBPP** : cycle complet `dump → run → validate`, viser ≥ 4/5.
      (Modèle qui suit le code-based : `llama-4-scout`, `llama-3.3-70b`, `qwen3-32b` —
      **pas** `gpt-oss-*`, voir note plus bas.)
- [ ] **SWE-bench** : viser ≥ 2/3 sur les tâches faciles. ✅ déjà résolues de bout en bout
      avec `llama-4-scout` : `sympy-13480`, `sympy-18189`, `django-11066`.
      ⚠️ **Bloqueur local** : la moulinette plante sur Docker rootless (lchown UID élevé) —
      workaround appliqué dans le `.venv`, voir `docs/bug-moulinette-docker-rootless.md`.
      Retour staff à faire.
- [ ] Tester avec un **MCP server inconnu** : vérifier que le manuel et les wrappers de tools
      se génèrent dynamiquement.

---

## 📄 Priorité 3 — Livrables

- [ ] **`BENCHMARK_REPORT.md`** à la racine (§V.7) : - Setup : modèles/providers comparés, tâches choisies et pourquoi - Table de résultats : pass/fail, itérations, tokens in/out, temps — pour ≥ 5 modèles × ≥ 3 tâches SWE-bench - Fiabilité provider : temps de réponse moyen, retries, disponibilité - ≥ 2 métriques intermédiaires (exploration, progrès partiel, discipline de soumission) - 1 étude d'ablation (avant/après un changement, mêmes tâches/modèle) — p. ex. impact de
      la validation forcée, ou des consignes `run_tests`/verbatim côté MBPP - Conclusions : modèles retenus / écartés, justifiés par les données
      (constat fort : `gpt-oss-*` incompatibles avec le code-based tool calling) - Garder les `solution.json` correspondants dans le repo
- [ ] **`README.md`** (actuellement quasi vide) — en **anglais** (§VII) : - 1ʳᵉ ligne en italique : _This project has been created as part of the 42 curriculum by <login>._ - Description, Instructions, Resources (+ comment l'IA a été utilisée) - Architecture système, explication de la boucle agent, design du sandbox,
      détails des tools, résultats de benchmark
- [ ] **Hygiène de soumission** (§VIII) : pas d'images Docker / poids de modèles / outputs
      générés ; **aucune clé API en dur** (échec sécurité automatique, §VI.3).
      ⚠️ Le patch du `.venv` (workaround moulinette) ne doit PAS partir dans le rendu.

---

## 🧪 Pistes optionnelles (bonus benchmark)

- [ ] **Support tool-calling natif** pour les modèles `gpt-oss-*` / `groq/compound`
      (déclarer les tools en natif + `tool_choice: auto`, parser `message.tool_calls`,
      traduire en appel Python). Permettrait de les inclure au rapport. Gros morceau,
      branche séparée dans `GroqClient` + l'extracteur (§V.1 encadré formats).
- [ ] **Détection de soumissions répétées** : si le modèle resoumet 2× la même réponse
      rejetée, durcir le feedback / arrêter tôt au lieu de boucler jusqu'aux limites.

---

## ✅ Déjà fait

### Socle

- Boucle agent Thought → Code → Observation (`core/agent/agent.py`)
- Sandbox isolé en process séparé : imports/open/socket/exec bloqués, RAM (`setrlimit`),
  timeout, `final_answer` injecté, bridge MCP via Pipe (`core/sandbox/sandbox.py`)
- Config sandbox Pydantic (`core/sandbox/config.py`)
- Client LLM Groq + rotation multi-clés, back-off 429 **et 413** (`core/llm/`)
- Extracteur de code (python / XML / JSON-Hermes / ReAct) (`core/extractor/`)
- Client MCP stdio + HTTP, manuel dynamique (`core/mcp/client.py`)
- CLI sandbox interactif, tools MBPP + tools SWE-bench complets

### Agent SWE-bench branché (MCP client, env vars, manuel dans le prompt)

### Limites & robustesse (§VI)

- Limites dures MBPP / SWE-bench appliquées ; arrêt sur tokens cumulés
- **`max_tokens_per_call`** séparé du budget total → corrige le dépassement TPM free tier
