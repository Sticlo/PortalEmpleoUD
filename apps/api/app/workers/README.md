# Workers

Jobs en background (no bloquear la API HTTP):

- Generación de HV en cola (picos de 100+ estudiantes)
- Ingest de ofertas (fuentes externas)
- Expirar ofertas > 24h

MVP: la HV puede ir síncrona. Cuando haya carga real, mover `cv/adapt` a worker.
