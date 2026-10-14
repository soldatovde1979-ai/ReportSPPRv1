# ----------------------------------------------------------------------
# build_mockup_v2.py — сборка макета отчёта v2 (examples/mockup_report_v2.html)
# ЧТО: тонкая обёртка над общим модулем src/report_v<МАЖОР>.py: выгрузка 1С + разметка ИИ из mockup_v2_ai.json → HTML
#      в оболочке template_v<МАЖОР>.html. Цифры, вёрстка и проверка разметки — в модуле.
# ПОЧЕМУ: Р-2 — цифры макета воспроизводимы; Р-6, В-18 = а — макет и боевой отчёт (RepSSPR.ipynb) собирает
#         один модуль, разойтись они не могут. До 2.5 расчёт и вёрстка жили в этом файле (1500 строк).
# Запуск (Linux / Bash):  python3 examples/build_mockup_v2.py
# ----------------------------------------------------------------------
VERSION = "2.9"      # 2.9 — цели и поручения из plan.csv; 2.8 — модуль — старший src/report_v*.py, шаблон — того же мажора (смена мажора без правки файла); 2.7 — неделя макета зафиксирована (REPORT_WEEK = 39); 2.6 — тонкая обёртка над модулем 5.x
# выгрузка; демо-копия с табличными частями — examples/sppr_dump_20260929_180748_842rec_demo_tab.json
DUMP_FILE = "examples/sppr_dump_20260929_180748_842rec_demo_tab.json"
AI_FILE = "examples/mockup_v2_ai.json"
OUT_FILE = "examples/mockup_report_v2.html"
# ЧТО ИЗМЕНЕНО: неделя макета зафиксирована (39), а не «по умолчанию» модуля
# ПОЧЕМУ: модуль 5.6 сменил неделю по умолчанию — прошл. завершённая (W38), а макет и разметка mockup_v2_ai.json
#         собраны под W39; без фиксации макет «уезжает» от разметки и не проходит проверку ключей
REPORT_WEEK = 39                     # номер ISO-недели; 39 — неделя макета и разметки mockup_v2_ai.json

import glob, json, os, re, sys, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

# ----------------------------------------------------------------------
# ЧТО ИЗМЕНЕНО (2.8): явной ссылки на мажор нет — модуль старшего мажора по маске src/report_v*.py (численно),
#               шаблон — template_v<тот же мажор>.html; выбор пишется в вывод
# ПОЧЕМУ: my-FT Р-12 — смена мажора не требует правки этого файла; правило версий (§9): тихий выбор недопустим
# ----------------------------------------------------------------------
_found = sorted((int(m.group(1)), p) for p in glob.glob("src/report_v*.py")
                for m in [re.fullmatch(r"report_v(\d+)\.py", os.path.basename(p))] if m)
if not _found:
    sys.exit("нет src/report_v<МАЖОР>.py")
MODULE_MAJOR, MODULE_FILE = _found[-1]
TEMPLATE_FILE = f"template_v{MODULE_MAJOR}.html"   # оболочка отчёта — мажор проверяет модуль
print(f"Взят {MODULE_FILE} и {TEMPLATE_FILE} (старший мажор, явная ссылка не задана)")

spec = importlib.util.spec_from_file_location(f"report_v{MODULE_MAJOR}", MODULE_FILE)
rv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv)
if int(rv.VERSION.split(".")[0]) != MODULE_MAJOR:
    sys.exit(f"{MODULE_FILE} версии {rv.VERSION}: мажор в имени и в VERSION расходятся")

raw = json.load(open(DUMP_FILE, encoding="utf-8"))
AI = json.load(open(AI_FILE, encoding="utf-8"))
R = rv.load(raw, DUMP_FILE, REPORT_WEEK, history=None, demo="_demo_tab" in DUMP_FILE)
rv.attach_ai(R, AI)
# ЧТО ИЗМЕНЕНО (2.9): цели и поручения — из plan.csv в корне проекта, как в ноутбуке (my-FT Р-14); нет файла — без целей
plan = rv.attach_plan(R, rv.read_plan(rv.PLAN_FILE))
print(f"План {rv.PLAN_FILE}: целей {len(plan['goals'])}, поручений {len(plan['tasks'])}" + (f", ошибок {len(plan['errors'])}: {plan['errors']}" if plan["errors"] else ""))

# проверка разметки кодом — та же, что в ноутбуке: неизвестный ключ метрики или номер не из выгрузки — сборка останавливается
errs = [f"slides.{k}: {rv.errors_text(e)}" for k, s in AI["slides"].items() for e in [rv.validate(R, "slide", s, k)] if e]
errs += [f"{p}: {rv.errors_text(e)}" for p in ("open_crit", "planshet", "signals") for e in [rv.validate(R, p, AI[p])] if e]
if errs:
    sys.exit("Разметка ИИ не прошла проверку:\n" + "\n".join(errs))
print("Разметка ИИ проверена: ключи метрик и номера обращений сходятся с выгрузкой")

html = rv.render(R, open(TEMPLATE_FILE, encoding="utf-8").read(), strict=True,
                  title=f"Макет v2 — Качество 1С-поддержки · Неделя {R.WEEK}",
                  banner=f"Макет v{VERSION} на выгрузке {R.NOW:%d.%m.%Y}: цифры и вёрстку делает модуль {MODULE_FILE} (тот же, что в ноутбуке RepSSPR.ipynb), "
                         f"разметку ИИ для макета сделал Claude по правилам промпта ноутбука. Это не боевой отчёт.")
open(OUT_FILE, "w", encoding="utf-8").write(html)
print(f"Записан {OUT_FILE}: {len(html)//1024} КБ, слайдов {len(rv.ORDER)}")
