# Compass Rose

Pipelines de dados ponta a ponta. O núcleo do projeto é o uso de features do Apache Airflow.

As fontes são a API pública [Open-Meteo](https://open-meteo.com/en/docs) e o Cloud Storage, com arquivos colocados manualmente para sensores e conexões externas. O desenho do pipeline ainda está em aberto.

## Stack

- Astro CLI
- Astro Runtime `3.3-11` (Airflow 3, Python 3.11)

## Estrutura

- `dags/` — DAGs
- `include/` — arquivos de apoio usados pelas tarefas
- `plugins/` — plugins do Airflow
- `tests/` — testes
- `Dockerfile`, `requirements.txt`, `packages.txt` — imagem e dependências

## Ambiente local

```bash
astro dev start
astro dev parse
astro dev stop
```
