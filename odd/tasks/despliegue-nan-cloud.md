# Despliegue en NaN Cloud

> Owner: Albert · Rama: `feat/despliegue-nan-cloud` · Estado: en curso

## Specs

- **S1 · Desplegar en NaN Cloud.** "Vamos a desplegarlo aqui en nan cloud. Preparalo todo [captura de `cloud.nan.builders/apps/new`] y en vez del puerto el 8000 le he puesto, hazlo en una rama a parte y cuando este todo ok, merge a dev, hazlo bien." El repositorio debe quedar listo para crear las apps en NaN Cloud, en una rama aparte, y mergearse a `dev` solo cuando los checks estén verdes.
- **S2 · Lista completa de variables.** "y a dime todas las keys y de database url y eso que hemos de poner en variables de entorno. no te dejes nada": hay que entregar la lista exhaustiva de variables, con valor, servicio y obligatoriedad, incluida la cadena de conexión.
- **S3 · Puerto coherente.** El puerto que se escribe en el formulario de NaN Cloud debe coincidir con el que escucha el contenedor. La captura muestra `3080`; el contenedor arranca en `${PORT:-8000}`.
- **S4 · Los PDFs sobreviven.** NaN Cloud solo da almacenamiento persistente a las apps marcadas como persistentes; los PDFs subidos tienen que quedar en un volumen, no en el sistema de ficheros efímero.
- **S5 · Sin base de datos gestionada.** NaN Cloud no ofrece Postgres, así que la `DATABASE_URL` viene de un Postgres externo y debe entrar tal cual la entrega el proveedor.

## Tasks

- [x] **T1** `frontend/Dockerfile`: aceptar `VITE_API_URL` como build argument (Vite lo incrusta al compilar) — cubre S1
- [x] **T2** `docs/deploy-nan-cloud.md`: dos apps, Postgres externo, puertos, volumen y verificación — cubre S1, S3, S4, S5
- [x] **T3** Tabla exhaustiva de variables de entorno en la guía — cubre S2

## Log

- **L1** (2026-11-13, Albert): "Vamos a desplegarlo aqui en nan cloud. Preparalo todo [captura] y en vez del puerto el 8000 le he puesto, hazlo en una rama a parte y cuando este todo ok, merge a dev, hazlo bien. y a dime todas las keys y de database url y eso que hemos de poner en variables de entorno. no te dejes nada"
- **L2** (2026-11-13, capacidades verificadas en `nan.builders/docs/apps`): NaN Cloud despliega **un contenedor por app** desde un repo de GitHub con Dockerfile; el puerto interno se escribe en el formulario y **no** se inyecta ninguna variable `PORT`; las variables de entorno admiten valores de **runtime y de build**; el disco se reparte por PVC y **solo lo usan las apps marcadas como persistentes** (Basic: 2 vCPU, 4 GiB RAM, 20 GiB disco, 5 pods); no hay base de datos gestionada; cada push a la rama configurada redeploya si el auto-deploy está activo.
- **L3** (2026-11-13, decisión de arquitectura): **dos apps**, no una. Servir el SPA desde el mismo contenedor que la API obligaría a prefijar todas las rutas del backend con `/api`, porque el SPA y la API comparten `/perfil` y `/licitaciones/{id}`; eso toca todos los tests y el cliente. Con dos apps la arquitectura no cambia respecto de `docker compose`, solo cambia dónde se ejecuta cada pieza. El API corre con 1 réplica y volumen en `/app/storage`; la web es un nginx estático que escucha en 80.
- **L4** (2026-11-13, verificación de T1): la imagen del frontend construida con `--build-arg VITE_API_URL=https://radar-api.example.test` incrusta esa URL en el bundle de `assets/`, comprobado con `grep` dentro del contenedor.
