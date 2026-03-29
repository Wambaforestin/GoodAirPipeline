## Fuseau horaire

### Choix : Europe/Paris

Le pipeline est configuré pour que l'IDTemps (clé temporelle du Data Warehouse) corresponde à l'heure locale française. Quand il est 12h à Paris, l'IDTemps enregistré est `...12`.

Ce choix est cohérent avec le contexte métier : les villes surveillées sont françaises, les chercheurs sont en France, et les analyses seront faites en heure locale.

**Implémentation (2 niveaux) :**

1. **Docker-compose** — l'interface Airflow et le scheduling affichent l'heure Paris :
   ```yaml
   AIRFLOW__CORE__DEFAULT_TIMEZONE: 'Europe/Paris'
   AIRFLOW__WEBSERVER__DEFAULT_UI_TIMEZONE: 'Europe/Paris'
   ```

2. **Code Python** — le `logical_date` d'Airflow est toujours en UTC en interne, même avec le timezone Paris configuré. Une fonction `to_paris_time()` dans `connections.py` convertit le datetime UTC en heure Paris avant de générer l'IDTemps :
   ```python
   from zoneinfo import ZoneInfo
   PARIS_TZ = ZoneInfo("Europe/Paris")

   def to_paris_time(dt):
       return dt.astimezone(PARIS_TZ)
   ```
   Cette conversion est appelée une seule fois dans le DAG, au point d'entrée de chaque task. Toutes les fonctions en aval reçoivent directement l'heure Paris.

### Alternative non retenue : UTC avec affichage Paris

L'autre approche consiste à garder le scheduling et les données en UTC, et ne changer que l'affichage de l'interface Airflow. C'est l'approche standard en entreprise pour les pipelines multi-pays. Elle n'a pas été retenue ici car elle crée un décalage de 1 à 2 heures entre l'IDTemps et l'heure réelle française, ce qui est perturbant pour un projet 100% France.

### DST (Changement d'heure) : ce qu'il faut savoir

Le DST (Daylight Saving Time) est le passage heure d'été ↔ heure d'hiver. En France il se produit 2 fois par an :

**Passage à l'heure d'été (dernier dimanche de mars)** : à 2h du matin, les horloges avancent à 3h. L'intervalle 2h-3h n'existe pas. Le pipeline peut sauter un créneau → un trou d'1 heure dans les données.

**Passage à l'heure d'hiver (dernier dimanche d'octobre)** : à 3h du matin, les horloges reculent à 2h. L'intervalle 2h-3h existe deux fois. Le pipeline peut tenter d'insérer un doublon → conflit de clé primaire sur IDTemps, résolu automatiquement par le retry Airflow et le MERGE (UPSERT).

**Actions à effectuer lors d'un changement d'heure :**

1. Vérifier le lendemain que le pipeline a bien tourné pendant la nuit :
   ```sql
   SELECT IDTemps, COUNT(*) AS NbVilles
   FROM Gold.FactMesures
   WHERE IDTemps LIKE '20261025%'
   ORDER BY IDTemps;
   ```
2. Si un créneau est manquant (trou) : c'est attendu, pas d'action nécessaire.
3. Si un run a échoué sur un conflit de clé : le retry Airflow le résout via le MERGE (UPSERT).

**Prochain changement d'heure :** 25 octobre 2026 (passage à l'heure d'hiver).