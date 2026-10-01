# ----------------------------------------------------------------------
# build_mockup_v2.py — сборка макета отчёта v2 (examples/mockup_report_v2.html)
# ЧТО: тонкая обёртка над общим модулем src/report_v5.py: выгрузка 1С + разметка ИИ из mockup_v2_ai.json → HTML
#      в оболочке template_v5.html. Цифры, вёрстка и проверка разметки — в модуле.
# ПОЧЕМУ: Р-2 — цифры макета воспроизводимы; Р-6, В-18 = а — макет и боевой отчёт (RepSSPR_v5) собирает
#         один модуль, разойтись они не могут. До 2.5 расчёт и вёрстка жили в этом файле (1500 строк).
# Запуск (Linux / Bash):  python3 examples/build_mockup_v2.py
# ----------------------------------------------------------------------
VERSION = "2.5"
# выгрузка; демо-копия с табличными частями — examples/sppr_dump_20260929_180748_842rec_demo_tab.json
DUMP_FILE = "examples/sppr_dump_20260929_180748_842rec_demo_tab.json"
AI_FILE = "examples/mockup_v2_ai.json"
OUT_FILE = "examples/mockup_report_v2.html"
MODULE_FILE = "src/report_v5.py"     # модуль расчёта и вёрстки — мажор MODULE_MAJOR
MODULE_MAJOR = 5
TEMPLATE_FILE = "template_v5.html"   # оболочка отчёта — мажор проверяет модуль
REPORT_WEEK = None                   # номер ISO-недели; None — с понедельника недели максимальной даты решения

import json, os, sys, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

spec = importlib.util.spec_from_file_location("report_v5", MODULE_FILE)
rv5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv5)
if int(rv5.VERSION.split(".")[0]) != MODULE_MAJOR:
    sys.exit(f"{MODULE_FILE} версии {rv5.VERSION}, обёртка ждёт мажор {MODULE_MAJOR}")

raw = json.load(open(DUMP_FILE, encoding="utf-8"))
AI = json.load(open(AI_FILE, encoding="utf-8"))
R = rv5.load(raw, DUMP_FILE, REPORT_WEEK, history=None, demo="_demo_tab" in DUMP_FILE)
rv5.attach_ai(R, AI)

# проверка разметки кодом — та же, что в ноутбуке: неизвестный ключ метрики или номер не из выгрузки — сборка останавливается
errs = [f"slides.{k}: {rv5.errors_text(e)}" for k, s in AI["slides"].items() for e in [rv5.validate(R, "slide", s, k)] if e]
errs += [f"{p}: {rv5.errors_text(e)}" for p in ("open_crit", "planshet", "signals") for e in [rv5.validate(R, p, AI[p])] if e]
if errs:
    sys.exit("Разметка ИИ не прошла проверку:\n" + "\n".join(errs))
print("Разметка ИИ проверена: ключи метрик и номера обращений сходятся с выгрузкой")

html = rv5.render(R, open(TEMPLATE_FILE, encoding="utf-8").read(), strict=True,
                  title=f"Макет v2 — Качество 1С-поддержки · Неделя {R.WEEK}",
                  banner=f"Макет v{VERSION} на выгрузке {R.NOW:%d.%m.%Y}: цифры и вёрстку делает модуль {MODULE_FILE} (тот же, что в ноутбуке v5), "
                         f"разметку ИИ для макета сделал Claude по правилам промпта ноутбука. Это не боевой отчёт.")
open(OUT_FILE, "w", encoding="utf-8").write(html)
print(f"Записан {OUT_FILE}: {len(html)//1024} КБ, слайдов {len(rv5.ORDER)}")
