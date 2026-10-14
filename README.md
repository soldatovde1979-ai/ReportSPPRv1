# ReportSPPR — еженедельный отчёт о качестве 1С-поддержки

**Запуск в Colab:** [![Открыть в Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/soldatovde1979-ai/ReportSPPRv1/blob/main/RepSSPR.ipynb) — ноутбук `RepSSPR.ipynb` (версия — в его шапке)

Единый вход: эта страница (`github.com/soldatovde1979-ai/ReportSPPRv1`). Имя ноутбука постоянное, кнопка всегда ведёт на текущую версию. Продуктив = ветка `main` (`docs/my-FT.md`, Р-10).

Ноутбук сам понимает, где запущен (my-FT Т-99):

| | Colab | Локально на ПК |
|---|---|---|
| Как открыть | кнопка выше | `run_local.bat` в папке проекта: сам делает `git pull` (последняя версия из `main`) и открывает Jupyter |
| ИИ по умолчанию | DeepSeek | OpenCoder (локальный прокси `127.0.0.1:8787` должен быть запущен) |
| Ключи | секреты Colab: `DEEPSEEK_API_KEY`, `GEMINI_API_KEY` | не нужны для OpenCoder; для DeepSeek/Google — переменная окружения или файл `.env` в папке проекта |
| Выгрузка | окно загрузки | самый свежий файл в `source/` |
| Модуль и шаблон | скачиваются с GitHub (`main`) | из папки проекта (`git pull` — и они свежие) |
| Отчёт, история | скачивается браузером; история — на Диске | `result/`, история и кэш ИИ — `result/history/` |
| Лог (`IS_DEBUG = 1`) | `result/logs/Logs.csv`, `Token.csv` на Диске (без Диска — скачивается) | `result/logs/Logs.csv`, `Token.csv` |

Как запускать:
1. Открыть ноутбук (таблица выше). «Выполнить всё»; в Colab в окне загрузки — выгрузка `sppr_dump_*.json`.
2. После ячейки 1 — строки `🖥️ Среда…`, `🤖 Провайдер…` и `🧩 Модуль report_v6.py …` с источником: (GitHub), (папка проекта) или (запасная копия) — GitHub недоступен, взята копия с Диска.

Первый локальный запуск (Windows): Python 3.10+, затем в папке проекта `py -m pip install -r requirements.txt`.

Подробно: `HANDOFF.md`, разд. 5, п. 4; что за система — `docs/spec.md`; правила для ИИ — `CLAUDE.md`.
