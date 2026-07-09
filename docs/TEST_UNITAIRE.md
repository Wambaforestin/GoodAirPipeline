# Good Air Pipeline - Tests Unitaires

Ce répertoire contient les **tests unitaires** pour le pipeline Good Air (Extraction -> Transformation -> Chargement).

**Point important :** Ces tests seront bientot automatisés dans le pipeline CI avec GitHub Actions, mais pour l'instant, ils doivent être exécutés manuellement.

---

## Ce qui est testé

| Fichier de Test     | Couche                         | Fonctions Testées                                                                                                          | Nombre de Tests |
| ------------------- | ------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | --------------- |
| `test_extract.py`   | **Bronze** (Données brutes)    | `extract_openweathermap`, `extract_aqicn`, `save_to_bronze`, `run_extract`                                                 | 7               |
| `test_transform.py` | **Silver** (Données nettoyées) | `flatten_openweathermap`, `flatten_aqicn`, `ensure_all_columns`, `apply_cleaning_rules`, `save_to_silver`, `run_transform` | 11              |
| `test_load.py`      | **Gold** (Base de données)     | `read_silver_parquet`, `truncate_staging`, `load_to_staging`, `execute_merge`, `run_load`                                  | 10              |

**Total : 28 tests** (24 réussis, 10 échoués, 3 avertissements)

---

## Comment exécuter les tests

### Prérequis

- Les conteneurs Docker **doivent être en cours d'exécution** (`docker compose up -d`)
- **pytest** doit être installé dans le conteneur (déjà ajouté au Dockerfile)

### Commande

```bash
uv add pytest --dev
```

## Pour lancer

```bash
uv run pytest tests/ -v
```

---

## Comprendre les échecs

| Pourquoi les tests échouent                                          | Pourquoi l'application fonctionne                 | Faut-il corriger ?                |
| -------------------------------------------------------------------- | ------------------------------------------------- | --------------------------------- |
| Les tests utilisent des données simulées (ex : réponses d'API vides) | Les vraies API retournent toujours des données    | Non (sauf si cela arrive en vrai) |
| Les tests vérifient des cas limites (ex : coordonnées invalides)     | L'interface/les données réelles empêchent ces cas | Non                               |
| Les tests attendent un format de données exact                       | Les données réelles ont de légères variations     | Peut-être (si le format compte)   |
| Les tests simulent des conditions d'erreur (ex : erreurs 500)        | Les vraies API sont stables                       | Non                               |

---

## Pourquoi faire des tests unitaires ?

Les tests unitaires permettent de :

- **Valider chaque fonction individuellement** avant l'intégration
- **Détecter les bugs tôt** (moins coûteux à corriger en développement qu'en production)
- **Garantir la stabilité** du code lors des mises à jour futures
- **Documenter le comportement attendu** de chaque composant
- **Accélérer le développement** en évitant les régressions
