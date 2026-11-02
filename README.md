# Compass Rose

Pipelines de dados ponta a ponta. O núcleo do projeto é o uso de features do Apache Airflow.

O caso é o clima diário das cidades monitoradas. A [Open-Meteo](https://open-meteo.com/en/docs) devolve a série de cada cidade. O CSV manual entra com o que a API não tem e o que o relatório usa: a região e o limite de chuva. A tabela final entra no BigQuery, uma view cruza os dois lados e o [Data Studio](https://docs.cloud.google.com/data-studio/welcome) mostra o painel.

## Fontes

O arquivo para o Cloud Storage, usado só no desenvolvimento local, é [input/locations.csv](input/locations.csv). `location_name` só escolhe a cidade, porque a previsão não devolve o nome. `region` e `rain_limit_mm` são o complemento: a região agrupa o painel e o limite diz, em milímetros, a partir de quanto a chuva do dia importa para aquela cidade. O exemplo traz São Paulo, Rio de Janeiro, Belo Horizonte e Porto Alegre. Latitude, longitude e fuso vêm da resposta da API.

O script localiza cada cidade na [Geocoding API](https://open-meteo.com/en/docs/geocoding-api) e consulta a previsão com `timezone=auto` e `daily=temperature_2m_max,temperature_2m_min,precipitation_sum`.

Sem datas, a chamada usa `past_days=30` e `forecast_days=7` e substitui o CSV inteiro. Com `--start-date` e `--end-date`, o intervalo segue o data interval do Airflow: início inclusivo e fim exclusivo. A previsão aceita `start_date` e `end_date` só na janela recente. Fora dela, a mesma data vai para a [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api). Cada execução troca apenas as linhas daquele intervalo, então um backfill ou catchup pode repetir um dia sem apagar os outros.

## Tabela final

`include/ingest_daily_weather.py` grava `output/daily_weather.csv`. Esse CSV é o substituto temporário da tabela `daily_weather` no BigQuery. A carga ainda não faz parte deste repositório.

| Coluna | Conteúdo |
| --- | --- |
| `location_name` | Cidade usada para buscar a série |
| `region` | Região do CSV manual |
| `rain_limit_mm` | Limite de chuva do CSV manual, em mm |
| `latitude` | Latitude devolvida pela previsão |
| `longitude` | Longitude devolvida pela previsão |
| `timezone` | Fuso devolvido pela previsão |
| `date` | Dia da série |
| `temperature_max_c` | Máxima diária em °C |
| `temperature_min_c` | Mínima diária em °C |
| `precipitation_mm` | Precipitação diária em mm |

O tratamento fica na view `daily_weather_report`:

```sql
CREATE OR REPLACE VIEW `project.dataset.daily_weather_report` AS
SELECT
  location_name,
  region,
  rain_limit_mm,
  latitude,
  longitude,
  timezone,
  date,
  temperature_max_c,
  temperature_min_c,
  precipitation_mm,
  precipitation_mm >= rain_limit_mm AS over_rain_limit,
  AVG(temperature_max_c) OVER (
    PARTITION BY location_name
    ORDER BY date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  ) AS temperature_max_7d_avg
FROM `project.dataset.daily_weather`;
```

## Data Studio

O painel lê `daily_weather_report`:

- Série temporal de `temperature_max_c` por `location_name`, no eixo `date`.
- Barras da contagem de `over_rain_limit` por `region`.
- Controle de intervalo de datas sobre `date`.

## Ingestão local

```bash
python include/ingest_daily_weather.py
python include/ingest_daily_weather.py --start-date 2026-10-15 --end-date 2026-10-16
```

A pasta `output/` fica fora do git.

## Stack

- Astro CLI
- Astro Runtime `3.3-11` (Airflow 3, Python 3.11)

## Estrutura

- `dags/` — DAGs
- `include/` — scripts que as DAGs precisam acessar
- `input/` — CSV manual para desenvolvimento local, fora do Airflow
- `plugins/` — plugins do Airflow
- `tests/` — testes
- `Dockerfile`, `requirements.txt`, `packages.txt` — imagem e dependências

## Ambiente local

```bash
astro dev start
astro dev parse
astro dev stop
```
