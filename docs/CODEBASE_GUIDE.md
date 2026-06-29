# Agent Smith — Guide complet de la codebase

> Document d'onboarding pour un nouvel arrivant sur le projet.
> Objectif : connaître le code sur le bout des doigts, comme si c'était le tien.
> Lis-le de haut en bas une première fois, puis garde-le ouvert à côté du code.

---

## Table des matières

1. [Le projet en deux phrases](#1-le-projet-en-deux-phrases)
2. [Le sujet : ce que la moulinette attend de nous](#2-le-sujet--ce-que-la-moulinette-attend-de-nous)
3. [Vue d'ensemble de l'architecture](#3-vue-densemble-de-larchitecture)
4. [Arborescence du dépôt](#4-arborescence-du-dépôt)
5. [Le flux complet d'une tâche, pas à pas](#5-le-flux-complet-dune-tâche-pas-à-pas)
6. [Module par module, fichier par fichier](#6-module-par-module-fichier-par-fichier)
   - [6.1 `core/llm` — appels modèle, clés, retries](#61-corellm--appels-modèle-clés-retries)
   - [6.2 `core/extractor` — extraction de code](#62-coreextractor--extraction-de-code)
   - [6.3 `core/sandbox` — exécution isolée](#63-coresandbox--exécution-isolée)
   - [6.4 `core/mcp` — client MCP](#64-coremcp--client-mcp)
   - [6.5 `core/agent` — la boucle](#65-coreagent--la-boucle)
   - [6.6 `core/cli` + entrypoints](#66-corecli--entrypoints-agent_mbpp-agent_swebench-sandbox_cli)
   - [6.7 `models/` — contrat Pydantic](#67-models--le-contrat-pydantic)
   - [6.8 Les serveurs MCP (`mcp_tools_*.py`)](#68-les-serveurs-mcp-racine-du-repo)
   - [6.9 La moulinette](#69-la-moulinette-évaluateur)
7. [Sécurité du sandbox : la checklist d'évaluation](#7-sécurité-du-sandbox--la-checklist-dévaluation)
8. [Les limites dures et où elles sont appliquées](#8-les-limites-dures-et-où-elles-sont-appliquées)
9. [Lancer le projet soi-même](#9-lancer-le-projet-soi-même)
10. [Points subtils / pièges à connaître](#10-points-subtils--pièges-à-connaître)
11. [Ce qui reste à faire](#11-ce-qui-reste-à-faire)

---

## 1. Le projet en deux phrases

On construit un **Code Agent** : un système autonome qui, face à une tâche de
programmation, **raisonne, écrit du code Python, l'exécute dans un sandbox
sécurisé, observe le résultat, et recommence** jusqu'à résoudre la tâche. Le
paradigme central est la boucle **Thought → Code → Observation**.

L'agent est évalué sur deux benchmarks :

- **MBPP** (*Mostly Basic Python Problems*) : petits problèmes algorithmiques,
  une fonction à écrire.
- **SWE-bench** (Verified) : vrais bugs dans de vrais dépôts (sympy, django,
  scikit-learn…), à corriger dans un conteneur Docker et à rendre sous forme
  de patch git.

La spécificité demandée par le sujet est le **code-based tool calling** : au
lieu d'appeler les outils via du JSON, le LLM **écrit du code Python** qui
appelle directement les outils (`result = read_file("x.py"); print(result)`).
C'est plus expressif : variables persistantes, boucles, logique conditionnelle.

---

## 2. Le sujet : ce que la moulinette attend de nous

(Source : `en.subject.pdf`. Voici l'essentiel, condensé.)

**Parties obligatoires :**

| Partie | Ce qu'il faut livrer | Où c'est dans notre code |
|---|---|---|
| Framework agentique | Boucle Thought→Code→Observation, extraction de code multi-format, exécution sandbox, feedback au LLM | `core/agent`, `core/extractor`, `core/sandbox` |
| Sandbox | CLI sandbox, `final_answer` injecté, restrictions (imports/fs/réseau/timeout/RAM/builtins), config Pydantic+JSON, manuel dynamique, MCP stdio **et** HTTP | `core/sandbox`, `sandbox_cli.py`, `core/mcp` |
| Agent MBPP | CLI, outil `run_tests`, modèles Pydantic | `agent_mbpp.py`, `mcp_tools_mbpp.py`, `models/mbpp.py` |
| Agent SWE-bench | CLI, tous les outils obligatoires, Docker, patch git | `agent_swebench.py`, `mcp_tools_swebench.py`, `models/swebench.py` |
| Outils obligatoires | `read_file`, `edit_file`, `list_files`, `search_code`, `search_function_or_class_definition_in_code`, `find_references`, `run_tests`, `get_patch`, `run_command` | `mcp_tools_swebench.py` |
| Multi-providers / multi-clés | Support de plusieurs providers OpenAI-compatibles, rotation de clés, fallback | `core/llm` |
| Usage tracking | tokens, retries, latence, requêtes | `models/*`, agrégé dans `agent.py` |
| Rapport de benchmark | `BENCHMARK_REPORT.md` (≥5 modèles × ≥3 tâches SWE-bench) | **à faire** (voir §11) |
| README | en anglais, sections imposées | **à faire** (voir §11) |

**Contraintes techniques imposées :**

- Python **3.10**, gestionnaire **`uv`**.
- **Interdiction** d'utiliser une lib qui ré-implémente l'orchestration
  d'agent (`smolagents`, `langgraph`, `crewai`, `autogen`, `llama-index`…).
  **La boucle est notre code.**
- Sécurité sandbox **uniquement** avec la lib standard (pas de
  `RestrictedPython`).
- **Aucune clé API en dur** → échec sécurité automatique, note 0.
- **Tout doit tourner en free tier**, multi-tokens obligatoire.
- L'agent doit résoudre les tâches par **exploration légitime**, pas en
  récupérant la solution depuis une PR / issue / sa mémoire d'entraînement →
  d'où les champs `system_prompt`, `llm_output`, `sandbox_input`,
  `sandbox_output` dans la sortie, qui servent à tracer le raisonnement.

**Limites dures** (dépassement = échec de la tâche) :

| Métrique | MBPP | SWE-bench |
|---|---|---|
| Itérations max | 10 | 30 |
| Input tokens max | 6 000 | 300 000 |
| Output tokens max | 1 500 | 10 000 |
| Timeout | 120 s | 900 s |

**Critères de passage :** MBPP 4/5, SWE-bench 2/3. Pendant la review, on nous
demandera de faire une **petite modif live** de l'agent et de le re-lancer →
d'où l'intérêt de connaître ce document.

---

## 3. Vue d'ensemble de l'architecture

```
                          ┌──────────────────────────────────────┐
                          │            Agent (boucle)            │
                          │   core/agent/agent.py                │
                          │                                      │
   ┌────────────┐         │   1. messages → LLM.generate()       │
   │ LLM client │◀────────┤   2. extract code                    │
   │ core/llm   │  texte  │   3. sandbox.execute(code)           │
   └────────────┘────────▶│   4. observation → messages          │
                          │   5. détecte FINAL_ANSWER / limites  │
                          └───────────────┬──────────────────────┘
                                          │ code
                                          ▼
                          ┌──────────────────────────────────────┐
                          │      Sandbox  core/sandbox           │
                          │   process séparé, builtins bridés,   │
                          │   imports/fs/réseau bloqués,         │
                          │   timeout + RLIMIT mémoire,          │
                          │   final_answer() injecté            │
                          └───────────────┬──────────────────────┘
                                          │ appel d'outil (via Pipe)
                                          ▼
                          ┌──────────────────────────────────────┐
                          │      MCP client  core/mcp            │
                          └───────────────┬──────────────────────┘
                                          │ stdio / http
                                          ▼
                  ┌───────────────────────┴────────────────────────┐
                  │  Serveur MCP (process séparé)                  │
                  │  mcp_tools_mbpp.py   → run_tests (subprocess)  │
                  │  mcp_tools_swebench.py → outils Docker         │
                  └────────────────────────────────────────────────┘
```

**Cinq pièces, cinq responsabilités nettes :**

1. **Agent / Orchestrateur** : la boucle centrale. Appelle le LLM, extrait le
   code, le passe au sandbox, lit l'observation, recommence.
2. **Code Extraction** : transformation entre la réponse du LLM et le sandbox.
   Gère plusieurs formats (python, XML, JSON-Hermes, ReAct).
3. **Sandbox** : la frontière d'exécution. Applique les restrictions de
   sécurité. Contient un client MCP qui se connecte à un serveur MCP externe.
4. **`final_answer()`** : construit **du sandbox** (pas un outil MCP). Toujours
   présent, quel que soit le serveur MCP.
5. **Serveur(s) MCP** : process séparés (stdio ou HTTP). Exposent les outils.

Frontière de sécurité importante : **le sandbox enveloppe le client MCP**, pas
l'inverse. Le sandbox restreint ce que peut faire le code Python généré
(imports, chemins, timeout, mémoire). Les **actions des outils MCP se passent
en dehors du sandbox** (lire des fichiers dans Docker, lancer des tests…) et ne
sont pas soumises au timeout du sandbox.

---

## 4. Arborescence du dépôt

```
agent_smith/
├── en.subject.pdf            # le sujet
├── pyproject.toml            # paquet "agent-smith", scripts uv, config mypy
├── README.md                 # quasi vide (à écrire — livrable)
├── mcp_tools_mbpp.py         # serveur MCP MBPP (à la RACINE, exigé par le sujet)
├── mcp_tools_swebench.py     # serveur MCP SWE-bench (à la RACINE)
│
├── student/                  # NOTRE code (le rendu)
│   ├── .env                  # API_KEYS=... (jamais commité)
│   ├── .env.exemple          # gabarit
│   ├── agent_mbpp.py         # entrypoint CLI MBPP
│   ├── agent_swebench.py     # entrypoint CLI SWE-bench
│   ├── sandbox_cli.py        # CLI sandbox autonome (batch + interactif)
│   ├── models/
│   │   ├── mbpp.py           # MBPPTaskInput, StepMetrics, SolutionOutput
│   │   └── swebench.py       # SWEBenchTaskInput, StepMetrics, SolutionOutput
│   └── core/
│       ├── agent/agent.py    # LA boucle
│       ├── extractor/code_extractor.py
│       ├── sandbox/
│       │   ├── sandbox.py    # IsolatedWorker + Sandbox
│       │   └── config.py     # SandboxConfig (Pydantic)
│       ├── llm/
│       │   ├── clients.py    # BaseClient + OpenAICompatibleClient
│       │   ├── key_manager.py# rotation multi-clés
│       │   └── model.py      # LlmResponse
│       ├── mcp/client.py     # wrapper synchrone autour de la session MCP async
│       └── cli/base_agent.py # base abstraite des CLI d'agent
│
├── docs/                     # cette doc, TODO, notes de bug
└── benchmark_outputs/        # résultats par tâche (task.json + <modele>.json)
```

> **La moulinette ne fait PAS partie du rendu.** C'est l'évaluateur fourni par
> le staff : un outil externe qui dump les tâches (`task.json`) et valide nos
> solutions (correctness + métriques). On ne la modifie pas et elle ne vit pas
> dans notre dépôt ; on l'invoque via sa CLI `moulinette_eval` (voir §5 et §9).
> Le **contrat de schéma** qu'elle impose est ce qui compte pour nous, et il est
> reproduit dans nos propres modèles `student/models/` (voir §6.7).

---

## 5. Le flux complet d'une tâche, pas à pas

Prenons MBPP (SWE-bench est identique en structure, voir différences plus bas).

1. **Dump** : la moulinette écrit `task.json` (description, signature, tests
   publics). C'est l'entrée de notre agent.

2. **Lancement** : `uv run python -m agent_mbpp --task-file task.json
   --output solution.json --model-name <m> --provider-url <url>`.
   → `MBPPAgentCLI.run()` ([student/agent_mbpp.py](../student/agent_mbpp.py)).

3. **Setup** dans `run()` :
   - charge la tâche en `MBPPTaskInput` ;
   - lance le serveur MCP : `MCPClient(command="python mcp_tools_mbpp.py")`
     puis `.connect()` ;
   - crée le client LLM `OpenAICompatibleClient(model_name, base_url)` ;
   - crée `SandboxConfig`, `Sandbox(config, mcp_client)` ;
   - crée `Agent(client, sandbox, max_iterations=10, max_input=6000,
     max_output=1500, max_time=120)`.

4. **Construction du prompt** : le `task` (énoncé + tests + instructions) et le
   `system_prompt` (format de réponse, manuel des outils via
   `mcp_client.get_man()`, contraintes du sandbox via
   `config.describe_constraints()`, règles de vérification).

5. **La boucle** `agent.run(...)` ([core/agent/agent.py](../student/core/agent/agent.py)) :
   pour chaque itération :
   1. vérifie les limites (temps, tokens cumulés) → arrêt propre si dépassé ;
   2. `llm.generate(messages, stop=["<end_code>", "Observation:"], max_tokens=...)` ;
   3. `CodeExtractor.extract(response.content)` → code Python ;
   4. `sandbox.execute(code)` → observation (stdout, erreur, ou marqueur
      `<<<FINAL_ANSWER:...>>>`) ;
   5. enregistre un `StepMetrics`, ajoute la paire assistant/observation aux
      messages ;
   6. si l'observation contient `<<<FINAL_ANSWER:...>>>` :
      - si vide → renvoie un feedback et continue ;
      - si un `answer_validator` est fourni → on **revérifie réellement** la
        solution (re-run des tests). Rejet = feedback au LLM, on continue.
        Acceptée = `SolutionOutput(success=True)` et fin.

6. **Sauvegarde** : `_save_output(res)` sérialise le `SolutionOutput` en JSON.

7. **Validation** : `moulinette_eval validate mbpp task.json solution.json` :
   - **Correctness** : la moulinette **réexécute tous les tests** (y compris
     cachés) contre `solution.solution` ;
   - **Metrics** : itérations/tokens/temps ≤ limites.

**Différences SWE-bench :**
- `task.json` contient `docker_image`, `eval_script`, `problem_statement`,
  `hints_text`, `repo`. L'agent exporte `SWE_DOCKER_IMAGE` et `SWE_EVAL_SCRIPT`
  en variables d'environnement, lues par le serveur MCP.
- L'agent explore le code dans Docker via les outils, édite des fichiers, lance
  `run_tests()`, et soumet `final_answer(get_patch())`.
- Le `validate_answer` relance le vrai `eval_script` et juge par **code de
  sortie 0 ET absence de marqueurs d'échec** (certains scripts, ex. `bin/test`
  de sympy, renvoient 0 même quand des tests échouent).

---

## 6. Module par module, fichier par fichier

### 6.1 `core/llm` — appels modèle, clés, retries

**`model.py`** — un seul modèle Pydantic, `LlmResponse` : `input_tokens`,
`output_tokens`, `content`, `request_time_ms`, `model_name`, `attempts`. C'est
le retour normalisé d'un appel LLM, quel que soit le provider.

**`key_manager.py`** — `KeyManager`. Lit `API_KEYS` (séparées par virgules)
depuis l'environnement. Maintient :
- `__keys` : le pool ;
- `__dead` : ensemble des clés rejetées définitivement (HTTP 401/403) — on ne
  les réessaie plus de toute la run ;
- `current_key`, et un `__index` pour la rotation.

Méthodes clés :
- `rotate_key()` : avance vers la prochaine clé **non morte** (parcourt le pool
  circulairement), renvoie `None` si toutes sont mortes ;
- `mark_current_dead()` : marque la courante comme invalide ;
- propriétés `has_live_keys`, `live_count`, `key_count`.

Le design est **provider-agnostique** : le même pool est essayé contre
n'importe quelle URL ; une clé du mauvais provider est marquée morte au premier
401/403 et ne pollue plus les essais.

**`clients.py`** — le cœur réseau.

- `BaseClient(ABC)` : interface. Stocke `model_name`, `base_url`, un
  `KeyManager`. Méthode abstraite `generate(messages, stop_sequences,
  max_tokens) -> LlmResponse`. → permet d'ajouter d'autres clients sans toucher
  l'agent (abstraction multi-providers exigée par le sujet).

- `OpenAICompatibleClient` : marche avec **tout** provider exposant
  `/chat/completions` (Groq, OpenRouter, l'URL OpenAI-compatible de Gemini…).
  Le provider est choisi **uniquement par `base_url`**.

`generate()` construit le payload (`messages`, `model`, `tool_choice: "none"`
car on fait du code-based tool calling, pas de tool calling natif ; ajoute
`stop` et `max_tokens` si fournis), puis boucle avec une **gestion d'erreurs
très complète** :

| Statut HTTP | Comportement |
|---|---|
| 200 | extrait `content` (ou `reasoning_content`/`reasoning` en repli), lit `usage`, renvoie `LlmResponse` |
| 429 (ou 413 + `rate_limit_exceeded`) | **rotation de clé d'abord** (balaye toutes les clés vivantes), puis seulement quand toutes sont throttlées, back-off via `Retry-After` ; abandon si l'attente dépasse `RATE_LIMIT_MAX_WAIT=120` s ou après 6 cycles |
| 400/401/403 | marque la clé morte, passe à la suivante ; abandon si plus aucune clé |
| ≥ 500 | back-off exponentiel plafonné (max 30 s), 4 tentatives |
| erreur réseau (`RequestException`) | back-off exponentiel, 4 tentatives |
| autre | lève `ValueError` |

`_parse_retry_after()` lit le délai d'attente depuis : header `Retry-After`
(Groq), `retry-after-ms` (Groq), ou le corps JSON (`"retryDelay": "23s"` /
`retry in 23s`, style Gemini). Sinon `default`.

> **Subtilité importante :** `attempts` (compté ici) devient `retries` dans les
> métriques. C'est le nombre de tentatives HTTP avant succès, pas le nombre
> d'itérations de l'agent.

### 6.2 `core/extractor` — extraction de code

**`code_extractor.py`** — `CodeExtractor`, méthodes statiques. Transforme la
sortie texte du LLM en code Python exécutable. Tout passe par `extract()` :

1. **Strip reasoning** d'abord : retire les blocs `<thought>…</thought>` /
   `<think>…</think>`. Les modèles « thinking » (ex. Gemma) mettent des blocs
   ```python exploratoires dans leur raisonnement ; on veut l'action finale,
   pas le brouillon. On essaie donc le texte **nettoyé** en premier, et le
   texte original en repli (au cas où tout le code vivait dans le raisonnement).
2. Pour chaque candidat (nettoyé, puis brut), on essaie les extracteurs dans
   l'ordre, premier match gagne :
   - `_extract_python_block` : ` ```python … ``` ` (fence de fin **optionnelle** :
     si le modèle est coupé par la stop-sequence, on prend jusqu'à la fin) ;
   - `_extract_xml_tool_call` : `<invoke name="..."><parameter…></invoke>`
     (style Anthropic) → converti en `result = func(args)` ;
   - `_extract_json_tool_call` : `<tool_call>{json}</tool_call>` (Hermes) ;
   - `_extract_react_format` : `Action: … / Action Input: {json}` (ReAct) ;
   - `_extract_final_answer_call` : `final_answer(...)` nu, hors fence.

`_format_value()` : un entier/flottant reste non quoté, le reste est mis entre
guillemets — pour reconstruire un appel Python valide à partir des formats non-
Python.

> **Pourquoi multi-format ?** Différents modèles, entraînés différemment, ne
> produisent pas tous des blocs ```python. Convertir tout en appels Python
> permet au sandbox de rester **agnostique au format** (exigence du sujet).

### 6.3 `core/sandbox` — exécution isolée

**`config.py`** — `SandboxConfig(BaseModel)`. Approche **allowlist** : seuls
les imports listés sont autorisés, tout le reste est bloqué. Champs :
`authorized_imports`, `allowed_directories` (`/testbed`, `/tmp/agent`),
`max_execution_time_seconds` (30 par défaut), `max_memory_mb` (512).

`describe_constraints()` rend ces limites en **texte prêt pour le prompt**.
Point de design : le prompt et l'application réelle des restrictions sont
**dérivés de la même config** → ils ne peuvent pas diverger. Change l'allowlist
ici, et chaque prompt qui embarque cette description suit.

**`sandbox.py`** — deux classes.

**`IsolatedWorker`** : ce qui tourne **dans le process enfant**. La méthode
statique `run(code, child_conn, config_dict, tool_names)` met en place **toutes
les restrictions de sécurité** :

- **Mémoire** : `resource.setrlimit(RLIMIT_AS, max_bytes)`.
- **Filesystem** : `builtins.open` est remplacé par `_safe_open` qui n'autorise
  que les chemins sous `allowed_dirs` (sinon `PermissionError`).
- **Imports** : `builtins.__import__` remplacé par `_safe_import` qui n'autorise
  que les modules de l'allowlist (sinon `ImportError`).
- **Réseau** : `socket.socket` remplacé par `_blocked_socket` (`PermissionError`).
- **Builtins dangereux** : `eval`, `exec`, `compile` sont **supprimés** des
  builtins (`delattr`). Le code utilisateur est exécuté via une **référence
  capturée avant suppression** (`_safe_exec = builtins.exec`).
- **Outils MCP** : pour chaque `tool_name`, un *stub* est injecté dans le
  namespace. Quand le code appelle un outil, le stub **envoie un message
  `CALL_TOOL` au parent via le Pipe** et attend la réponse (le vrai appel MCP a
  lieu côté parent, hors sandbox).
- **`final_answer`** : injecté ; envoie `FINAL_ANSWER` au parent et fait
  `sys.exit(0)`.
- **Capture stdout/stderr** dans un `StringIO`, restauré en `finally`.
- En sortie : envoie `SUCCESS`+output, ou `ERROR`+output+traceback.

**`Sandbox`** : ce qui tourne **dans le process parent** (l'orchestrateur).

- `__init__` : stocke la config, le client MCP, et la liste des noms d'outils
  (`tool_names`) à injecter dans l'enfant.
- `MAX_OBSERVATION_CHARS = 6000` + `_truncate()` : si une sortie d'outil est
  énorme (lister tout un repo…), on garde **tête + queue** et on insère un
  message explicite `[... output truncated ...]` — le LLM n'est jamais laissé à
  deviner ce qui a été coupé.
- `execute(code)` : le cœur.
  1. crée un `multiprocessing.Pipe`, lance `IsolatedWorker.run` dans un
     `Process`, **ferme la copie parent de `child_conn`** ;
  2. boucle tant que le process vit, en **pollant** `parent_conn` avec le
     `timeout` configuré ;
  3. sur `CALL_TOOL` : appelle réellement `mcp_client.call_tool(...)`, renvoie
     `{status: ok, result}` ou `{status: error, message}` ;
  4. sur `FINAL_ANSWER` : ajoute `<<<FINAL_ANSWER:...>>>` à la sortie, termine
     le process ;
  5. sur `SUCCESS`/`ERROR` : ajoute la sortie (tronquée) ;
  6. si `poll(timeout)` expire alors que le process vit toujours →
     **`terminate()` + retourne `"Error: execution has timed out."`**.
  7. à la fin, si rien n'a été imprimé → `"Code executed with success!"`.

> **Le timeout ne s'applique qu'au code du sandbox.** Un outil MCP qui lance un
> sous-process (ex. les tests Docker) n'est pas soumis à ce timeout — il a son
> propre timeout côté serveur MCP. C'est exactement ce que demande le sujet.

> **Choix d'isolation : process séparé** (et non thread / même process). Avantages :
> on peut vraiment **tuer** du code qui boucle (`terminate`), `setrlimit` est
> par-process, et la mémoire est isolée. Inconvénient : il faut un canal de
> communication (le Pipe) — d'où le protocole `CALL_TOOL`/`FINAL_ANSWER`.

### 6.4 `core/mcp` — client MCP

**`client.py`** — `MCPClient`. Wrapper **synchrone** au-dessus de la session
MCP **asynchrone** (la lib `mcp` est async ; tout le reste de notre code est
sync). Tour de passe-passe : un `asyncio` event loop privé (`self._loop`) et
`run_until_complete` pour chaque opération.

- `__init__(command=…, url=…)` : choisit le transport — **stdio** (`command`,
  lancé comme sous-process, on lui passe `SWE_DOCKER_IMAGE`/`SWE_EVAL_SCRIPT`
  dans l'env) ou **HTTP** (`url`). Les deux transports sont exigés par le sujet.
- `connect()` → `_connect_async()` : ouvre le transport, démarre la
  `ClientSession`, `initialize()`, puis **liste tools, resources, prompts**.
  Resources et prompts sont **optionnels** en MCP : si le serveur ne les
  supporte pas, l'exception est avalée (`_list_resources_async`,
  `_list_prompts_async`).
- `call_tool(name, args)` → `_call_tool_async` : appelle l'outil ; **si le
  serveur signale `isError`, on lève `RuntimeError`** — important : ça fait
  remonter l'échec d'un outil (ex. `edit_file` qui ne matche rien) dans
  l'observation du sandbox et **arrête le bloc de code**, au lieu d'être
  silencieusement ignoré quand le modèle n'imprime pas la valeur de retour.
- `get_tools()` : renvoie, pour chaque outil, un **wrapper callable** qui
  accepte args positionnels **et** kwargs (mappés via le schéma) — c'est ce qui
  permet d'appeler `read_file("x.py", 1, 50)` aussi bien que
  `read_file(filepath="x.py")`.
- `get_man()` : génère le **manuel dynamique** injecté dans le system prompt :
  pour chaque outil, nom + description + `inputSchema` ; idem resources/prompts.
  → quand on branche un **serveur MCP inconnu**, le manuel reflète
  automatiquement ses outils (exigence du sujet).
- `disconnect()` : ferme proprement session + transport + event loop.

### 6.5 `core/agent` — la boucle

**`agent.py`** — `Agent`. **C'est notre implémentation à nous** de
l'orchestration (le sujet interdit les libs d'agent).

`__init__` : `llm_client`, `sandbox`, et les budgets — `max_iterations`,
`max_input_tokens`, `max_output_tokens`, `max_total_time_seconds`, et
**`max_tokens_per_call`** (cap dur sur **une seule** requête). Ce dernier est
crucial : les providers comptent la **réservation** `prompt + max_tokens`
contre leur quota TPM ; une valeur trop grande fait sauter les limites du free
tier. Par défaut il vaut `max_output_tokens`.

`_check_limits(...)` : avant chaque itération, retourne un message d'arrêt si :
temps écoulé ≥ budget, output cumulé ≥ budget, ou (coût estimé de la prochaine
requête + input cumulé) ≥ budget input. Sinon `None`.

`run(task, system_prompt, task_id, benchmark, answer_validator)` : la boucle.

- initialise `messages = [system, user(task)]`, compteurs, `start_time`,
  `last_code`.
- pour `i in range(max_iterations)` :
  1. `_check_limits(...)` → si stop, retourne un `SolutionOutput(success=False,
     error=stop, solution=last_code)` ;
  2. `llm.generate(...)` dans un try/except (toute erreur LLM → `SolutionOutput`
     d'échec, pas de crash) ;
  3. cumule tokens et requêtes ;
  4. `CodeExtractor.extract(...)` :
     - si `None` → observation `"Error: No code block found."` (feedback
       explicite, pas de silence) ;
     - sinon → `last_code = code`, `sandbox.execute(code)` (lui aussi en
       try/except) ;
  5. append un `StepMetrics` complet (tokens, temps, url, modèle, llm_output,
     sandbox_input, sandbox_output, retries) ;
  6. append assistant + `Observation: …` aux messages ;
  7. cherche `<<<FINAL_ANSWER:(.*?)>>>` dans l'observation :
     - **vide** → remplace le dernier message par un feedback adapté
       (SWE-bench : « get_patch a probablement renvoyé un diff vide… » ; MBPP :
       « fournis la solution complète… ») et `continue` ;
     - **`answer_validator` fourni** → appelle le validateur ; s'il renvoie un
       message de rejet, on le réinjecte comme observation et `continue` ;
     - sinon → `SolutionOutput(success=True, solution=answer)` et **fin**.
- si on sort de la boucle sans succès → `SolutionOutput(success=False,
  error="Max iterations reached.")`.

> **Le validateur (`answer_validator`) est le garde-fou anti-triche/hallucination.**
> L'agent ne fait pas confiance au « j'ai réussi » du modèle : il **réexécute**
> les tests. Côté MBPP, re-run de `run_tests` avec les tests officiels. Côté
> SWE-bench, re-run de l'`eval_script`. Un faux positif est rejeté et renvoyé
> au modèle pour correction.

### 6.6 `core/cli` + entrypoints (`agent_mbpp`, `agent_swebench`, `sandbox_cli`)

**`cli/base_agent.py`** — `BaseAgentCLI(ABC)`. Factorise le commun des deux
agents : parse `--task-file`, `--output`, `--model-name`, `--provider-url`
(tous requis) ; `_save_output()` (écrit le `SolutionOutput` en JSON, crée le
dossier de sortie) ; méthodes abstraites `_load_task()` et `run()`.

**`agent_mbpp.py`** — `MBPPAgentCLI(BaseAgentCLI)`.
- `_load_task()` : `MBPPTaskInput(**json.load(...))`.
- `run()` : monte les composants (MCP `mcp_tools_mbpp.py`, client LLM, sandbox
  10 s, agent avec limites MBPP), construit le `task` (énoncé + tests + un
  appel `run_tests(...)` **modèle à recopier verbatim**) et le `system_prompt`
  (format ```python + `<end_code>`, **une seule** code block par tour, manuel
  des outils, contraintes sandbox, règles de vérification, consigne « tests
  verbatim, pas d'`assert` nu »).
- `validate_answer(code)` : réexécute `run_tests` avec les tests officiels ;
  rejette si `Error:`/`Traceback` apparaît.

**`agent_swebench.py`** — `SWEBenchAgentCLI(BaseAgentCLI)`.
- exporte `SWE_DOCKER_IMAGE` / `SWE_EVAL_SCRIPT` (lus par le serveur MCP) ;
- monte les composants (MCP `mcp_tools_swebench.py`, sandbox 30 s, agent limites
  SWE-bench, `max_tokens_per_call=2048`) ;
- `task` : énoncé + hints + méthodo (explore → édite → `run_tests` → soumettre
  `final_answer(get_patch())`) ;
- `validate_answer(patch)` : relance `run_tests`, juge par **exit code 0 ET
  absence de marqueurs d'échec** (`[FAIL]`, `FAILED (`, `N failed`,
  `=== FAILURES ===`, `Traceback`). Tronque le rapport à 4000 chars pour le
  feedback.

**`sandbox_cli.py`** — `SandboxCLI`, exposé en `uv run sandbox`. Deux modes :
- **batch (défaut)** : lit **tout stdin** comme un seul bloc, l'exécute une
  fois, imprime l'observation. Pour piper : `echo '<code>' | uv run sandbox
  --mcp-stdio "python mcp_tools_mbpp.py"` ;
- **`--interactive`** : REPL — on tape du code, `EXEC` exécute, `MAN` affiche le
  manuel des outils, `QUIT` quitte.

Args : `config` (chemin JSON optionnel), `--mcp-stdio`, `--mcp-server` (URL),
`--interactive`. C'est ce qui prouve que **les outils marchent indépendamment
de la boucle agent** (exigence du sujet).

### 6.7 `models/` — le contrat Pydantic

**`models/mbpp.py`** et **`models/swebench.py`** définissent les trois modèles
clés (versions quasi identiques, `swebench.py` est plus richement documenté) :

- **`MBPPTaskInput`** : `task_id`, `task_definition`, `function_definition`,
  `test_imports`, `test_list`.
- **`SWEBenchTaskInput`** : `instance_id`, `problem_statement`, `docker_image`,
  `eval_script`, `hints_text`, `repo`.
- **`StepMetrics`** : une entrée par itération — `step`, `input_tokens`,
  `output_tokens`, `request_time_ms`, `api_url`, `model_name`, `llm_output`,
  `sandbox_input`, `sandbox_output`, `retries`, `timestamp`.
- **`SolutionOutput`** : la sortie finale — `task_id`, `benchmark`, `success`,
  `solution` (code MBPP / patch SWE-bench), `system_prompt`, `iterations`,
  `total_requests`, `total_input_tokens`, `total_output_tokens`,
  `total_time_seconds`, `steps`, `error`, `timestamp`.

> **Ce schéma EST le contrat avec l'évaluateur.** Il doit correspondre
> exactement au schéma JSON attendu par la moulinette (l'outil externe de
> grading). Les champs `system_prompt`, `llm_output`, `sandbox_input`,
> `sandbox_output`, `retries` existent pour la **traçabilité anti-triche**
> (l'évaluateur vérifie que la solution vient d'une vraie exploration, pas d'une
> PR récupérée).

### 6.8 Les serveurs MCP (racine du repo)

Ils sont **à la racine** (`mcp_tools_mbpp.py`, `mcp_tools_swebench.py`), comme
exigé, pour pouvoir être testés indépendamment avec un MCP inconnu. Tous deux
utilisent `FastMCP` et s'enregistrent via `mcp.tool()`.

**`mcp_tools_mbpp.py`** — `MBPPTools`. Un seul outil :
- `run_tests(code, test_list, test_imports)` : assemble imports + code + tests
  dans un fichier temporaire, l'exécute via `subprocess.run([python, file])`
  avec timeout 30 s, renvoie stdout (+ stderr préfixé `Error:`). Gère
  `TimeoutExpired` et exceptions.

> Note : ce `run_tests` tourne **hors sandbox** (c'est un outil MCP), dans un
> sous-process Python distinct. C'est volontaire : la frontière sandbox protège
> le code généré, l'exécution des tests vit côté serveur MCP.

**`mcp_tools_swebench.py`** — `SWEBenchTools`. Backé par **Docker**. Lit
`SWE_DOCKER_IMAGE` / `SWE_EVAL_SCRIPT` à l'init (lève `ValueError` si absents).

Helpers :
- `_start_container()` : `docker run -d <image> sleep infinity` (lazy, une fois).
- `_exec(command, workdir=/testbed, timeout, input_data)` : `docker exec` du
  bash dans le conteneur, renvoie `{stdout, stderr, exit_code}`.

Les **9 outils obligatoires** :

| Outil | Implémentation |
|---|---|
| `read_file(filepath, start_line, end_line)` | `cat` + numérotation `N: ligne` (format `cat -n`) |
| `edit_file(filepath, old_str, new_str)` | remplace une chaîne **exacte** ; si absente, **lève** une erreur avec des **lignes similaires en indice** (ancre = ligne la plus longue de `old_str`) pour aider le modèle à recopier verbatim |
| `list_files(directory, pattern)` | `find -type f -name <pattern>` |
| `search_code(pattern, file_pattern)` | `grep -rEn`, format `/path:line contenu`, **plafonné à 100** résultats |
| `search_function_or_class_definition_in_code(name)` | `search_code("(def|class) name")` |
| `find_references(name)` | `search_code(name)` |
| `run_command(command, workdir)` | bash dans Docker, renvoie STDOUT/STDERR/EXIT_CODE formatés |
| `get_patch()` | `git -c core.fileMode=false diff` |
| `run_tests()` | lance l'`eval_script` (timeout 900 s), renvoie STDOUT/STDERR/EXIT_CODE |

`run()` lance le serveur et **nettoie le conteneur** (`docker rm -f`) dans un
`finally` — la propreté post-exécution est exigée par le sujet.

### 6.9 La moulinette — l'évaluateur externe (ne fait PAS partie du rendu)

⚠️ **La moulinette n'est pas dans notre dépôt rendu.** C'est l'outil de grading
fourni par le staff. On ne la modifie pas et on ne la livre pas : on l'utilise
juste comme une boîte noire pour **dump** les tâches et **valider** nos
solutions. Cette section explique seulement **comment elle nous juge**, pour
qu'on sache à quoi se conformer.

C'est une CLI Fire (`moulinette_eval`) qui expose :
- `dump benchmark [--task-id] [--seed] --output` : écrit `task.json` (l'entrée
  de notre agent) ;
- `validate benchmark task.json solution.json [--skip-metrics]` : **correctness**
  (réexécute tous les tests / relance l'eval Docker du patch) **+ metrics** ;
- `validate_metrics benchmark solution.json` : metrics seules ;
- `select swebench --count N [--seed]` : tire des tâches du pool d'examen ;
- `display solution.json [--full]` : pretty-print + **checks de cohérence**
  (system_prompt non vide, llm_output non vide, timestamps croissants, modèle
  constant, **détection de copier-coller** entre steps consécutifs…). C'est
  exactement ce que le correcteur regarde — utile pour s'auto-vérifier.

Ce qu'il faut retenir côté contrat :
- elle valide notre `solution.json` contre **le même schéma Pydantic** que celui
  reproduit dans `student/models/` (voir §6.7) — d'où l'importance de ne pas en
  dévier ;
- les **limites dures** qu'elle applique (itérations / tokens in-out / temps)
  sont celles du §8 : MBPP 10 / 6 000 / 1 500 / 120 s, SWE-bench 30 / 300 000 /
  10 000 / 900 s. Nos agents sont configurés sur ces mêmes valeurs ;
- pour un patch SWE-bench, elle vérifie d'abord que la solution **ressemble à un
  patch git** (`diff --git`, `--- a/`, `+++ b/`, `@@`) avant de lancer l'eval
  Docker.

---

## 7. Sécurité du sandbox : la checklist d'évaluation

`exam_sandbox.sh` teste **tout** (pass = ALL). Voici où chaque garantie est
implémentée, à savoir par cœur pour la défense :

| Test | Mécanisme | Où |
|---|---|---|
| Blocage d'import | `__import__` override + allowlist | `sandbox.py` `_safe_import` |
| Blocage de builtin | `eval`/`exec`/`compile` supprimés des builtins | `sandbox.py` (`delattr`) |
| Blocage réseau | `socket.socket` → `PermissionError` | `sandbox.py` `_blocked_socket` |
| Restriction de chemin | `open` override + `allowed_dirs` | `sandbox.py` `_safe_open` |
| Timeout | `parent_conn.poll(timeout)` + `terminate()` | `sandbox.py` `execute` |
| Limite mémoire | `setrlimit(RLIMIT_AS)` | `sandbox.py` `IsolatedWorker.run` |
| Protocole MCP | stub `CALL_TOOL` via Pipe → `mcp_client.call_tool` | `sandbox.py` + `mcp/client.py` |

Points fins à comprendre :
- Les restrictions sont posées **dans le process enfant**, pas le parent — elles
  ne s'appliquent qu'au code généré.
- `final_answer` n'est **pas** un outil MCP : c'est une fonction injectée par le
  sandbox lui-même, présente quel que soit le serveur MCP connecté.
- Le sujet exige que `KeyboardInterrupt`/`SystemExit` **ne soient pas avalés**
  silencieusement : ils doivent remonter à la boucle. Notre `final_answer` fait
  justement `sys.exit(0)` pour signaler la fin proprement.

---

## 8. Les limites dures et où elles sont appliquées

Triple cohérence à garder en tête :

1. **Côté agent** (proactif) : `Agent._check_limits` arrête **avant** de
   dépasser. Les valeurs viennent des entrypoints :
   - MBPP : `Agent(client, sandbox, 10, 6000, 1500, 120)` ;
   - SWE-bench : `Agent(client, sandbox, max_iterations=30,
     max_tokens_per_call=2048)` (les autres budgets gardent les défauts larges).
2. **Côté requête unique** : `max_tokens_per_call` borne la réservation TPM par
   appel (évite de faire sauter le free tier).
3. **Côté moulinette** (verdict) : `MetricsValidationResult.validate_solution`
   compare la sortie à `MetricsLimits` après coup.

Tokens **cumulés** sur toute la tâche, **reasoning tokens inclus** — d'où la
préférence pour des modèles **non-reasoning** quand les limites sont serrées.

---

## 9. Lancer le projet soi-même

```bash
# 0. Préparer les clés (jamais commiter .env !)
cp student/.env.exemple student/.env
# éditer student/.env :  API_KEYS=clé1,clé2,clé3

# 1. Installer NOTRE projet (à la racine, paquet agent-smith)
uv sync
# La moulinette est un outil EXTERNE (non rendu) : on l'installe à part, là où
# le staff l'a fournie, et on l'invoque via sa CLI `moulinette_eval` (étapes 3+).

# 2. Tester le sandbox seul (outils indépendants de l'agent)
echo 'print(run_tests(code="def f(): return 1", test_list=["assert f()==1"], test_imports=[]))' \
  | uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py"

# 3. Cycle MBPP complet
cd moulinette
uv run moulinette_eval dump mbpp --output ../cache/mbpp_task.json
cd ../student
uv run python -m agent_mbpp \
  --task-file ../cache/mbpp_task.json \
  --output ../cache/mbpp_solution.json \
  --model-name "meta-llama/llama-4-scout-17b-16e-instruct" \
  --provider-url "https://api.groq.com/openai/v1"
cd ../moulinette
uv run moulinette_eval validate mbpp ../cache/mbpp_task.json ../cache/mbpp_solution.json

# 4. Cycle SWE-bench : identique avec 'swebench' et agent_swebench
#    (nécessite Docker — voir docs/bug-moulinette-docker-rootless.md)
```

**Modèles connus qui marchent** (voir [docs/test_models.md](test_models.md)) :
`llama-4-scout-17b-16e-instruct`, `llama-3.3-70b-versatile`, `qwen3-32b` (Groq).
À éviter : les `gpt-oss-*` (incompatibles avec le code-based tool calling).

---

## 10. Points subtils / pièges à connaître

- **`tool_choice: "none"`** dans le payload LLM : on **désactive** le tool
  calling natif, parce qu'on fait du **code-based** tool calling. Le modèle doit
  écrire du code, pas renvoyer des `tool_calls` JSON.
- **Stop sequences `["<end_code>", "Observation:"]`** : essentielles. Sans
  elles, le modèle **hallucine** l'observation au lieu d'attendre la vraie
  exécution. Le system prompt insiste : « une seule code block par tour, puis
  STOP ».
- **`<<<FINAL_ANSWER:...>>>`** est un **marqueur texte** dans l'observation, pas
  une valeur structurée. C'est le pont entre le sandbox (qui ne connaît pas la
  boucle) et l'agent (qui parse l'observation par regex). Le sandbox écrit le
  marqueur, l'agent le détecte.
- **Le validateur peut rejeter une « réussite »** : un `success` claimé par le
  modèle ne suffit pas, on réexécute. C'est ce qui fait que `solution.json`
  reflète une vraie résolution.
- **`edit_file` exige un match byte-for-byte** : indentation et retours à la
  ligne compris. Quand ça échoue, l'erreur renvoie des lignes proches en indice
  — sans ça, le modèle tourne en rond.
- **Le `.venv` patché** (workaround Docker rootless,
  [docs/bug-moulinette-docker-rootless.md](bug-moulinette-docker-rootless.md))
  **ne doit JAMAIS partir dans le rendu** : c'est une modif locale d'un package
  tiers, pas du projet.
- **Bug Docker rootless** : sur les comptes 42 (UID élevé), la validation
  SWE-bench de la moulinette plante au `lchown` avant même d'appliquer le patch
  → faux `FAILED`. Détail + correctif recommandé dans le doc dédié. Question
  ouverte au staff : le grading officiel tourne-t-il en rootful ?
- **`get_patch()` peut renvoyer un diff vide** si le modèle n'a rien édité →
  l'agent renvoie un feedback spécifique pour l'inviter à vraiment modifier le
  code avant de re-soumettre.

---

## 11. Ce qui reste à faire

(D'après [docs/TODO.md](TODO.md), état au 2026-06-24. Les deux agents résolvent
réellement des tâches en free tier.)

**Restant — validation :**
- Tester avec un **serveur MCP inconnu** (vérifier la génération dynamique du
  manuel et des wrappers d'outils).

**Restant — livrables (Priorité 3) :**
- **`BENCHMARK_REPORT.md`** à la racine : setup, table de résultats (≥5 modèles
  × ≥3 tâches SWE-bench), fiabilité provider (temps moyen, retries, dispo), ≥2
  métriques intermédiaires, ≥1 étude d'ablation, conclusions. Garder les
  `solution.json` correspondants (déjà dans `benchmark_outputs/`).
- **`README.md`** (à la racine, en **anglais**) : première ligne en italique
  « _This project has been created as part of the 42 curriculum by <login>._ »,
  Description, Instructions, Resources (+ usage de l'IA), architecture système,
  boucle agent, design sandbox, détails outils, résultats de benchmark.
- **Hygiène de soumission** : pas d'images Docker / poids de modèles / outputs
  générés ; **aucune clé en dur** ; ne pas commiter le patch du `.venv`.

**Pistes bonus :**
- Support du **tool calling natif** pour `gpt-oss-*` / `groq/compound`
  (déclarer les tools, `tool_choice: auto`, parser `message.tool_calls`).
- **Détection de re-soumissions répétées** : si le modèle re-soumet 2× la même
  réponse rejetée, durcir le feedback ou arrêter tôt.

---

## En résumé — la mentalité du code

Trois principes guident toute la base, garde-les en tête :

1. **Le LLM ne doit jamais deviner.** Chaque échec (pas de code, timeout,
   troncature, outil en erreur) produit une **observation explicite** renvoyée
   au modèle.
2. **On ne fait pas confiance au modèle sur parole.** Toute « réussite » est
   **revérifiée** par réexécution réelle des tests (`answer_validator`).
3. **Une seule source de vérité par préoccupation.** La config sandbox génère à
   la fois l'application des règles **et** le texte du prompt ; le manuel est
   généré depuis les schémas MCP réels ; les limites de l'agent reflètent celles
   de la moulinette. Rien ne peut diverger silencieusement.
