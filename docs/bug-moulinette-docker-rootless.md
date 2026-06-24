# Bug : `moulinette_eval validate swebench` échoue sur Docker rootless (comptes à UID élevé)

## Symptôme

Toute validation SWE-bench échoue en `Correctness: FAILED`, alors que la
solution est correcte. Erreur :

```
Error validating solution: 500 Server Error for
http+docker://.../containers/<id>/archive?path=%2Ftmp:
Internal Server Error ("failed to Lchown "/tmp/patch.diff" for UID 102483, GID 4225:
lchown /tmp/patch.diff: invalid argument")
```

La validation **plante avant d'appliquer le patch et de lancer les tests** —
le verdict ne reflète donc pas la solution.

## Cause racine

- Docker tourne en **mode rootless** (`unix:///run/user/<uid>/docker.sock`).
- Les comptes 42 ont un **UID hôte élevé** (ici 102483), avec
  `/etc/subuid` = `user:202483:65536`.
- Le user-namespace du conteneur ne mappe donc que les IDs **0 → 65536**
  (uid hôte → 0, puis subuids `202483…268018` → `1…65536`).
- `swebench.harness.docker_utils.copy_to_container` construit le tar avec
  `tar.add(src, arcname=dst.name)`, qui **préserve l'UID/GID hôte du fichier**
  (102483).
- À l'extraction (`put_archive`), le démon fait `lchown(..., 102483, ...)`
  dans le namespace ; `102483 > 65536` → non mappé → `EINVAL` → 500.

C'est donc une incompatibilité **harness SWE-bench × Docker rootless × UID
hôte > taille de la plage subuid**. Rien à voir avec le rendu étudiant.

## Correctif recommandé (côté moulinette)

Forcer uid/gid à 0 dans le tar (le fichier devient root du namespace, qui
remappe vers l'uid hôte → `lchown(...,0,0)` réussit toujours). Dans
`copy_to_container` :

```python
def _root(ti):
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = "root"
    return ti
tar.add(src, arcname=dst.name, filter=_root)
```

Comme `copy_to_container` vient du package `swebench`, le plus propre est de
**wrapper/monkeypatcher** cette fonction dans la moulinette plutôt que de
patcher le `.venv`.

## Alternatives

- Faire tourner le grading sur un **Docker rootful** (le `lchown` vers un UID
  arbitraire y est autorisé).
- Élargir la plage `/etc/subuid` / `/etc/subgid` pour couvrir l'UID hôte
  (nécessite l'admin).

## Impact / question pour le staff

Sur quelle config le grading **officiel** tourne-t-il ?

- Si c'est **rootful**, les rendus passent côté staff malgré l'échec local.
- Si c'est la **même config rootless**, **tous les rendus SWE-bench sont
  faussement notés FAILED** et le correctif ci-dessus est nécessaire.

## Repro / diagnostic (commandes utiles)

```sh
id                                   # uid hôte (102483)
docker info | grep -i rootless       # confirme le mode rootless
grep "$(whoami)" /etc/subuid /etc/subgid   # plage = 65536, base 202483
```

## Workaround local (pour vérifier ses propres solutions)

Patch temporaire de `.venv/.../swebench/harness/docker_utils.py`
(`copy_to_container`) avec le `filter=_root` ci-dessus. À NE PAS confondre
avec le rendu : c'est une modif locale du package, pas du projet étudiant.
