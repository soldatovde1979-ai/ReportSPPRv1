# ----------------------------------------------------------------------
# report_v5.py — расчёт и вёрстка еженедельного отчёта ReportSPPR v5
# ЧТО: общий модуль: из выгрузки 1С, разметки ИИ и истории недель считает все цифры
#      и собирает HTML отчёта в формате макета v2 (11 слайдов). Оболочка страницы
#      (CSS, навигация, скрипт) — шаблон template_v5.html.
# ПОЧЕМУ: my-FT Р-6, В-18 = а — один модуль вызывают и ноутбук RepSSPR_v5.x, и сборка
#         макета examples/build_mockup_v2.py: макет и боевой отчёт не могут разойтись.
#         Код перенесён из build_mockup_v2.py 2.4; отличия помечены «ЧТО ИЗМЕНЕНО».
# Как вызывать:
#   R = load(выгрузка, имя_файла, report_week, history)   # период, выборки, без ИИ
#   attach_ai(R, разметка)                                  # разметка ИИ → все метрики R.M
#   R.AI["slides"] = разборы                                # разборы слайдов (s1…s11)
#   html = render(R, текст_шаблона, title=...)
# ----------------------------------------------------------------------
VERSION = "5.0"
TEMPLATE_MAJOR = 5              # мажор template_v5.html, с которым работает модуль (контроль — check_template)

OLD_BOARD_PREFIX = "Выполнено - "   # статусы старой доски — игнорируются при загрузке (Т-21)
L1_ANALYST = "Попова Анна"          # первая линия (Т-10)
L1_WORD = "confluence"
NSI_SECTION = "Нормализация"        # НСИ (Т-11)
SLA_DIVIDER = 3                     # 24 ч / 3 = 8 ч в рабочем дне (Т-68)
# праздники РФ 2026 (нерабочие дни) — сверить с производственным календарём
HOLIDAYS = {f"2026-{d}" for d in ("01-01", "01-02", "01-03", "01-04", "01-05", "01-06", "01-07", "01-08",
                                  "02-23", "03-09", "05-01", "05-11", "06-12", "11-04", "12-31")}
SVC_RX = r"списания выполнены|планерк|совещани"   # признаки служебной карточки учёта времени
FAST_H, LONG_H, OLD_DAYS = 8, 40, 30

import json, re, html, statistics, os
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from html.parser import HTMLParser

SOLVED = ["Отработано, требует подтверждения", "Закрыто"]
REJECTED = "Отклонено"
CATS = ["Инцидент", "Правка данных", "НСИ", "Консультация", "Права доступа", "Дубль"]
CAT_COLOR = {"Инцидент": "#D93025", "Правка данных": "#D08700", "НСИ": "#7E57C2",
             "Консультация": "#1E8E3E", "Права доступа": "#1A56DB", "Дубль": "#0097A7",
             "Служебное": "#9AA5B1"}
ST2TYPE = {"I": "Инцидент", "D": "Изменение данных в системе", "K": "Консультация", "P": "Права доступа",
           "DB": "Дубль", "SVC": "Служебное"}
TYPE_SHORT = {"Инцидент": "Инцидент", "Изменение данных в системе": "Правка данных", "Консультация": "Консультация",
              "Права доступа": "Права", "Дубль": "Дубль", "Служебное": "Служебное"}
HOLDERS = ["Пользователь", "Поддержка", "Разработка"]
# ----------------------------------------------------------------------
# ЧТО ИЗМЕНЕНО: добавлены статусы требования, которые с 29.09 может отдать выгрузка
# ПОЧЕМУ: иначе «Возврат на доработку» и подобные попадали к разработке (data.md, разд. 10, п. 4)
# ----------------------------------------------------------------------
HOLDER_OF = {"Уточнение": "Пользователь", "Ожидает анализа": "Поддержка", "Анализ": "Поддержка",
             "Новое": "Поддержка", "Передано в работу": "Поддержка", "Уточнение предоставлено": "Поддержка",
             "Возврат на доработку": "Поддержка", "Перенесено": "Поддержка"}
FINAL_ST = {"Отработано, требует подтверждения", "Закрыто", "Отклонено"}
TAB_COLS = {"tab_trud": 2, "tab_status": 4}   # число колонок строки табличной части (data.md, разд. 10)
WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MON = ["", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
# ----------------------------------------------------------------------
# ЧТО ИЗМЕНЕНО: справочники, которые в макете жили внутри функций слайдов или в разметке ИИ, — вынесены сюда
# ПОЧЕМУ: в v5 по ним же строятся промпты ноутбука и проверка ответов модели — одно место на все
# ----------------------------------------------------------------------
MON_FULL = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
# действия по старым открытым (поле ag разметки open_old); тексты — как в макете
OPEN_ACTIONS = {"dup": "Объединить дубли — одна доработка", "close": "Закрыть по регламенту: ответа пользователя нет",
                "check": "Проверить: вероятно, уже решено", "empty": "Закрыть: пустая карточка",
                "esc": "Эскалировать: анализ без движения", "plan": "Решить с разработкой: делать или отклонить",
                "rel": "Довести до релиза"}
OPEN_ORDER = ["close", "empty", "check", "dup", "esc", "plan", "rel"]
# причина ручной правки (поле why) → что сделать и кому
WHY_ACT = {"нет прав у пользователя": ("Выдать право или ускорить ЗНИ", "Владелец процесса"),
           "дефект системы": ("Завести инцидент на причину", "Разработка"),
           "ошибка пользователя": ("Проверка при вводе, обучение конкретных людей", "Руководитель подразделения"),
           "штатная правка": ("Самообслуживание по шаблону", "Владелец НСИ"),
           "разрыв процесса": ("Встроить шаг в бизнес-процесс", "Владелец процесса"),
           "пробел НСИ": ("Назначить владельца справочника, обязательные поля", "Владелец НСИ"),
           "нет функционала": ("ЗНИ на доработку", "Разработка"),
           "ошибка ввода НСИ": ("Проверка при вводе", "Владелец НСИ")}
# ключ метрики why_<код> → причина (why_rights, why_user — имена из макета)
WHY_KEYS = {"rights": "нет прав у пользователя", "defect": "дефект системы", "user": "ошибка пользователя",
            "routine": "штатная правка", "process": "разрыв процесса", "nsigap": "пробел НСИ",
            "nofunc": "нет функционала", "nsiinput": "ошибка ввода НСИ"}
GRADE = {"О": "Отлично", "Х": "Хорошо", "П": "Плохо", "—": "—"}
# причины обращений по планшетам (разметка planshet); «Массовый сбой ДД.ММ» — с датой сбоя
PL_KINDS = ["Вход и учётная запись", "Функции мобильного инженера", "Зависания и запуск", "Массовый сбой",
            "Связь в ремзонах", "Доработки и прочее"]
PL_COLOR = {"Вход и учётная запись": "#1A56DB", "Функции мобильного инженера": "#7E57C2", "Зависания и запуск": "#D08700",
            "Массовый сбой": "#D93025", "Связь в ремзонах": "#0097A7", "Доработки и прочее": "#1E8E3E"}
PL_PLACES = (("Терминал C", r"терминал[а-я]*\s*[CС]\b"), ("Терминал D", r"терминал[а-я]*\s*[DД]\b|терм\.\s*Д"), ("ДГМ Ш-2", r"Ш-?2"),
             ("ДГМ Ш-3", r"Ш-?3"), ("Линейка СТК", r"линейк[а-я]*\s*СТК|СТК"))
CONSEQ = {("Правка данных", "Инцидент"): "Дефект правят руками, разработка о нём не знает",
          ("Консультация", "Инцидент"): "Сбой закрыт как «объяснили» — причина остаётся",
          ("Консультация", "Правка данных"): "Правка данных спрятана в консультации — поток правок занижен",
          ("Консультация", "Дубль"): "Повторная регистрация того же обращения",
          ("Правка данных", "Консультация"): "Правкой названа консультация — поток правок завышен",
          ("Права", "Консультация"): "Права уже были — нужна была инструкция"}
TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))
# порядок слайдов и меню; номера слайдов — метрики n_s1…n_s11 для текстов разборов
NAV = [("Состояние недели", [("s1", "Неделя {WEEK}"), ("s11", "Сроки и долгострой"), ("s2", "Очередь на {NOW}")]),
       ("Где болит", [("s3", "Инциденты"), ("s4", "Ручные правки и НСИ"), ("s5", "Повторы"), ("s7", "Планшеты")]),
       ("Качество, люди, цена", [("s6", "Качество и классификация"), ("s9", "Аналитики"), ("s8", "Цена в часах")]),
       ("Приложение", [("s10", "Паспорт данных")])]
ORDER = ["s1", "s11", "s2", "s3", "s4", "s5", "s7", "s6", "s9", "s8", "s10"]
AI_SLIDES = ["s1", "s11", "s2", "s3", "s4", "s5", "s7", "s6", "s9", "s8"]   # слайды с разбором ИИ (паспорт — без)
# поля разборов слайдов: обязательные списки и поля их строк (data.md, разд. 11)
SLIDE_ITEM = ("fact", "conc", "act", "who", "eff", "ids")
SLIDE_EXTRA = {"s1": {"decisions": ("problem", "fact", "ids", "act", "who", "eff"), "prev": ("what", "was", "now", "status"),
                      "root_all": ("cause", "ids", "act", "who")},
               "s3": {"root": ("cause", "ids", "fix", "kind"), "notsolved": ("id", "done", "why", "risk"), "fix_first": ("name", "ids", "act")},
               "s4": {"nsi_nonedit": ("id", "cls", "note")},
               "s6": {"best": ("id", "why", "kb")}}


class Report:
    """Состояние одного отчёта: строки выгрузки, период, выборки, разметка ИИ, метрики."""


def P(s):
    return datetime.fromisoformat(s) if s else None


# ----------------------------------------------------------------------
# ЧТО ИЗМЕНЕНО: срок решения — календарные часы только рабочих дней / 3: 8 ч в рабочем дне, выходные и праздники не считаются
# ПОЧЕМУ: Т-67, Т-68: «/3» по всем дням добавлял выходные — на W39 шесть из 23 «долгостроев» были ими
# ----------------------------------------------------------------------
def work_h(a, b):
    t, d = 0.0, datetime(a.year, a.month, a.day)
    while d < b:
        nd = d + timedelta(days=1)
        if d.weekday() < 5 and f"{d:%Y-%m-%d}" not in HOLIDAYS:
            t += max(0.0, (min(b, nd) - max(a, d)).total_seconds())
        d = nd
    return t / 3600 / SLA_DIVIDER


def dump_moment(fname):
    m = re.search(r"(\d{8})_(\d{6})", fname or "")
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S") if m else None
    except ValueError:
        return None


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def pct(a, b):
    return round(100 * a / b) if b else 0


def by(lst, key):
    d = defaultdict(list)
    for r in lst:
        d[key(r)].append(r)
    return d


def hsum(lst):
    return round(sum(r["trud"] for r in lst), 1)


E = lambda s: html.escape(str(s), quote=True)
DD = lambda d: f"{d:%d.%m}" if d else "—"
c1 = lambda x: "—" if x is None else str(x).replace(".", ",")      # число с запятой; нет значения — «—»


def short(name):
    p = name.split()
    return f"{p[0]} {p[1][0]}. {p[2][0]}." if len(p) >= 3 and re.match("[А-ЯЁ]", p[0]) else name


def slug(text):
    """Латинский ключ из русского текста: «Заказ-наряд: даты» → zakaz_naryad_daty."""
    t = "".join(TRANSLIT.get(c, c) for c in str(text).lower())
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def pl_kind_base(kind):
    """«Массовый сбой 02.09» → «Массовый сбой»: цвет и порядок причины — по основе."""
    return "Массовый сбой" if str(kind).startswith("Массовый сбой") else kind


def check_template(text):
    """Контроль мажора шаблона (CLAUDE.md, правило версий): версия — строка TEMPLATE_VERSION в начале файла."""
    m = re.search(r'TEMPLATE_VERSION\s*=\s*"(\d+)\.(\d+)"', text[:2000])
    if not m:
        raise ValueError("В шаблоне нет строки TEMPLATE_VERSION = \"5.x\" — это не template_v5.html")
    if int(m.group(1)) != TEMPLATE_MAJOR:
        raise ValueError(f"Шаблон версии {m.group(1)}.{m.group(2)}, модуль report_v5 {VERSION} работает с мажором {TEMPLATE_MAJOR}: "
                         f"возьмите template_v{TEMPLATE_MAJOR}.html")
    return f"{m.group(1)}.{m.group(2)}"


def status_holder(st):
    if st in FINAL_ST: return None
    return HOLDER_OF.get(st, "Разработка")


def holder_hours(r, NOW):
    """Календарные часы у каждого держателя по истории статусов (tab_status)."""
    ev = sorted(r["tab_status"], key=lambda e: e[0])
    out = Counter()
    for k, e in enumerate(ev):
        h = status_holder(e[3])
        if not h: continue
        end = ev[k + 1][0] if k + 1 < len(ev) else (NOW if r["is_open"] else e[0])
        out[h] += max(0, (end - e[0]).total_seconds() / 3600)
    return out


# ================================================================ ЗАГРУЗКА И ПЕРИОД
def load(raw, dump_name="", report_week=None, history=None, demo=False, say=print):
    """Выгрузка (список объектов JSON) → Report: строки, отчётный период, выборки. Разметки ИИ ещё нет."""
    R = Report()
    R.say = say
    R.raw, R.dump_name, R.demo = raw, os.path.basename(dump_name or ""), demo
    R.NOW = dump_moment(R.dump_name) or max(P(r["reg"]) for r in raw if r.get("reg"))
    rows, dropped, noreg = [], [], []
    TAB_BAD = Counter()
    for r in raw:
        r = {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: нет поля или null — пустая строка; обращение без даты регистрации отбрасывается со счётчиком
        # ПОЧЕМУ: боевой модуль не должен падать на неполной строке выгрузки посреди прогона с платными вызовами ИИ
        # ----------------------------------------------------------------------
        for k in ("st", "id", "reg", "res", "cls", "sec", "desc", "sol", "anl", "cli", "type"):
            if r.get(k) is None: r[k] = ""
        if r["st"].startswith(OLD_BOARD_PREFIX):
            dropped.append(r["id"]); continue
        r["reg_dt"], r["res_dt"], r["cls_dt"] = P(r["reg"]), P(r["res"]), P(r["cls"])
        if r["reg_dt"] is None:
            noreg.append(r["id"]); continue
        r["done_dt"] = r["res_dt"] or r["cls_dt"]
        r["h"] = round(work_h(r["reg_dt"], r["done_dt"]), 1) if r["done_dt"] else None
        r["trud"] = float(r.get("AmountTrud") or 0)
        # табличные части: нет поля / null / [] — нет данных; кривые строки отбрасываются
        for tname, ncol in TAB_COLS.items():
            good = []
            for row in (r.get(tname) or []):
                try:
                    if len(row) != ncol: raise ValueError
                    if tname == "tab_trud":
                        good.append((str(row[0]).strip(), float(row[1])))
                    else:
                        dt = P(row[0])
                        if dt is None: raise ValueError
                        good.append((dt, str(row[1]).strip(), row[2], str(row[3]).strip()))
                except (ValueError, TypeError):
                    TAB_BAD[tname] += 1
            r[tname] = good
        r["line"] = "L1" if r["anl"].startswith(L1_ANALYST) or L1_WORD in r["sol"].lower() else "L2"
        r["cat"] = "НСИ" if r["sec"] == NSI_SECTION else TYPE_SHORT.get(r["type"], r["type"]).replace("Права", "Права доступа")
        r["is_sol"] = r["st"] in SOLVED
        r["is_rej"] = r["st"] == REJECTED
        r["is_open"] = not r["is_sol"] and not r["is_rej"]
        r["age"] = (R.NOW - r["reg_dt"]).days
        r["holder"] = HOLDER_OF.get(r["st"], "Разработка") if r["is_open"] else ""
        # служебные карточки учёта времени: явные признаки в тексте (разметка ИИ SVC — в attach_ai)
        if re.search(SVC_RX, r["desc"] + " " + r["sol"], re.I):
            r["cat"] = "Служебное"
        r["ai"] = {}
        rows.append(r)
    say(f"Загружено {len(raw)} строк; отброшено статусов старой доски: {len(dropped)} {dropped}"
        + (f"; без даты регистрации: {len(noreg)} {noreg}" if noreg else ""))
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО: склейка двух написаний одного человека по коду сотрудника (cli_id, anl_id), если поля есть
    # ПОЧЕМУ: Т-69 — латинское и кириллическое ФИО одного инициатора делили топы; нет полей — всё как раньше
    # ----------------------------------------------------------------------
    R.merged = {}
    for fld, idf in (("cli", "cli_id"), ("anl", "anl_id")):
        names = defaultdict(Counter)
        for r in rows:
            if r.get(idf): names[str(r[idf])][r[fld]] += 1
        canon = {}
        for code, cnt in names.items():
            if len(cnt) > 1:
                cyr = [n for n, _ in cnt.most_common() if re.match("[А-ЯЁ]", n)]
                canon[code] = cyr[0] if cyr else cnt.most_common(1)[0][0]
        for r in rows:
            if r.get(idf) and str(r[idf]) in canon:
                r[fld] = canon[str(r[idf])]
        R.merged[fld] = len(canon) if names else None
    R.rows, R.dropped, R.noreg, R.TAB_BAD = rows, dropped, noreg, TAB_BAD

    # ---------------------------------------------------------------- отчётный период (Т-12)
    solved_dt = [r["done_dt"] for r in rows if r["is_sol"] and r["done_dt"]]
    if not solved_dt:
        raise ValueError("В выгрузке нет решённых обращений с датой решения — отчётный период не определить")
    max_res = max(solved_dt)
    if report_week:
        WS = datetime.fromisocalendar(max_res.year, int(report_week), 1); WE = WS + timedelta(days=7)
        rule = f"неделя {report_week} задана параметром"
    else:
        WS = datetime(max_res.year, max_res.month, max_res.day) - timedelta(days=max_res.weekday())
        WE = datetime(max_res.year, max_res.month, max_res.day) + timedelta(days=1)
        rule = f"по максимальной дате решения {max_res:%d.%m %H:%M}"
    R.WS, R.WE, R.rule = WS, WE, rule
    R.WEEK = WS.isocalendar()[1]
    R.YEAR = WS.isocalendar()[0]
    R.DAYS = [WS + timedelta(days=i) for i in range((WE - WS).days)]
    R.PER = f"{WS:%d.%m}–{(WE - timedelta(days=1)):%d.%m.%Y}"
    R.PER_S = f"{WS:%d.%m}–{(WE - timedelta(days=1)):%d.%m}"
    R.first_res = min(solved_dt)
    say(f"Период: W{R.WEEK} {R.PER} ({rule}); срез {R.NOW:%d.%m %H:%M}")

    in_per = R.in_per = lambda dt, a=WS, b=WE: dt is not None and a <= dt < b
    R.sol = [r for r in rows if r["is_sol"] and in_per(r["done_dt"])]
    R.inc = [r for r in rows if in_per(r["reg_dt"])]
    R.rej = [r for r in rows if r["is_rej"] and in_per(r["cls_dt"])]
    _split_open(R)
    # 4 недели: три полные до отчётной + отчётный период
    out = []
    for k in range(3, -1, -1):
        a = WS - timedelta(days=7 * k)
        b = a + timedelta(days=7) if k else WE
        out.append((a, b))
    R.WEEKS4 = out
    R.W4S = out[0][0]
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО: проверка, что выгрузка покрывает 4 недели (первое решение не позже начала окна)
    # ПОЧЕМУ: блоки «4 недели» (динамика, цена, аналитики) считаются из самой выгрузки; короткая выгрузка — неполные цифры
    # ----------------------------------------------------------------------
    R.cover_ok = R.first_res < R.W4S + timedelta(days=1)
    if not R.cover_ok:
        say(f"⚠️ Выгрузка начинается с решений {R.first_res:%d.%m}, а окно 4 недель — с {R.W4S:%d.%m}: блоки «4 недели» неполные")
    # планшеты — 4 недели по дате регистрации + открытые
    R.pl = [r for r in rows if re.search("планшет", r["desc"] + r["sol"], re.I) and (r["reg_dt"] >= R.W4S or r["is_open"])]
    # ---------------------------------------------------------------- табличные части: метрики
    R.TAB_ON = {t: sum(1 for r in rows if r[t]) for t in TAB_COLS}
    R.TRUD_MISMATCH = [r["id"] for r in rows if r["tab_trud"] and abs(sum(h for _, h in r["tab_trud"]) - r["trud"]) > 0.05]
    say(f"Табличные части: {R.TAB_ON}; отброшено строк {dict(TAB_BAD)}; расхождений tab_trud с AmountTrud {len(R.TRUD_MISMATCH)}"
        + (" (ДЕМО)" if demo else ""))
    R.BYID = {r["id"]: r for r in rows}
    R.RAWID = {str(r.get("id", "")).strip(): r for r in raw}
    R.history = normalize_history(history or [])
    R.AI = {"tickets": [], "open_old": [], "open_crit": [], "planshet": {}, "signals": [], "slides": {}}
    R.AIT, R.AIO = {}, {}
    R.M = {}
    say(f"Пришло {len(R.inc)}, решено {len(R.sol)}, отклонено {len(R.rej)}, открыто {len(R.opn)}")
    return R


def _split_open(R):
    R.opn_svc = [r for r in R.rows if r["is_open"] and r["cat"] == "Служебное"]
    R.opn = [r for r in R.rows if r["is_open"] and r["cat"] != "Служебное"]   # служебные карточки — не очередь
    R.old = [r for r in R.opn if r["age"] > OLD_DAYS]


# ================================================================ РАЗМЕТКА ИИ И МЕТРИКИ
def attach_ai(R, ai):
    """Разметка ИИ (схема data.md, разд. 11) → поля строк и все метрики R.M. Разборы слайдов можно добавить позже."""
    ai = ai or {}
    R.AI = {"tickets": [a for a in (ai.get("tickets") or []) if isinstance(a, dict) and a.get("id")],
            "open_old": [a for a in (ai.get("open_old") or []) if isinstance(a, dict) and a.get("id")],
            "open_crit": [a for a in (ai.get("open_crit") or []) if isinstance(a, dict) and a.get("id")],
            "planshet": dict(ai.get("planshet") or {}),
            "signals": [a for a in (ai.get("signals") or []) if isinstance(a, dict) and a.get("id")],
            "slides": dict(ai.get("slides") or {})}
    R.AIT = {a["id"]: a for a in R.AI["tickets"]}
    R.AIO = {a["id"]: a for a in R.AI["open_old"]}
    # служебные карточки: разметка ИИ дополняет явные признаки в тексте (load)
    for r in R.rows:
        a = R.AIT.get(r["id"])
        if a and a.get("st") == "SVC":
            r["cat"] = "Служебное"
    _split_open(R)
    for r in R.sol:
        r["ai"] = R.AIT.get(r["id"], {})
        st = r["ai"].get("st")
        r["type_ai"] = ST2TYPE.get(st, r["type"])
        r["cat_ai"] = ("НСИ" if r["sec"] == NSI_SECTION else TYPE_SHORT.get(r["type_ai"], r["type_ai"]).replace("Права", "Права доступа")) if st else r["cat"]
    missing_ai = [r["id"] for r in R.sol if not r["ai"]]
    R.say(f"Разметка ИИ: решённых размечено {len(R.sol) - len(missing_ai)} из {len(R.sol)}; без разметки (Н/Д): {missing_ai}")
    _metrics(R)
    return R


def _metrics(R):
    rows, sol, inc, rej, opn, old, in_per = R.rows, R.sol, R.inc, R.rej, R.opn, R.old, R.in_per
    AIO, M, W4S = R.AIO, {}, R.W4S
    real = R.real = [r for r in sol if r["cat"] != "Служебное"]
    M.update(m_in=len(inc), m_sol=len(sol), m_rej=len(rej), m_open=len(opn), sol_n=len(sol), open_n=len(opn))
    M["dq"] = len(inc) - len(sol) - len(rej)
    wk = R.wk = []
    for a, b in R.WEEKS4:
        i = [r for r in rows if in_per(r["reg_dt"], a, b)]
        s = [r for r in rows if r["is_sol"] and in_per(r["done_dt"], a, b)]
        j = [r for r in rows if r["is_rej"] and in_per(r["cls_dt"], a, b)]
        wk.append(dict(a=a, b=b, i=i, s=s, j=j, dq=len(i) - len(s) - len(j)))
    # ЧТО ИЗМЕНЕНО: dq_w38 → dq_prev. ПОЧЕМУ: имя метрики не должно зависеть от номера недели
    M["dq_prev"] = wk[-2]["dq"]
    L1 = R.L1 = [r for r in real if r["line"] == "L1"]; L2 = R.L2 = [r for r in real if r["line"] == "L2"]
    M.update(med_all=med([r["h"] for r in real]), med_l1=med([r["h"] for r in L1]), med_l2=med([r["h"] for r in L2]),
             long_all=sum(r["h"] > LONG_H for r in real), long_l2=sum(r["h"] > LONG_H for r in L2),
             long_l1=sum(r["h"] > LONG_H for r in L1))
    M["l2_l1_ratio"] = str(round(M["med_l2"] / M["med_l1"], 1)).replace(".", ",") if M["med_l1"] and M["med_l2"] is not None else "—"
    M["trud_sol"] = hsum(sol); M["svc_h"] = hsum([r for r in sol if r["cat"] == "Служебное"])
    M["svc_pct"] = pct(M["svc_h"], M["trud_sol"])
    bycat = R.bycat = by(real, lambda r: r["cat"])
    M["inc_med"] = med([r["h"] for r in bycat["Инцидент"]]); M["pr_med"] = med([r["h"] for r in bycat["Правка данных"]])
    dev = R.dev = [r for r in opn if r["holder"] == "Разработка"]
    M["dev_open"], M["dev_gt30"] = len(dev), sum(r["age"] > OLD_DAYS for r in dev)
    M["open_gt30"] = len(old)
    agc = Counter(AIO[r["id"]].get("ag") for r in old if r["id"] in AIO)
    M["dup_n"] = agc["dup"]; M["close_n"] = agc["close"]; M["esc_n"] = agc["esc"]
    M["empty_n"] = agc["empty"]; M["check_n"] = agc["check"]; M["plan_n"] = agc["plan"]; M["rel_n"] = agc["rel"]
    M["dup_close"] = sum(1 for r in old if r["id"] in AIO and AIO[r["id"]].get("ag") == "dup" and "Дубль" in (AIO[r["id"]].get("a") or ""))
    M["quick_close"] = agc["close"] + agc["empty"] + agc["check"] + M["dup_close"]
    why = lambda k: [r for r in sol if r["cat"] == "Правка данных" and r["ai"].get("why") == k]
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО: why_<код> — по всем причинам правки, а не только «нет прав» и «ошибка пользователя»
    # ПОЧЕМУ: в v5 тексты пишет модель — ей нужны ключи для любой причины (why_rights, why_user — прежние имена)
    # ----------------------------------------------------------------------
    for code, k in WHY_KEYS.items():
        M["why_" + code] = len(why(k)); M[f"why_{code}_h"] = hsum(why(k))
    pr = R.pr = bycat["Правка данных"]
    M["pr_n"], M["pr_h"] = len(pr), hsum(pr)
    M["pr_defect"] = sum(1 for r in pr if r["type_ai"] == "Инцидент" or r["ai"].get("why") == "дефект системы")
    nsi = R.nsi = bycat["НСИ"]
    M["nsi_n"], M["nsi_med"] = len(nsi), med([r["h"] for r in nsi])
    M["nsi_kontr"] = sum(1 for r in nsi if (r["ai"].get("obj") or "").startswith("Контрагент"))
    inc_types = R.inc_types = [r for r in opn if r["type"] == "Инцидент"]
    M["inc_open"] = len(inc_types); M["inc_in"] = sum(r["type"] == "Инцидент" for r in inc)
    M["inc_sol"] = sum(r["type"] == "Инцидент" for r in sol); M["inc_ai"] = sum(r["type_ai"] == "Инцидент" for r in sol)
    M["hidden_ratio"] = str(round(M["inc_ai"] / M["inc_sol"], 1)).replace(".", ",") if M["inc_sol"] else "—"
    M["inc_old"] = sum(r["age"] > OLD_DAYS for r in inc_types)
    M["inc_dev"] = sum(r["age"] > OLD_DAYS and r["holder"] == "Разработка" for r in inc_types)
    mis = R.mis = [r for r in sol if r["ai"].get("st") not in (None, "SVC") and r["type_ai"] != r["type"]]
    sol_ai = R.sol_ai = [r for r in sol if r["ai"].get("st") not in (None, "SVC")]
    M["mis_n"], M["sol_ai"], M["mis_pct"] = len(mis), len(sol_ai), pct(len(mis), len(sol_ai))
    M["mis_to_inc"] = sum(r["type_ai"] == "Инцидент" for r in mis)
    M["bad_n"] = sum(r["ai"].get("gr") == "П" for r in sol_ai)
    R.OPEN_CRIT = {x["id"]: x.get("why", "") for x in R.AI["open_crit"] if x["id"] in R.BYID and R.BYID[x["id"]]["is_open"]}
    pl = R.pl
    M["pl_4w"] = len(pl); M["pl_open"] = sum(r["is_open"] for r in pl); M["pl_rej"] = sum(r["is_rej"] for r in pl)
    PLK = R.AI["planshet"]
    for r in pl:
        r["pl_kind"] = PLK.get(r["id"]) or pl_kind(r)   # причина — разметка ИИ; для неразмеченных — по словам
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО: массовый сбой — любая «Массовый сбой ДД.ММ», а не только 02.09; счётчики по всем причинам
    # ПОЧЕМУ: дата сбоя в макете была зашита в код; в v5 её ставит модель
    # ----------------------------------------------------------------------
    M["pl_mass"] = sum(str(r["pl_kind"]).startswith("Массовый сбой") for r in pl)
    M["pl_login"] = sum(r["pl_kind"] == "Вход и учётная запись" for r in pl)
    M["pl_func"] = sum(r["pl_kind"] == "Функции мобильного инженера" for r in pl)
    M["pl_hang"] = sum(r["pl_kind"] == "Зависания и запуск" for r in pl)
    M["pl_net"] = sum(r["pl_kind"] == "Связь в ремзонах" for r in pl)
    M["pl_other"] = sum(r["pl_kind"] == "Доработки и прочее" for r in pl)
    M["pl_sd"] = sum(bool(re.search("сервис деск|отработано сервис", r["sol"], re.I)) for r in pl)
    M["pl_l1"] = sum(r["line"] == "L1" for r in pl)
    # часы
    M["inc_hpt"] = str(round(hsum(bycat["Инцидент"]) / max(1, len(bycat["Инцидент"])), 1)).replace(".", ",")
    M["pr_hpt"] = str(round(hsum(pr) / max(1, len(pr)), 1)).replace(".", ",")
    ratios = [(r["done_dt"] - r["reg_dt"]).total_seconds() / 3600 / r["trud"] for r in real if r["trud"] > 0]
    M["wait_ratio"] = round(statistics.median(ratios)) if ratios else None
    sol4 = R.sol4 = [r for r in rows if r["is_sol"] and r["done_dt"] and r["done_dt"] >= W4S]
    M["zombie"] = sum(1 for r in old if r["trud"] == 0)
    # топ-7 групп
    grp = R.grp = by([r for r in sol if r["ai"].get("g")], lambda r: r["ai"]["g"])
    top7 = R.top7 = sorted(grp.items(), key=lambda kv: (-len(kv[1]), -hsum(kv[1])))[:7]
    M["top7_n"] = sum(len(v) for _, v in top7)
    M["top7_nsi"] = sum(1 for _, v in top7 if sum(r["cat"] == "НСИ" for r in v) > len(v) / 2)
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО: метрики долгостроя считаются здесь, а не внутри слайда 11
    # ПОЧЕМУ: каталог метрик должен быть полным до вызова модели — разборы ссылаются на любые ключи
    # ----------------------------------------------------------------------
    lng = R.lng = sorted([r for r in real if r["h"] > LONG_H], key=lambda r: -r["h"])
    n = len(lng); tot_h = sum(r["h"] for r in lng); tot_w = sum(r["trud"] for r in lng)
    cons = [r for r in lng if r["cat"] == "Консультация"]
    top2 = Counter(short(r["anl"]) for r in lng).most_common(2)
    M.update(real_n=len(real), long_h_thr=LONG_H, lng_share=pct(n, len(real)), lng_h=round(tot_h), lng_trud=round(tot_w), lng_work_pct=pct(tot_w, tot_h),
             lng_cons=len(cons), lng_cons_trud=round(sum(r["trud"] for r in cons)), lng_cons_h=round(sum(r["h"] for r in cons)),
             lng_two=sum(v for _, v in top2), lng_top_h=round(lng[0]["h"]) if lng else None, lng_top_pct=pct(lng[0]["h"], tot_h) if lng else None,
             lng_med=med([r["h"] for r in lng]))
    num = {k: i + 1 for i, k in enumerate(ORDER)}
    M.update({f"n_{k}": v for k, v in num.items()})   # номера слайдов в текстах разборов ИИ — от порядка слайдов
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО: метрики «по фамилии» (alshin_old, mis_krav, zero_kosh…), устройства (pl_2637) и объекта правки
    #               (zn_dates) — общими семействами a_<фамилия>_<метрика>, pl_dev_<номер>, obj_<объект>
    # ПОЧЕМУ: в макете ключи были написаны под одну неделю; модель v5 на любой неделе должна найти ключ
    #         для любого аналитика, устройства и объекта (data.md, разд. 11.4)
    # ----------------------------------------------------------------------
    names = sorted(({r["anl"] for r in sol} | {r["anl"] for r in old} | {r["anl"] for r in sol4}) - {""})
    base = Counter(slug(n.split()[0]) for n in names)
    R.anl_slug, used = {}, set()
    for nm in names:
        s = slug(nm.split()[0]) or "x"
        if base[s] > 1:
            s = slug(nm.split()[0] + " " + "".join(p[0] for p in nm.split()[1:3])) or s
        while s in used: s += "x"
        used.add(s); R.anl_slug[nm] = s
    for nm, s in R.anl_slug.items():
        so = [r for r in sol if r["anl"] == nm]
        s4 = [r for r in sol4 if r["anl"] == nm]
        ol = [r for r in old if r["anl"] == nm]
        vals = {"sol": len(so), "mis": sum(r["anl"] == nm for r in mis), "med": med([r["h"] for r in so]),
                "bad": sum(r["anl"] == nm and r["ai"].get("gr") == "П" for r in sol_ai),
                "old": len(ol), "old0": sum(r["trud"] == 0 for r in ol),
                "zero4w": pct(sum(r["trud"] == 0 for r in s4), len(s4)) if s4 else None}
        for k, v in vals.items():
            if v is not None: M[f"a_{s}_{k}"] = v
    R.devices = Counter()
    for r in pl:
        for x in sorted(set(re.findall(r"(?:ID|планшет[а-я]*|№)\s*[:№]?\s*(\d{4})", r["desc"], re.I))):
            R.devices[x] += 1
    for x, v in R.devices.items():
        M["pl_dev_" + x] = v
    R.obj_keys = {}
    for r in sol:
        o = (r["ai"].get("obj") or "").strip()
        if o and slug(o):
            k = "obj_" + slug(o)
            M[k] = M.get(k, 0) + 1
            R.obj_keys.setdefault(k, o)
    R.M = M
    R.say(f"Метрик: {len(M)}")
    return M


def pl_kind(r):
    """Причина обращения по планшету по словам — только для обращений без разметки ИИ."""
    t = (r["desc"] + " " + r["sol"]).lower()
    # ЧТО ИЗМЕНЕНО: убрано правило «02.09 + слова — массовый сбой». ПОЧЕМУ: дата сбоя одной недели была зашита в код
    if re.search("сигнал|теряет сотов|нет связи|слаб", t): return "Связь в ремзонах"
    if re.search("войти|вход|учетн|учётн|уз |у\\.з|логин|парол|заход", t): return "Вход и учётная запись"
    if re.search("дефект|отбор|метк|функци|обновлен|файл|фото", t): return "Функции мобильного инженера"
    if re.search("завис|тормоз|загруз|крутит|не запуск|пустой|не работает", t): return "Зависания и запуск"
    return "Доработки и прочее"


# ================================================================ КАТАЛОГ МЕТРИК ДЛЯ ИИ
# ----------------------------------------------------------------------
# ЧТО ИЗМЕНЕНО: у каждой метрики — описание; каталог «ключ = значение — что это» уходит в промпт разборов
# ПОЧЕМУ: цифры в текстах ИИ — только ключами {метрика}, их подставляет код (HANDOFF, разд. 0); модель
#         должна знать, что значит каждый ключ, иначе возьмёт не тот
# ----------------------------------------------------------------------
METRIC_INFO = {
    "m_in": "пришло за период (дата регистрации в периоде)", "m_sol": "решено за период (статус «Закрыто» или «Отработано…», дата решения в периоде)",
    "m_rej": "отклонено за период", "m_open": "открыто на момент выгрузки, без служебных карточек",
    "sol_n": "решено за период (то же, что m_sol)", "open_n": "открыто на момент выгрузки (то же, что m_open)",
    "dq": "изменение очереди за период: пришло − решено − отклонено (плюс — очередь растёт)",
    "dq_prev": "изменение очереди за предыдущую неделю",
    "med_all": "медиана срока решения, раб. ч (8 ч в рабочем дне, выходные не считаются), решённые за период без служебных",
    "med_l1": "медиана срока решения первой линии, раб. ч", "med_l2": "медиана срока решения второй линии, раб. ч",
    "l2_l1_ratio": "во сколько раз медиана второй линии больше медианы первой",
    "long_all": f"долгострой: решены за период, но шли дольше {LONG_H} раб. ч (без служебных)",
    "long_l1": "долгострой первой линии", "long_l2": "долгострой второй линии",
    "trud_sol": "трудозатраты на решённые за период, ч (AmountTrud), со служебными карточками",
    "svc_h": "часов на служебные карточки среди решённых за период", "svc_pct": "доля служебных карточек в часах решённых за период, %",
    "inc_med": "медиана срока решения инцидентов (тип при регистрации, без НСИ), раб. ч",
    "pr_med": "медиана срока решения правок данных без НСИ, раб. ч",
    "dev_open": "открыто у разработки (от планирования до проверки релиза)", "dev_gt30": "из них старше 30 дней",
    "open_gt30": f"открытых старше {OLD_DAYS} дней",
    "dup_n": "старых открытых с действием ИИ «объединить дубли»", "close_n": "старых открытых с действием «закрыть по регламенту: ответа пользователя нет»",
    "esc_n": "старых открытых с действием «эскалировать: анализ без движения»", "empty_n": "старых открытых с действием «закрыть: пустая карточка»",
    "check_n": "старых открытых с действием «проверить: вероятно, уже решено»", "plan_n": "старых открытых с действием «решить с разработкой»",
    "rel_n": "старых открытых с действием «довести до релиза»",
    "dup_close": "из «дублей» — карточек, которые можно сразу закрыть как дубль",
    "quick_close": "старых открытых можно закрыть без разработки: по регламенту + пустые + вероятно решено + дубли к закрытию",
    "pr_n": "ручных правок данных без НСИ, решено за период", "pr_h": "часов на ручные правки данных без НСИ за период",
    "pr_defect": "из ручных правок — по сути дефекты системы (тип по сути инцидент или причина «дефект системы»)",
    "nsi_n": "НСИ (раздел «Нормализация») — решено за период", "nsi_med": "медиана срока решения НСИ, раб. ч",
    "nsi_kontr": "НСИ за период с объектом правки «Контрагент…»",
    "inc_open": "открытых инцидентов (тип при регистрации)", "inc_in": "пришло инцидентов за период (тип при регистрации)",
    "inc_sol": "решено инцидентов за период (тип при регистрации)", "inc_ai": "решено за период инцидентов по сути (оценка ИИ)",
    "hidden_ratio": "во сколько раз инцидентов по сути больше, чем зарегистрировано", "inc_old": "открытых инцидентов старше 30 дней",
    "inc_dev": "открытых инцидентов старше 30 дней у разработки",
    "mis_n": "решённых за период с неверным типом (тип при регистрации ≠ тип по сути)", "sol_ai": "решённых за период с разметкой ИИ, без служебных",
    "mis_pct": "доля неверного типа среди размеченных, %", "mis_to_inc": "из неверных — по сути инциденты",
    "bad_n": "решений за период с оценкой «Плохо»",
    "pl_4w": "обращений по планшетам: зарегистрированы за 4 недели + все открытые", "pl_open": "из них открыто", "pl_rej": "из них отклонено",
    "pl_mass": "из них — массовый сбой", "pl_login": "из них — вход и учётная запись", "pl_func": "из них — функции мобильного инженера",
    "pl_hang": "из них — зависания и запуск", "pl_net": "из них — связь в ремзонах", "pl_other": "из них — доработки и прочее",
    "pl_sd": "из них решено словами «передано в Сервис Деск»", "pl_l1": "из них у первой линии",
    "inc_hpt": "часов трудозатрат на один решённый инцидент", "pr_hpt": "часов трудозатрат на одну правку данных",
    "wait_ratio": "медиана: календарных часов от регистрации до решения на час работы (решённые за период с трудозатратами)",
    "zombie": "старых открытых без единого часа трудозатрат",
    "top7_n": "обращений в топ-7 групп тем", "top7_nsi": "групп НСИ в топ-7",
    "real_n": "решено за период без служебных карточек", "long_h_thr": "порог долгостроя, раб. ч",
    "lng_share": "доля долгостроя среди решённых без служебных, %", "lng_h": "суммарный срок долгостроев, раб. ч",
    "lng_trud": "трудозатраты на долгострои, ч", "lng_work_pct": "доля работы (трудозатрат) в сроке долгостроев, %",
    "lng_cons": "долгостроев-консультаций", "lng_cons_trud": "трудозатраты на долгострои-консультации, ч",
    "lng_cons_h": "срок долгостроев-консультаций, раб. ч", "lng_two": "долгостроев у двух аналитиков, у которых их больше всего",
    "lng_top_h": "срок самого долгого обращения, раб. ч", "lng_top_pct": "его доля в часах долгостроя, %",
    "lng_med": "медиана срока долгостроев, раб. ч",
}
ANL_INFO = {"sol": "решено за период", "mis": "из них с неверным типом", "med": "медиана срока решённых за период, раб. ч",
            "bad": "оценок «Плохо» за период", "old": f"открытых старше {OLD_DAYS} дней", "old0": "из них без единого часа",
            "zero4w": "доля решённых за 4 недели без часов, %"}


def metric_info(R, k):
    if k in METRIC_INFO: return METRIC_INFO[k]
    if k.startswith("why_"):
        code = k[4:].removesuffix("_h")
        if code in WHY_KEYS:
            return ("часов на " if k.endswith("_h") else "") + f"правки данных без НСИ за период с причиной «{WHY_KEYS[code]}»"
    if k.startswith("n_s"): return "номер слайда в отчёте"
    if k.startswith("pl_dev_"): return f"обращений по планшетам с номером устройства {k[7:]}"
    if k.startswith("obj_"): return f"решённых за период с объектом правки «{R.obj_keys.get(k, '')}»"
    if k.startswith("a_"):
        for nm, s in R.anl_slug.items():
            if k.startswith(f"a_{s}_") and k[len(s) + 3:] in ANL_INFO:
                return f"{short(nm)}: {ANL_INFO[k[len(s) + 3:]]}"
    return ""


def catalog_text(R):
    """Каталог метрик для промпта: общие — строкой «{ключ} = значение — описание», по людям — таблицей."""
    M = R.M
    lines = ["Общие метрики:"]
    fam = ("a_", "pl_dev_", "obj_")
    for k, v in M.items():
        if v is None or k.startswith(fam): continue
        lines.append(f"{{{k}}} = {c1(v)} — {metric_info(R, k)}")
    lines.append("")
    lines.append("По аналитикам: ключ a_<код>_<метрика>, например {a_%s_sol}. Метрики: " % (next(iter(R.anl_slug.values()), "ivanov"))
                 + "; ".join(f"{k} — {d}" for k, d in ANL_INFO.items()) + ".")
    for nm, s in R.anl_slug.items():
        vals = ", ".join(f"{k}={c1(M[f'a_{s}_{k}'])}" for k in ANL_INFO if f"a_{s}_{k}" in M)
        lines.append(f"{s} — {nm}: {vals}")
    if R.devices:
        lines.append("")
        lines.append("Устройства-планшеты (число обращений с номером): " + "; ".join(f"{{pl_dev_{x}}} = {v}" for x, v in R.devices.most_common()))
    if R.obj_keys:
        lines.append("")
        lines.append("Объекты правки (решено за период): " + "; ".join(f"{{{k}}} = {M[k]} «{o}»" for k, o in sorted(R.obj_keys.items(), key=lambda kv: -M[kv[0]])))
    return "\n".join(lines)


def fmt_plain(R, s):
    """Текст ИИ с подставленными цифрами, без HTML: для истории решений и для промпта сводного разбора."""
    return re.sub(r"\{(\w+)\}", lambda m: c1(R.M.get(m.group(1))) if m.group(1) in R.M else m.group(0), str(s or ""))


# ================================================================ ПРОВЕРКА ОТВЕТОВ ИИ
KEY_RX = re.compile(r"\{(\w+)\}")
ID_RX = re.compile(r"\d{2}-\d{8}")
WORD_RX = re.compile(r"[а-яёa-z0-9]+")


def _strings(o, path=()):
    """(путь, текст) для всех строк ответа; путь — кортеж ключей и индексов."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _strings(v, path + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _strings(v, path + (i,))
    elif isinstance(o, str):
        yield path, o


def path_str(p):
    return "".join(f"[{x}]" if isinstance(x, int) else (f".{x}" if i else str(x)) for i, x in enumerate(p)) or "ответ"


def _check_text(R, o):
    """Ключи метрик и номера обращений во всех строках ответа."""
    errs = []
    for p, t in _strings(o):
        for k in KEY_RX.findall(t):
            if R.M.get(k) is None:
                errs.append((p, f"неизвестный ключ метрики {{{k}}}"))
        for x in ID_RX.findall(t):
            if x not in R.RAWID:
                errs.append((p, f"номера {x} нет в выгрузке"))
    return errs


def quote_ok(R, rid, q):
    """Цитата есть в тексте обращения: не меньше 60% слов (от 4 букв) встречаются в описании и решении."""
    r = R.RAWID.get(rid)
    if not r or not q: return False
    norm = lambda s: [w for w in WORD_RX.findall(str(s).lower().replace("ё", "е")) if len(w) >= 4]
    tw = set(norm(f"{r.get('desc', '')} {r.get('sol', '')}"))
    qw = norm(q)
    return bool(qw) and sum(w in tw for w in qw) / len(qw) >= 0.6


def validate(R, part, obj, key=None):
    """Проверка ответа ИИ кодом (HANDOFF, разд. 0). Возвращает [(путь, ошибка)]; пусто — ответ годен.
    part: slide (key = s1…s11), open_crit, planshet, signals."""
    errs = []
    if part == "slide":
        s = obj
        if not isinstance(s, dict): return [((), "ответ — не объект JSON")]
        if not isinstance(s.get("summary"), str) or not s["summary"].strip():
            errs.append((("summary",), "нет summary"))
        for name, fields in {"items": SLIDE_ITEM, **SLIDE_EXTRA.get(key, {})}.items():
            lst = s.get(name)
            if not isinstance(lst, list):
                errs.append(((name,), f"{name} — не список")); continue
            for i, x in enumerate(lst):
                p = (name, i)
                if not isinstance(x, dict):
                    errs.append((p, "строка — не объект")); continue
                miss = [f for f in fields if f not in x]
                if miss: errs.append((p, "нет полей " + ", ".join(miss)))
                for f in fields:
                    if f == "ids" and f in x:
                        if not isinstance(x["ids"], list):
                            errs.append((p, "ids — не список номеров"))
                        else:
                            errs += [(p, f"«{v}» — не номер обращения вида 00-00012345") for v in x["ids"] if not (isinstance(v, str) and ID_RX.fullmatch(v))]
                    elif f in x and not isinstance(x[f], str):
                        errs.append((p, f"{f} — не строка"))
        sol_ids = {r["id"] for r in R.sol}
        ai_ids = {r["id"] for r in R.sol_ai}
        if key == "s3":
            for i, x in enumerate(s.get("notsolved") or []):
                if not isinstance(x, dict): continue
                if x.get("id") not in sol_ids:
                    errs.append((("notsolved", i), f"{x.get('id')} — не из решённых за период"))
                if x.get("risk") not in ("высокий", "средний", "низкий"):
                    errs.append((("notsolved", i), "risk — не «высокий / средний / низкий»"))
        if key == "s6":
            for i, x in enumerate(s.get("best") or []):
                if isinstance(x, dict) and x.get("id") not in ai_ids:
                    errs.append((("best", i), f"{x.get('id')} — не из размеченных решённых за период"))
        if key == "s4":
            for i, x in enumerate(s.get("nsi_nonedit") or []):
                if isinstance(x, dict) and (x.get("id") not in R.BYID or R.BYID[x["id"]]["sec"] != NSI_SECTION):
                    errs.append((("nsi_nonedit", i), f"{x.get('id')} — не обращение раздела «{NSI_SECTION}»"))
        if key == "s9":
            if not isinstance(s.get("fix"), dict):
                errs.append((("fix",), "fix — не объект «ФИО: что поправить»"))
            else:
                for nm, t in s["fix"].items():
                    if nm not in R.anl_slug or not isinstance(t, str):
                        errs.append((("fix", nm), f"«{nm}» — нет такого аналитика (ФИО полностью, как в выгрузке)"))
            for c in ("case_best", "case_worst"):
                x = s.get(c)
                if not isinstance(x, dict) or not isinstance(x.get("why"), str) or x.get("id") not in ai_ids:
                    errs.append(((c,), f"{c}: нужен id размеченного решённого за период и why"))
        errs += _check_text(R, s)
    elif part == "open_crit":
        if not isinstance(obj, list): return [((), "open_crit — не список")]
        for i, x in enumerate(obj):
            if not isinstance(x, dict) or not isinstance(x.get("why"), str):
                errs.append(((i,), "нужны id и why")); continue
            r = R.BYID.get(x.get("id"))
            if not r or not r["is_open"]: errs.append(((i,), f"{x.get('id')} — не открытое обращение"))
        errs += _check_text(R, obj)
    elif part == "planshet":
        if not isinstance(obj, dict): return [((), "planshet — не объект «номер: причина»")]
        pl_ids = {r["id"] for r in R.pl}
        for rid, kind in obj.items():
            if rid not in pl_ids:
                errs.append(((rid,), f"{rid} — не обращение по планшетам"))
            elif not isinstance(kind, str) or not (kind in PL_KINDS or re.fullmatch(r"Массовый сбой \d\d\.\d\d", kind)):
                errs.append(((rid,), f"причина «{kind}» не из списка"))
    elif part == "signals":
        if not isinstance(obj, list): return [((), "signals — не список")]
        for i, x in enumerate(obj):
            if not isinstance(x, dict) or not all(isinstance(x.get(f), str) for f in ("id", "q", "k", "a")):
                errs.append(((i,), "нужны id, q, k, a")); continue
            if x["id"] not in R.RAWID:
                errs.append(((i,), f"номера {x['id']} нет в выгрузке"))
            elif not quote_ok(R, x["id"], x["q"]):
                errs.append(((i,), f"цитаты «{x['q'][:60]}» нет в тексте {x['id']}"))
        errs += _check_text(R, obj)
    return errs


def errors_text(errs):
    return "; ".join(f"{path_str(p)}: {m}" for p, m in errs)


def sanitize(obj, errs):
    """Отбрасывает строки ответа с ошибками, остальное оставляет — после последней неудачной попытки."""
    if any(not p for p, _ in errs):                     # ответ негоден целиком
        return [] if isinstance(obj, list) else {}
    if isinstance(obj, list):
        bad = {p[0] for p, _ in errs}
        return [x for i, x in enumerate(obj) if i not in bad]
    out = dict(obj)
    drop = defaultdict(set)
    for p, _ in errs:
        name, v = p[0], out.get(p[0])
        if name == "summary":
            out["summary"] = "Разбор ИИ по слайду прошёл проверку частично: строки с ошибками отброшены."
        elif name in ("case_best", "case_worst") or isinstance(v, str):
            out.pop(name, None)
        elif len(p) == 1 or not isinstance(v, (list, dict)):
            out[name] = {} if (isinstance(v, dict) or name == "fix") else []
        else:
            drop[name].add(p[1])
    for name, bad in drop.items():
        v = out.get(name)
        if isinstance(v, list): out[name] = [x for i, x in enumerate(v) if i not in bad]
        elif isinstance(v, dict): out[name] = {k: x for k, x in v.items() if k not in bad}
    return out


# ================================================================ ИСТОРИЯ НЕДЕЛЬ (формат v2, hist_ver = 3)
def normalize_history(lst):
    """Записи истории v4 (year, week_num, total_tickets, med_hour, incidents) и v5 — в один список по возрастанию недель."""
    out = {}
    for rec in lst or []:
        try:
            k = (int(rec.get("year", 0)), int(rec.get("week_num", 0)))
        except (TypeError, ValueError, AttributeError):
            continue
        if k[0] and k[1]:
            out[k] = dict(rec, year=k[0], week_num=k[1])
    return [out[k] for k in sorted(out)]


def history_records(R, decisions=None):
    """Записи истории за недели, которые выгрузка покрывает целиком, — из 4 недель отчёта.
    Отчётная неделя — ещё и очередь на срез и решения руководителя (Т-52, В-15)."""
    out = []
    for w in R.wk:
        if w["a"] < datetime(R.first_res.year, R.first_res.month, R.first_res.day):
            continue          # неделя началась раньше первого решения в выгрузке — данные неполные, не пишем
        y, n = w["a"].isocalendar()[0], w["a"].isocalendar()[1]
        cc = lambda lst: dict(Counter(r["cat"] for r in lst))
        mm = lambda lst, f: {m: dict(Counter(r["cat"] for r in lst if f"{r[f]:%Y-%m}" == m)) for m in sorted({f"{r[f]:%Y-%m}" for r in lst})}
        rec = {"year": y, "week_num": n, "hist_ver": 3, "total_tickets": len(w["s"]), "med_hour": med([r["h"] for r in w["s"]]) or 0.0,
               "incidents": sum(r["type"] == "Инцидент" for r in w["s"]), "partial": (w["b"] - w["a"]).days < 7,
               "in": cc(w["i"]), "sol": cc(w["s"]), "rej": cc(w["j"]), "in_m": mm(w["i"], "reg_dt"), "sol_m": mm(w["s"], "done_dt")}
        if w is R.wk[-1]:
            rec.update(open=len(R.opn), open_gt30=len(R.old), holders=dict(Counter(r["holder"] for r in R.opn)),
                       dump=R.dump_name, decisions=decisions or [])
        out.append(rec)
    return out


def merge_history(old, new):
    m = {(r["year"], r["week_num"]): r for r in normalize_history(old)}
    for r in new:
        prev = m.get((r["year"], r["week_num"]), {})
        # решения недели не затираются пересчётом той же недели без разборов ИИ
        if not r.get("decisions") and prev.get("decisions"): r = dict(r, decisions=prev["decisions"])
        m[(r["year"], r["week_num"])] = r
    return [m[k] for k in sorted(m)]


def prev_decisions(R):
    """Решения руководителя прошлой недели из истории (Т-52): [(неделя, [решения])] или None."""
    py, pw = (R.WS - timedelta(days=7)).isocalendar()[:2]
    for rec in R.history:
        if (rec["year"], rec["week_num"]) == (py, pw) and rec.get("decisions"):
            return pw, rec["decisions"]
    return None


# ================================================================ ВЁРСТКА
def _num(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _months6(R):
    """Последние 6 месяцев, заканчивая месяцем последнего дня периода: [(год, месяц)]."""
    last = R.WE - timedelta(days=1)
    y, m, out = last.year, last.month, []
    for _ in range(6):
        out.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def _build(R, with_ai=True, strict=False, run_log=None):
    """Слайды отчёта: (меню, {ключ слайда: HTML}). with_ai=False — без блоков «Разбор ИИ по слайду» (текст для промпта)."""
    raw, rows, dropped = R.raw, R.rows, R.dropped
    AI, AIT, AIO, BYID, RAWID, M = R.AI, R.AIT, R.AIO, R.BYID, R.RAWID, R.M
    NOW, WS, WE, WEEK, DAYS, PER, PER_S, rule, in_per = R.NOW, R.WS, R.WE, R.WEEK, R.DAYS, R.PER, R.PER_S, R.rule, R.in_per
    sol, inc, rej, opn, opn_svc, old, real, L1, L2 = R.sol, R.inc, R.rej, R.opn, R.opn_svc, R.old, R.real, R.L1, R.L2
    bycat, dev, pr, nsi, inc_types, mis, sol_ai, top7 = R.bycat, R.dev, R.pr, R.nsi, R.inc_types, R.mis, R.sol_ai, R.top7
    pl, wk, WEEKS4, W4S, OPEN_CRIT = R.pl, R.wk, R.WEEKS4, R.W4S, R.OPEN_CRIT
    TAB_ON, TAB_BAD, TRUD_MISMATCH, DEMO_TAB = R.TAB_ON, R.TAB_BAD, R.TRUD_MISMATCH, R.demo
    wn = lambda w: w["a"].isocalendar()[1]
    WL = f"W{wn(wk[0])}–W{wn(wk[-1])}"                 # ЧТО ИЗМЕНЕНО: было зашито «W36–W39»
    months = _months6(R)
    (y0, m0), (y5, m5) = months[0], months[-1]
    mlab = f"{MON[m0]}–{MON[m5]} {y5}" if y0 == y5 else f"{MON[m0]} {y0}–{MON[m5]} {y5}"   # было зашито «апр–сен 2026»

    def fmt(s):
        def rep(m):
            k = m.group(1)
            if M.get(k) is None:
                # ЧТО ИЗМЕНЕНО: неизвестный ключ в боевом отчёте — «—» и предупреждение, а не падение после часа платных вызовов
                # ПОЧЕМУ: ответы ИИ проверяются до вёрстки (validate); здесь — последняя страховка
                if strict:
                    raise KeyError(f"Разбор ИИ ссылается на неизвестную метрику {{{k}}}")
                R.warnings.append(f"неизвестная метрика {{{k}}}")
                return "—"
            v = M[k]
            return str(v).replace(".", ",") if isinstance(v, float) else str(v)
        # ЧТО ИЗМЕНЕНО: текст ИИ экранируется до подстановки цифр. ПОЧЕМУ: в v5 текст пишет модель, читающая обращения пользователей
        return re.sub(r"\{(\w+)\}", rep, E(s if s is not None else ""))

    STAMP = {
        "in": ("▲", f"Пришло {PER_S}"), "sol": ("▼", f"Решено {PER_S}"), "rej": ("✕", f"Отклонено {PER_S}"),
        "open": ("●", f"Открыто на {NOW:%d.%m}"), "w4": ("◇", f"4 недели {WEEKS4[0][0]:%d.%m}–{PER_S[-5:]}"),
        "sol4": ("▼", f"Решено · 4 недели {WEEKS4[0][0]:%d.%m}–{PER_S[-5:]}"), "in4": ("▲", f"Пришло · 4 недели {WEEKS4[0][0]:%d.%m}–{PER_S[-5:]}"),
        "sol6": ("▼", f"Решено · {mlab}"), "in6": ("▲", f"Пришло · {mlab}"),
        "ai": ("✦", "Разбор ИИ"), "all": ("◆", "Вся выгрузка"), "demo": ("⚠", "Демо-данные: табличные части выдуманы"),
    }

    def stamps(*keys):
        return '<div class="stamps">' + "".join(
            f'<span class="stamp s-{k}"><i>{STAMP[k][0]}</i>{E(STAMP[k][1])}</span>' for k in keys) + "</div>"

    def tk(i, full=False):
        """Номер обращения + дата регистрации (+ решения) + аналитик — Т-2, Т-3."""
        r = BYID.get(i) or RAWID.get(i)
        if r is None:
            return f'<span class="tid">{E(i)}</span>'
        reg = P(r["reg"]) if isinstance(r.get("reg"), str) else r["reg_dt"]
        res = P(r["res"]) if r.get("res") else None
        d = f"рег {DD(reg)}" + (f" · реш {DD(res)}" if res else "")
        if not res and r.get("st") not in SOLVED + [REJECTED]:
            d += f" · {(NOW - reg).days} дн."
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: открытое обращение с датой решения показывается как возврат, с возрастом
        # ПОЧЕМУ: 00-00034389 в «Анализе» выглядело решённым («реш 04.09», без возраста)
        # ----------------------------------------------------------------------
        if res and r.get("st") not in SOLVED + [REJECTED]:
            d = f"рег {DD(reg)} · возврат: решение {DD(res)} · {(NOW - reg).days} дн."
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: если у обращения есть поле url — номер становится ссылкой, как пришла из выгрузки
        # ПОЧЕМУ: Т-57 (В-13: тонкий клиент, ссылка приходит готовой и просто открывается; нет поля — номер остаётся текстом)
        # ----------------------------------------------------------------------
        url = r.get("url")
        tid = f'<a class="tid" href="{E(url)}">{E(i)}</a>' if url else f'<span class="tid">{E(i)}</span>'
        return (f'<span class="tk">{tid}<small>{d} · {E(short(r.get("anl", "")))}</small></span>')

    def tks(ids):
        return "".join(tk(i) for i in ids)

    def panel(title, st, body, what, use, cls=""):
        return (f'<section class="panel {cls}"><header class="ph"><h3>{title}</h3>{st}</header><div class="pb">{body}</div>'
                f'<p class="why"><b>Что это.</b> {what}</p><p class="use"><b>Польза / проблема.</b> {use}</p></section>')

    AI_WHAT = ('Постоянный блок внизу слайда (Т-43): ИИ пишет вывод по схеме «факт → вывод → действие → кому → эффект», '
               'цифры подставляет код, номера обращений проверяются по выгрузке.')
    AI_USE = 'Превращает графики в решения: кого поправить, где поменять процесс, что чинить первым.'

    def ai_block(key, extra=""):
        if not with_ai:
            return ""
        s = AI["slides"].get(key)
        if not s:
            # ----------------------------------------------------------------------
            # ЧТО ИЗМЕНЕНО: нет разбора (сбой модели или ответ не прошёл проверку) — нейтральная строка, отчёт строится дальше
            # ПОЧЕМУ: как в v4.2 — читателю отчёта текст ошибки не нужен, он в журнале запуска
            # ----------------------------------------------------------------------
            return (f'<section class="panel aibox"><header class="ph"><h3>✦ Разбор ИИ по слайду</h3>{stamps("ai")}</header>'
                    f'<div class="pb"><p class="ai-sum">Разбор ИИ недоступен: сбой модели или ответ не прошёл проверку. Подробности — в журнале запуска.</p></div>'
                    f'<p class="why"><b>Что это.</b> {AI_WHAT}</p><p class="use"><b>Польза / проблема.</b> {AI_USE}</p></section>')
        rows_ = "".join(
            f'<tr><td>{fmt(x.get("fact"))}{("<div class=ids>" + tks(x["ids"]) + "</div>") if x.get("ids") else ""}</td>'
            f'<td>{fmt(x.get("conc"))}</td><td><b>{fmt(x.get("act"))}</b></td><td>{E(x.get("who", ""))}</td><td>{fmt(x.get("eff")) or "—"}</td></tr>'
            for x in s.get("items", []))
        tbl = (f'<div class="tw"><table class="ai"><thead><tr><th>Факт</th><th>Вывод</th><th>Действие</th><th>Кому</th><th>Эффект</th></tr></thead>'
               f'<tbody>{rows_}</tbody></table></div>') if rows_ else ""
        return (f'<section class="panel aibox"><header class="ph"><h3>✦ Разбор ИИ по слайду</h3>{stamps("ai")}</header>'
                f'<div class="pb"><p class="ai-sum">{fmt(s.get("summary"))}</p>{tbl}{extra}</div>'
                f'<p class="why"><b>Что это.</b> {AI_WHAT}</p>'
                f'<p class="use"><b>Польза / проблема.</b> {AI_USE}</p></section>')

    def legend(cats, colors=CAT_COLOR):
        return '<div class="legend">' + "".join(f'<span><i style="background:{colors[c]}"></i>{c}</span>' for c in cats) + "</div>"

    def stack_svg(groups, cats, w=560, h=230, ymax=None, label_top=True, colors=CAT_COLOR):
        """groups: [(подпись, {кат: n}, признак_пусто)] → столбцы с разбивкой по категориям."""
        n = len(groups); pad_l, pad_b, pad_t = 30, 34, 18
        ymax = ymax or max([sum(g[1].values()) for g in groups] + [1])
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: шкала Y — «круглые» деления (шаг 1/2/5/10/20/25/50/100…), линии сетки темнее
        # ПОЧЕМУ: Т-58 — прежние 4 равные доли давали повторы подписей (0,1,1,4,5) и бледную сетку;
        #         при общем ymax у двух графиков шкала совпадает (поток по дням)
        # ----------------------------------------------------------------------
        tick = next((s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500) if -(-ymax // s) <= 5), 10 ** len(str(int(ymax))))
        nt = -(-ymax // tick)
        ymax = nt * tick
        bw = (w - pad_l - 10) / n * 0.62
        step = (w - pad_l - 10) / n
        out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img">']
        for k in range(0, nt + 1):
            y = h - pad_b - (h - pad_b - pad_t) * k / nt
            v = k * tick
            out.append(f'<line class="grid" x1="{pad_l}" x2="{w-4}" y1="{y:.1f}" y2="{y:.1f}"/><text class="ax" x="{pad_l-6}" y="{y+4:.1f}" text-anchor="end">{v}</text>')
        for gi, (lab, vals, empty) in enumerate(groups):
            x = pad_l + step * gi + (step - bw) / 2
            y = h - pad_b
            tot = sum(vals.values())
            if empty:
                out.append(f'<rect class="nodata" x="{x:.1f}" y="{pad_t+20}" width="{bw:.1f}" height="{h-pad_b-pad_t-20}" rx="3"/>'
                           f'<text class="ax" x="{x+bw/2:.1f}" y="{h/2:.1f}" text-anchor="middle">н/д</text>')
            for c in cats:
                v = vals.get(c, 0)
                if not v: continue
                hh = (h - pad_b - pad_t) * v / ymax
                y -= hh
                out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(hh-2,1):.1f}" fill="{colors[c]}" rx="1.5"><title>{E(lab)}: {c} — {v}</title></rect>')
            if tot and label_top:
                out.append(f'<text class="val" x="{x+bw/2:.1f}" y="{y-5:.1f}" text-anchor="middle">{tot}</text>')
            out.append(f'<text class="ax day" x="{x+bw/2:.1f}" y="{h-pad_b+16}" text-anchor="middle">{E(lab.split("|")[0])}</text>')
            if "|" in lab:
                out.append(f'<text class="ax" x="{x+bw/2:.1f}" y="{h-pad_b+29}" text-anchor="middle">{E(lab.split("|")[1])}</text>')
        out.append("</svg>")
        return "".join(out)

    def hbars(items, color="#3B4754", unit="", maxv=None, fmtv=lambda v: v):
        maxv = maxv or max([v for _, v, _ in items] + [1])
        return '<div class="hbars">' + "".join(
            f'<div class="hb"><span class="hb-l" title="{E(l)}">{E(l)}</span><span class="hb-t"><i style="width:{100*v/maxv:.0f}%;background:{c or color}"></i></span>'
            f'<span class="hb-v">{fmtv(v)}<small>{unit}</small></span></div>' for l, v, c in items) + "</div>"

    def kpi(title, st, big, unit, l1, l2, note, cls=""):
        return (f'<div class="kpi {cls}">{st}<h4>{title}</h4><div class="kpi-v">{big}<span>{unit}</span></div>'
                f'<div class="kpi-lines"><span><b>{l1}</b> первая линия</span><span><b>{l2}</b> вторая линия</span></div>'
                f'<div class="kpi-s">{note}</div></div>')

    def holder_rows(lst, show_anl=False):
        """Кто держит: полоса по возрасту + число + медиана возраста + часы."""
        buckets = [("≤ 7 дн", 0, 7, "#9DB6CF"), ("8–30 дн", 8, 30, "#5D86B0"), ("31–90 дн", 31, 90, "#B7800F"), ("> 90 дн", 91, 10**6, "#B3261E")]
        mx = max([len([r for r in lst if r["holder"] == h]) for h in HOLDERS] + [1])
        out = []
        for h in HOLDERS:
            o = [r for r in lst if r["holder"] == h]
            segs = ""
            for lab, a, b, col in buckets:
                n = sum(a <= r["age"] <= b for r in o)
                if n:
                    segs += f'<i style="width:{100*n/mx:.1f}%;background:{col}" title="{lab}: {n}">{n if n>1 else ""}</i>'
            sts = Counter(r["st"] for r in o).most_common(3)
            out.append(f'<div class="own"><div class="own-l"><b>{h}</b><small>{E(", ".join(f"{s} {n}" for s, n in sts))}</small></div>'
                       f'<div class="own-b">{segs}</div><div class="own-n">{len(o)}<small>медиана {med([r["age"] for r in o]) or 0:.0f} дн · {hsum(o):.0f} ч</small></div></div>')
        leg = '<div class="legend">' + "".join(f'<span><i style="background:{c}"></i>{l}</span>' for l, _, _, c in buckets) + "</div>"
        return "".join(out) + leg

    h1 = lambda x: "—" if x is None else f"{x:.1f} ч".replace(".", ",")

    # ================================================================ СЛАЙД 1 — неделя
    def slide1():
        cc = lambda lst: Counter(r["cat"] for r in lst)
        inc_c, sol_c, rej_c = cc(inc), cc(sol), cc(rej)
        was = len(opn) - M["dq"]
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: баланс потока — цветные числа, у каждого из четырёх чисел плашки I / II линия,
        #               под числами — яркие разбивки: «Пришло» (инциденты / правка данных / остальное),
        #               «Решено» (из пришедших за период / из прошлых периодов), «Отклонено» (все типы)
        # ПОЧЕМУ: Т-60 — цифры под значениями это информация, а не комментарий; разбивка «из прошлых
        #         периодов» показывает, разбираем ли мы хвост или только текущий поток
        # ----------------------------------------------------------------------
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО (v5): плашки I / II — справа от большого числа, столбиком (обёртка .nl)
        # ПОЧЕМУ: Т-60, замечание пользователя № 2 (HANDOFF, разд. 4): по образцу «203 → I 103 / II 100», а не строкой под числом
        # ----------------------------------------------------------------------
        ln = lambda lst: (f'<div class="ln"><span title="первая линия"><i>I</i>{sum(r["line"] == "L1" for r in lst)}</span>'
                          f'<span title="вторая линия"><i>II</i>{sum(r["line"] == "L2" for r in lst)}</span></div>')
        nl = lambda big, lines: f'<div class="nl"><b>{big}</b>{lines}</div>'
        dl1 = sum(r["line"] == "L1" for r in inc) - sum(r["line"] == "L1" for r in sol) - sum(r["line"] == "L1" for r in rej)
        dl2 = M["dq"] - dl1
        # инциденты — по типу при регистрации, как в плитке «Инциденты» (включая инциденты в разделе НСИ), чтобы числа на слайде совпадали
        inc_i = sum(r["type"] == "Инцидент" for r in inc)
        other = len(inc) - inc_i - inc_c["Правка данных"]
        sol_new = sum(in_per(r["reg_dt"]) for r in sol)
        sub = lambda *p: '<div class="sub3">' + "".join(f'<span>{a}<b>{b}</b></span>' for a, b in p) + "</div>"
        rej_sub = sub(*[(k.lower(), v) for k, v in rej_c.most_common()]) if rej_c else '<div class="sub3"><span>нет</span></div>'
        bal = (f'<div class="eqbar"><div class="in"><span class="k">▲ Пришло</span>{nl(len(inc), ln(inc))}'
               f'{sub(("инциденты, все разделы", inc_i), ("правка данных без НСИ", inc_c["Правка данных"]), ("остальное", other))}</div><em>−</em>'
               f'<div class="sl"><span class="k">▼ Решено</span>{nl(len(sol), ln(sol))}'
               f'{sub(("из пришедших за период", sol_new), ("из прошлых периодов", len(sol) - sol_new))}</div><em>−</em>'
               f'<div class="rj"><span class="k">✕ Отклонено</span>{nl(len(rej), ln(rej))}{rej_sub}</div><em>=</em>'
               f'<div class="res {"up" if M["dq"] > 0 else ""}"><span class="k">Очередь за период</span>'
               + nl(f'{M["dq"]:+d}', f'<div class="ln"><span title="первая линия"><i>I</i>{dl1:+d}</span><span title="вторая линия"><i>II</i>{dl2:+d}</span></div>')
               + f'{sub(("было ≈", was), ("стало", len(opn)))}</div></div>')
        p0 = panel("Справились ли с потоком", stamps("in", "sol", "rej", "open"), bal,
                   f"Пришедшие, решённые и отклонённые за {PER}; «было» — расчётно: открыто сейчас минус изменение за период.",
                   "Главный вопрос недели одной строкой: растёт очередь или тает. Рост две недели подряд — сигнал добавлять людей или резать поток.", "hero")
        # строка 1 — показатели с разбивкой по линиям (Т-14)
        le8 = lambda l: f'{pct(sum(r["h"] <= FAST_H for r in l), len(l))}%'
        oi = [r for r in opn if r["type"] == "Инцидент"]
        ii = [r for r in inc if r["type"] == "Инцидент"]
        prev_med = med([r["h"] for r in wk[-2]["s"]])
        k = [kpi("Время до решения, медиана", stamps("sol"), c1(M["med_all"]), "раб. ч",
                 h1(M["med_l1"]), h1(M["med_l2"]),
                 f'неделей ранее {h1(prev_med)}' + "; раб. ч: 8 ч в рабочем дне, выходные не считаются"),
             kpi("Решено в пределах рабочего дня", stamps("sol"), le8(real)[:-1], "%", le8(L1), le8(L2), f"≤ {FAST_H} раб. ч от регистрации до решения"),
             kpi("Долгострой", stamps("sol"), str(M["long_all"]), "обращ.", str(M["long_l1"]), str(M["long_l2"]), f'решены, но шли дольше {LONG_H} раб. ч · <a href="#s11">подробно →</a>'),
             kpi("Инциденты", stamps("open", "in"), str(len(oi)), "открыто", f'{sum(r["line"]=="L1" for r in oi)} откр.', f'{sum(r["line"]=="L2" for r in oi)} откр.',
                 # ЧТО ИЗМЕНЕНО: «пришло за период» — отдельная крупная красная строка с разбивкой I / II
                 # ПОЧЕМУ: Т-62 — число было серым комментарием, а это главный сигнал плитки
                 f'<div class="inc-new"><b>{len(ii)}</b> пришло за {PER_S}<span>I {sum(r["line"]=="L1" for r in ii)} · II {sum(r["line"]=="L2" for r in ii)}</span></div>', "kpi-inc")]
        row1 = ('<div class="grid g4">' + "".join(k) + "</div>"
                '<p class="why rowwhy"><b>Что это.</b> Крупно — общее значение, мелко — первая линия (Попова А. В. или решение со ссылкой на confluence) и вторая. '
                'Служебные карточки из расчёта исключены.</p><p class="use rowwhy"><b>Польза / проблема.</b> Видно, чья скорость тянет общую цифру вниз: '
                'если вторая линия медленнее в разы, улучшать надо её маршрут, а не всю поддержку.</p>')
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: таблица «Долгострой» убрана со слайда 1 — теперь отдельный слайд (slide11)
        # ПОЧЕМУ: Т-61, ответ на В-11 «б» — на первом слайде только крупное, детали по плитке — на своём слайде
        # ----------------------------------------------------------------------
        # строка 2 — медианы по типам (Т-15)
        cards = ""
        for c in CATS + ["Служебное"]:
            s = [r for r in sol if r["cat"] == c]
            if not s: continue
            cards += (f'<div class="tc" style="--c:{CAT_COLOR[c]}"><span>{c}</span><b>{c1(med([r["h"] for r in s]))}</b><small>раб. ч медиана</small>'
                      f'<em>{len(s)} решено · {hsum(s):.0f} ч трудозатрат</em></div>')
        row2 = panel("Сколько ждут решения — по типам", stamps("sol"), f'<div class="tcs">{cards}</div>',
                     "Медиана от регистрации до решения по типу при регистрации. НСИ — раздел «Нормализация» целиком, «Правка данных» — без НСИ. Трудозатраты — поле AmountTrud.",
                     "Сравнение типов между собой: какой тип заставляет ждать и сколько стоит в часах. Инцидент в десятки раз медленнее правки — место для ускорения.")
        # строка 3 — поток по дням и типам
        days_in = [(f"{WD[d.weekday()]}|{d:%d.%m}", Counter(r["cat"] for r in inc if r["reg_dt"].date() == d.date()), False) for d in DAYS]
        days_sol = [(f"{WD[d.weekday()]}|{d:%d.%m}", Counter(r["cat"] for r in sol if r["done_dt"].date() == d.date()), False) for d in DAYS]
        ym = max(max(sum(g[1].values()) for g in days_in), max(sum(g[1].values()) for g in days_sol))
        cats7 = CATS + ["Служебное"]
        row3 = panel("Поток по дням и типам", stamps("in", "sol"),
                     f'<div class="grid g2"><div><div class="ch">Что пришло — по дню регистрации</div>{stack_svg(days_in, cats7, ymax=ym)}</div>'
                     f'<div><div class="ch">Что решено — по дню решения</div>{stack_svg(days_sol, cats7, ymax=ym)}</div></div>{legend(cats7)}',
                     "Слева — нагрузка на входе, справа — выход, шкала одна. Цвет — тип обращения.",
                     "Видно, в какие дни не успевали и какой тип копится: если столбец справа ниже левого — очередь в этот день росла.")
        # строка 4 — динамика по неделям
        wgroups = []
        for w in wk:
            nd = (w["b"] - w["a"]).days
            lab = f'W{w["a"].isocalendar()[1]}|{w["a"]:%d.%m}' + (f" · {nd} дн." if nd < 7 else "")
            wgroups += [(lab.replace("|", " пришло|"), Counter(r["cat"] for r in w["i"]), False),
                        (lab.replace("|", " решено|"), Counter(r["cat"] for r in w["s"]), False)]
        tbl = "".join(f'<tr><td>W{w["a"].isocalendar()[1]} · {w["a"]:%d.%m}–{(w["b"]-timedelta(days=1)):%d.%m}</td><td>{len(w["i"])}</td><td>{len(w["s"])}</td>'
                      f'<td>{len(w["j"])}</td><td class="{"bad" if w["dq"] > 0 else "ok"}">{w["dq"]:+d}</td><td>{c1(med([r["h"] for r in w["s"]]))}</td><td>{hsum(w["s"]):.0f}</td></tr>' for w in wk)
        row4 = panel("Динамика по неделям", stamps("in4", "sol4"),
                     f'{stack_svg([(g[0].replace(" пришло", " ▲").replace(" решено", " ▼"), g[1], g[2]) for g in wgroups], cats7, w=1100, h=240)}{legend(cats7)}'
                     f'<div class="tw"><table class="num"><thead><tr><th>Неделя</th><th>▲ Пришло</th><th>▼ Решено</th><th>✕ Отклонено</th><th>Очередь</th><th>Медиана, ч</th><th>Трудозатраты, ч</th></tr></thead><tbody>{tbl}</tbody></table></div>',
                     f"Пары столбцов: ▲ пришло и ▼ решено за неделю по типам. Последняя неделя — отчётный период {PER_S} (без выходных). Источник — та же выгрузка за 4 недели.",
                     "Тренд, а не один снимок: поток снижается, очередь тает — или наоборот. Смена состава типов видна раньше, чем рост очереди.")
        # строка 5 — по месяцам
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: шесть месяцев — до месяца отчётного периода, а не зашитые апрель–сентябрь 2026; месяцы до начала
        #               выгрузки — из истории недель v2 (поток по типам и месяцам), если она есть; подписи и сноска — по данным
        # ПОЧЕМУ: Т-18 — график «по имеющимся данным», дальше месяцы копятся из истории (data.md, разд. 6)
        # ----------------------------------------------------------------------
        mg_in, mg_sol, na = [], [], []
        first_res = R.first_res
        fm = (first_res.year, first_res.month)
        hist = defaultdict(lambda: {"in": Counter(), "sol": Counter()})
        for rec in R.history:
            for fld in ("in", "sol"):
                for mk, cnt in (rec.get(fld + "_m") or {}).items():
                    y_, m_ = map(int, mk.split("-"))
                    if (y_, m_) < fm:
                        hist[(y_, m_)][fld].update(cnt)
        for y, m in months:
            lab = f"{MON[m]}"
            # ----------------------------------------------------------------------
            # ЧТО ИЗМЕНЕНО: «полный» месяц — начиная с первого числа месяца, следующего за первым решением в выгрузке
            # ПОЧЕМУ: было «+32 дня от 1-го числа» — первое число сдвигалось на 2 сентября, и сентябрь ошибочно показывался как «н/д»
            # ----------------------------------------------------------------------
            full = datetime(y, m, 1) >= (datetime(first_res.year, first_res.month, 1) + timedelta(days=32)).replace(day=1)
            part = (y, m) == fm
            si = Counter(r["cat"] for r in rows if r["is_sol"] and r["done_dt"] and r["done_dt"].year == y and r["done_dt"].month == m)
            ci = Counter(r["cat"] for r in rows if r["reg_dt"].year == y and r["reg_dt"].month == m)
            if full or part:
                mg_in.append((lab + ("|неполный" if part else ""), ci, False))
                mg_sol.append((lab + (f"|с {first_res:%d.%m}" if part else ""), si, False))
            elif (y, m) in hist:
                mg_in.append((lab + "|по истории", dict(hist[(y, m)]["in"]), False))
                mg_sol.append((lab + "|по истории", dict(hist[(y, m)]["sol"]), False))
            else:
                mg_in.append((lab, {}, True)); mg_sol.append((lab, {}, True)); na.append(m)
        na_note = ""
        if na:
            nm = MON_FULL[na[0]].capitalize() + (f"–{MON_FULL[na[-1]]}" if len(na) > 1 else "")
            na_note = (f'<p class="na-note">{nm} — нет данных: выгрузка начинается с решений {first_res:%d.%m}. Полная картина — после разовой выгрузки за 6 месяцев; '
                       f'дальше месяцы копятся из истории недель.</p>')
        row5 = panel("Динамика по месяцам — последние 6 месяцев", stamps("in6", "sol6"),
                     f'<div class="grid g2"><div><div class="ch">▲ Пришло по месяцу регистрации</div>{stack_svg(mg_in, cats7)}</div>'
                     f'<div><div class="ch">▼ Решено по месяцу решения</div>{stack_svg(mg_sol, cats7)}</div></div>{legend(cats7)}' + na_note,
                     f"Те же разрезы, что по неделям, но по календарным месяцам. {MON_FULL[months[-1][1]].capitalize()} — до даты выгрузки.",
                     "Сезонность и долгий тренд: растёт ли доля инцидентов и НСИ от месяца к месяцу. Недели этого не показывают.")
        # строка 6 — что требует решения руководителя + контроль решений
        S = AI["slides"].get("s1") or {}
        dec = "".join(f'<tr><td><b>{E(d.get("problem", ""))}</b></td><td>{fmt(d.get("fact"))}<div class="ids">{tks(d.get("ids", []))}</div></td>'
                      f'<td><b>{fmt(d.get("act"))}</b></td><td>{E(d.get("who", ""))}</td><td>{fmt(d.get("eff"))}</td></tr>' for d in S.get("decisions", []))
        if not dec:
            dec = '<tr><td colspan="5" class="mut">Разбор ИИ недоступен — решения недели не сформированы.</td></tr>'
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: статус «выполнено» — зелёный (в макете любое слово с «не» внутри, и «выполнено» тоже, красилось красным);
        #               нет решений прошлой недели в истории — строка-пояснение; неделя в заголовке — по периоду, а не «макет W38»
        # ПОЧЕМУ: Т-52 — решения недели хранятся в истории и возвращаются в следующий отчёт; первый отчёт v5 — без них
        # ----------------------------------------------------------------------
        stc = lambda st: "bad" if st.startswith("не") else "ok" if st.startswith("выполн") else "warn"
        prev = "".join(f'<tr><td>{E(x.get("what", ""))}</td><td>{E(x.get("was", ""))}</td><td>{fmt(x.get("now"))}</td><td><span class="stt {stc(str(x.get("status", "")))}">{E(x.get("status", ""))}</span></td></tr>' for x in S.get("prev", []))
        if not prev:
            prev = ('<tr><td colspan="4" class="mut">Решений прошлой недели в истории нет. Решения этой недели сохраняются в истории '
                    'и будут проверены в следующем отчёте.</td></tr>')
        pw = (WS - timedelta(days=7)).isocalendar()[1]
        row6 = panel("Что требует решения руководителя", stamps("ai", "sol", "open"),
                     f'<div class="tw"><table class="dec"><thead><tr><th>Проблема</th><th>Факт и обращения</th><th>Действие</th><th>Кому</th><th>Эффект</th></tr></thead><tbody>{dec}</tbody></table></div>'
                     f'<h4 class="sub">Контроль решений прошлой недели</h4><div class="tw"><table><thead><tr><th>Что решили (W{pw})</th><th>Было</th><th>Сейчас</th><th>Статус</th></tr></thead><tbody>{prev}</tbody></table></div>',
                     "Пять решений недели по схеме «проблема — факт — действие — кому — эффект». Ручные правки считаются без НСИ. Ниже — что было решено на прошлой неделе и что из этого сдвинулось: решения сохраняются в истории и возвращаются в следующий отчёт (Т-52).",
                     "Совещание начинается с этого блока: не «что случилось», а что делаем и кто отвечает. Невыполненные решения не теряются — они висят здесь, пока не сдвинутся.")
        ra = "".join(f'<tr><td><b>{E(x.get("cause", ""))}</b></td><td>{tks(x.get("ids", []))}</td><td><b>{E(x.get("act", ""))}</b></td><td>{E(x.get("who", ""))}</td></tr>' for x in S.get("root_all", []))
        row7 = panel("Первопричины недели — все типы обращений", stamps("ai", "sol", "open"),
                     f'<div class="tw"><table class="ai"><thead><tr><th>Первопричина</th><th>Обращения</th><th>Что сделать</th><th>Кому</th></tr></thead><tbody>{ra}</tbody></table></div>',
                     "Корневые причины, которые ИИ видит сразу в нескольких обращениях разных типов — правках, консультациях, инцидентах (бывшие «Выводы ИИ» старого отчёта, Т-50).",
                     "Одна мера по первопричине снимает сразу группу обращений разных типов — это уровень решений руководителя, а не аналитика.")
        return (f'<article class="slide" id="s1"><div class="sh"><h2>Неделя {WEEK}: поток, скорость, решения</h2>'
                f'<p class="lead">Период {PER} ({rule}) · срез открытых на {NOW:%d.%m.%Y %H:%M} · выгрузка {len(raw)} строк</p></div>'
                + p0 + row1 + row2 + row3 + row4 + row5 + row6 + row7 + ai_block("s1") + "</article>")

    # ================================================================ СЛАЙД 11 — сроки и долгострой
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО: новый слайд «Долгострой» (бывшая таблица со слайда 1 + плитки, разрезы и разбор ИИ)
    # ПОЧЕМУ: Т-61 — долгострой раскрывает одноимённую плитку слайда 1, а не лежит под ней таблицей
    # ----------------------------------------------------------------------
    def slide11():
        lng = R.lng                      # ЧТО ИЗМЕНЕНО (v5): список и метрики долгостроя считаются в _metrics — для каталога ИИ
        n = len(lng)
        medl = lambda l: f'{med([r["h"] for r in l]) or 0:.0f} ч'
        tl = lambda l: f'{sum(r["trud"] for r in l):.0f} ч'
        top = (f'<div class="kpi">{stamps("sol")}<h4>Самый долгий</h4><div class="kpi-v">{M["lng_top_h"]}<span>раб. ч</span></div>'
               f'<div class="kpi-lines"><span><b>{M["lng_top_pct"]}%</b> всех часов долгостроя</span></div>'
               f'<div class="kpi-s">{tk(lng[0]["id"])} {E(lng[0]["ai"].get("s", ""))}</div></div>') if lng else \
              (f'<div class="kpi">{stamps("sol")}<h4>Самый долгий</h4><div class="kpi-v">—</div><div class="kpi-s">долгостроя за период нет</div></div>')
        k = [kpi("Долгострой, обращений", stamps("sol"), str(n), "из " + str(len(real)), str(sum(r["line"] == "L1" for r in lng)), str(sum(r["line"] == "L2" for r in lng)),
                 f"{M['lng_share']}% решённых; порог — {LONG_H} раб. ч от регистрации до решения"),
             kpi("Срок, медиана", stamps("sol"), f"{M['lng_med']:.0f}".replace(".", ",") if M["lng_med"] is not None else "—", "раб. ч",
                 medl([r for r in lng if r["line"] == "L1"]), medl([r for r in lng if r["line"] == "L2"]),
                 f"суммарно {M['lng_h']} раб. ч календарного срока"),
             kpi("Из них работа", stamps("sol"), str(M["lng_trud"]), "ч", tl([r for r in lng if r["line"] == "L1"]), tl([r for r in lng if r["line"] == "L2"]),
                 f"{M['lng_work_pct']}% срока — списанные трудозатраты (AmountTrud); остальное — ожидание"),
             top]
        p1 = ('<div class="grid g4">' + "".join(k) + "</div>"
              f'<p class="why rowwhy"><b>Что это.</b> Решённые за {PER_S} обращения, шедшие дольше {LONG_H} раб. ч (8 ч в рабочем дне, выходные и праздники не считаются); служебные карточки исключены. Мелко — первая и вторая линия.</p>'
              '<p class="use rowwhy"><b>Польза / проблема.</b> Сколько обращений «зависает» и как мало в этом времени работы: если работы единицы процентов — проблема в ожидании, а не в сложности.</p>')
        body = "".join(f'<tr><td>{tk(r["id"])}</td><td class="c"><b>{r["h"]:g}</b></td><td class="c">{r["trud"]:g}</td><td>{E(r["cat"])}</td><td>{E(r["sec"])}</td>'
                       f'<td>{"1-я" if r["line"] == "L1" else "2-я"}</td><td>{E(r["ai"].get("s", ""))}</td></tr>' for r in lng)
        p2 = panel(f"Все долгострои периода — {n}", stamps("sol", "ai"),
                   f'<div class="tw"><table><thead><tr><th>Обращение</th><th>Срок, раб. ч</th><th>Работа, ч</th><th>Тип</th><th>Раздел</th><th>Линия</th><th>Суть (ИИ)</th></tr></thead><tbody>{body}</tbody></table></div>',
                   f"Решённые за период, шедшие дольше {LONG_H} раб. ч, от самого долгого (бывший «Топ-10 самых длительных» приложения старого отчёта, Т-51). Дата и аналитик — в номере.",
                   "С этих строк начинается разбор: где ждали — у пользователя, в анализе или у разработки. Большой срок при малой работе — ожидание.")
        bt = Counter(r["cat"] for r in lng).most_common(); ba = Counter(short(r["anl"]) for r in lng).most_common(); bs = Counter(r["sec"] for r in lng).most_common(6)
        p3 = panel("Кто и что в долгострое", stamps("sol"),
                   f'<div class="grid g2"><div><div class="ch">По типу обращения</div>{hbars([(c, v, CAT_COLOR.get(c)) for c, v in bt])}</div>'
                   f'<div><div class="ch">По аналитику</div>{hbars([(a, v, "#3B4754") for a, v in ba])}</div></div>'
                   f'<div class="ch" style="margin-top:12px">По разделу (первые 6)</div>{hbars([(c, v, "#5D6B7A") for c, v in bs])}',
                   f"Те же {n} обращений в трёх разрезах: тип при регистрации, ответственный аналитик, раздел.",
                   "Концентрация — признак системной причины: один аналитик, один раздел или один тип (консультации не должны идти неделями).")
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: слайд расширен до «Сроки решения и долгострой»: распределение сроков всех решённых
        # ПОЧЕМУ: медиана прячет «два горба» — часть решается за час, часть идёт неделями (аудит 8а.4); слайд раскрывает плитки «Медиана», «За рабочий день», «Долгострой»
        # ----------------------------------------------------------------------
        B = [(0, 1, "≤ 1 ч", "#0F6E3A"), (1, 4, "1–4 ч", "#4E9A6B"), (4, FAST_H, f"4–{FAST_H} ч", "#8DBA9C"),
             (FAST_H, 24, f"{FAST_H}–24 ч", "#C9A227"), (24, LONG_H, f"24–{LONG_H} ч", "#D08700"), (LONG_H, 10**9, f"> {LONG_H} ч", "#B3261E")]
        cnt = [(lab, sum(a < r["h"] <= b or (a == 0 and r["h"] == 0) for r in real), col) for a, b, lab, col in B]
        p0 = panel("Распределение сроков решения", stamps("sol"),
                   hbars(cnt, unit=" обр.") + f'<p class="cmp">Медиана {c1(M["med_all"])} раб. ч; за рабочий день (≤ {FAST_H} ч) — {sum(c for _, c, _ in cnt[:3])}, долгострой (> {LONG_H} ч) — {cnt[-1][1]} из {len(real)}.</p>',
                   f"Все решённые за {PER_S} без служебных карточек, по сроку от регистрации до решения в рабочих часах (8 ч в рабочем дне, выходные не считаются).",
                   "Одна медиана прячет «два горба»: быстрые решения и хвост, который идёт неделями. Улучшать надо хвост — он и даёт недовольство.")
        return (f'<article class="slide" id="s11"><div class="sh"><h2>Сроки решения и долгострой</h2>'
                f'<p class="lead">Решено за {PER_S}: {len(real)} обращений без служебных; дольше {LONG_H} раб. ч — {n}</p></div>'
                + p0 + p1 + p2 + p3 + ai_block("s11") + "</article>")

    # ================================================================ СЛАЙД 2 — очередь
    def slide2():
        p1 = panel("Кто сейчас держит открытые обращения", stamps("open"), holder_rows(opn),
                   f"Все {len(opn)} открытых на {NOW:%d.%m}. Уточнение — ждём пользователя; ожидает анализа и анализ — поддержка; от планирования до проверки релиза — разработка. "
                   f"Статусы старой доски ({len(dropped)} шт.) отброшены при загрузке. Возраст — от даты регистрации.",
                   "Показывает, у кого мяч. Красная часть полосы — то, что висит больше трёх месяцев: с неё начинается разбор.")
        p_wait = ""
        ws = [r for r in sol if r["tab_status"]]
        if ws:
            hh = {r["id"]: holder_hours(r, NOW) for r in ws}
            tot = sum(sum(v.values()) for v in hh.values()) or 1
            body = ""
            for h in HOLDERS:
                vals = [v[h] for v in hh.values() if v[h] > 0]
                body += (f'<tr><th>{h}</th><td>{len(vals)}</td><td>{str(med(vals) or 0).replace(".", ",")}</td>'
                         f'<td><b>{pct(sum(vals), tot)}%</b></td><td><span class="hb-t" style="display:block;width:180px"><i style="width:{100*sum(vals)/tot:.0f}%;background:#5D86B0"></i></span></td></tr>')
            pingpong = [r["id"] for r in ws if sum(e[3] == "Уточнение" for e in r["tab_status"]) >= 2]
            auto = [r for r in ws if any(e[3] == "Закрыто" and e[1] == "Регламентное задание" for e in r["tab_status"])]
            closed = [r for r in ws if any(e[3] == "Закрыто" for e in r["tab_status"])]
            top = sorted(ws, key=lambda r: -hh[r["id"]]["Пользователь"])[:5]
            tt = "".join(f'<tr><td>{tk(r["id"])}</td><td class="c">{hh[r["id"]]["Пользователь"]:.0f}</td><td class="c">{hh[r["id"]]["Поддержка"]:.0f}</td><td class="c">{hh[r["id"]]["Разработка"]:.0f}</td></tr>' for r in top if hh[r["id"]]["Пользователь"] > 0)
            p_wait = panel("Где ждали решённые за период — по истории статусов", stamps("sol", "demo" if DEMO_TAB else "sol"),
                           f'<div class="grid g2"><div class="tw"><table class="num"><thead><tr><th>Держатель</th><th>Обращ.</th><th>Медиана, ч</th><th>Доля времени</th><th></th></tr></thead><tbody>{body}</tbody></table>'
                           f'<p class="cmp">Возвращали пользователю на уточнение дважды и больше: <b>{len(pingpong)}</b>. Закрыто автоматически: <b>{len(auto)}</b> из {len(closed)} закрытых.</p></div>'
                           f'<div><div class="ch">Дольше всего ждали пользователя, ч</div><div class="tw"><table class="num"><thead><tr><th>Обращение</th><th>Пользователь</th><th>Поддержка</th><th>Разработка</th></tr></thead><tbody>{tt}</tbody></table></div></div></div>',
                           f"Календарные часы в каждом статусе из табличной части tab_status для {len(ws)} решённых за период; держатель — по статусу (data.md, разд. 10).",
                           "Показывает, где на самом деле теряется время: у пользователя, в анализе или у разработки. Пинг-понг с уточнениями и автозакрытие видны по фактам, а не по догадке.",
                           "demo" if DEMO_TAB else "")
        # прогноз очереди (Т-52): по потоку 4 недель; разработка — по истории статусов, если она есть
        nets = [w["dq"] for w in wk]
        per_w = [7 / max(1, (w["b"] - w["a"]).days) for w in wk]          # неполная неделя — к 7 дням
        avg = sum(n * k for n, k in zip(nets, per_w)) / len(nets)
        fc = [len(opn) + round(avg * k) for k in range(1, 5)]
        dev_line = ""
        DEV = {"Планирование разработки", "Разработка", "Внутреннее тестирование", "Внутреннее тестирование на Предпроде", "Проверка релиза", "Релиз установлен"}
        if TAB_ON["tab_status"]:
            ins = outs = 0
            for r in rows:
                ev = sorted(r["tab_status"], key=lambda e: e[0])
                for k, e in enumerate(ev):
                    if e[0] < W4S: continue
                    prev_dev = k > 0 and ev[k - 1][3] in DEV
                    if e[3] in DEV and not prev_dev: ins += 1
                    if e[3] not in DEV and prev_dev: outs += 1
            wks = (WE - W4S).days / 7
            net = (ins - outs) / wks
            tail = sum(r["age"] > OLD_DAYS for r in dev)
            cc1 = lambda x: f"{x:.1f}".replace(".", ",")
            verdict = (f"хвост старше 30 дней ({tail}) при таком темпе выхода разберётся примерно за <b>{tail / (outs / wks):.0f} нед.</b>" if outs else "из разработки ничего не выходит — хвост не разберётся")
            dev_line = (f'<p class="cmp">Разработка: входит <b>{cc1(ins / wks)}</b> в неделю, выходит <b>{cc1(outs / wks)}</b> — очередь {"растёт" if net > 0 else "тает"} на {cc1(abs(net))} в неделю; {verdict}'
                        + (' <span class="stt warn">демо</span>' if DEMO_TAB else "") + "</p>")
        wrow = "".join(f'<td>{n:+d}</td>' for n in nets)
        p_fc = panel("Прогноз очереди", stamps("w4", "open"),
                     f'<div class="tw"><table class="num"><thead><tr><th></th>' + "".join(f'<th>W{w["a"].isocalendar()[1]}</th>' for w in wk) +
                     f'<th>Через 1 нед.</th><th>2</th><th>3</th><th>4</th></tr></thead><tbody><tr><th>Изменение очереди</th>{wrow}' +
                     "".join(f'<td class="mut">≈ {avg:+.0f}</td>' for _ in fc) + f'</tr><tr><th>Открыто</th><td colspan="{len(wk)}" class="mut">сейчас {len(opn)}</td>' +
                     "".join(f'<td><b>{v}</b></td>' for v in fc) + f'</tr></tbody></table></div>{dev_line}',
                     "Изменение очереди по неделям (пришло − решено − отклонено; неполная неделя пересчитана на 7 дней) и простая экстраполяция средним на 4 недели вперёд. Строка про разработку — по истории статусов (tab_status).",
                     "Отвечает на вопрос «справимся ли без изменений»: если очередь или хвост разработки не тает — нужны люди, приоритеты или отказ от части обращений.")
        # аналитик × держатель, старше 30 дней
        anl = sorted(set(r["anl"] for r in old), key=lambda a: (-sum(r["anl"] == a for r in old), a))
        body = ""
        for a in anl:
            cells = ""
            for h in HOLDERS:
                o = [r for r in old if r["anl"] == a and r["holder"] == h]
                cells += (f'<td>{len(o)}<small> · до {max(r["age"] for r in o)} дн</small></td>' if o else '<td class="mut">·</td>')
            o = [r for r in old if r["anl"] == a]
            z = sum(r["trud"] == 0 for r in o)
            body += f'<tr><th>{E(short(a))}</th>{cells}<td><b>{len(o)}</b></td><td>{hsum(o):.0f}</td><td class="{"bad" if z else "mut"}">{z or "·"}</td></tr>'
        p2 = panel("Кто и сколько держит — старше 30 дней", stamps("open"),
                   f'<div class="tw"><table class="num"><thead><tr><th>Аналитик</th>' + "".join(f"<th>{h}</th>" for h in HOLDERS) +
                   f'<th>Всего</th><th>Часов вложено</th><th>Из них 0 ч</th></tr></thead><tbody>{body}</tbody></table></div>',
                   f"{len(old)} открытых старше {OLD_DAYS} дней: у кого из аналитиков и на каком шаге висят; в ячейке — число и максимальный возраст. «0 ч» — по обращению не списано ни часа.",
                   "Кого спросить на разборе очереди и где «свалка»: много старых и ноль часов — за обращения никто не брался.")
        # до 30 дней: блок × статус (Т-49)
        young = [r for r in opn if r["age"] <= OLD_DAYS]
        sts = [s for s, _ in Counter(r["st"] for r in young).most_common()]
        secs = [s for s, _ in Counter(r["sec"] for r in young).most_common()]
        body = "".join(f'<tr><th>{E(s)}</th>' + "".join(f'<td>{sum(r["sec"] == s and r["st"] == t for r in young) or "·"}</td>' for t in sts) +
                       f'<td><b>{sum(r["sec"] == s for r in young)}</b></td></tr>' for s in secs)
        p3 = panel("Молодая очередь — до 30 дней: раздел × статус", stamps("open"),
                   f'<div class="tw"><table class="num heat"><thead><tr><th>Раздел</th>' + "".join(f"<th>{E(t)}</th>" for t in sts) + f'<th>Всего</th></tr></thead><tbody>{body}</tbody></table></div>',
                   f"{len(young)} открытых младше {OLD_DAYS} дней по разделу и текущему статусу.",
                   "Что ещё не стало хвостом, но может им стать: раздел, где копится «Уточнение» или «Планирование», завтра даст старые обращения.")
        # как сократить очередь
        grp_ = by([r for r in old if r["id"] in AIO], lambda r: AIO[r["id"]].get("ag"))
        body = ""
        for g in OPEN_ORDER:
            lst = grp_.get(g, [])
            if not lst: continue
            body += (f'<tr><td><b>{E(OPEN_ACTIONS[g])}</b></td><td class="c">{len(lst)}</td><td>{hsum(lst):.0f}</td>'
                     f'<td>{tks([r["id"] for r in sorted(lst, key=lambda r: -r["age"])])}</td></tr>')
        p4 = panel("Как сократить очередь — действия по старым обращениям", stamps("ai", "open"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Действие</th><th>Обращ.</th><th>Часов вложено</th><th>Обращения</th></tr></thead><tbody>{body}</tbody></table></div>',
                   f"ИИ разобрал каждое из {len(old)} обращений старше {OLD_DAYS} дней и предложил одно действие. Первые три строки не требуют разработки.",
                   f"Готовый план чистки: {M['quick_close']} карточек можно закрыть на этой неделе без разработки, остальные — со сроком или единой доработкой.")
        # полная таблица старше 30 дней по держателям
        body = ""
        for h in HOLDERS:
            lst = sorted([r for r in old if r["holder"] == h], key=lambda r: -r["age"])
            body += f'<tr class="grp"><th colspan="6">{h} — {len(lst)}</th></tr>'
            for r in lst:
                a = AIO.get(r["id"], {})
                body += (f'<tr><td>{tk(r["id"])}</td><td>{E(r["st"])}</td><td><span class="tt" style="--c:{CAT_COLOR.get(r["cat"], "#999")}">{E(r["cat"])}</span><br><small>{E(r["sec"])}</small></td>'
                         f'<td>{E(a.get("s", ""))}</td><td class="c">{r["trud"]:g}</td><td>{E(a.get("a", ""))}</td></tr>')
        p5 = panel(f"Все открытые старше {OLD_DAYS} дней — по держателю", stamps("open", "ai"),
                   f'<div class="tw"><table class="long"><thead><tr><th>Обращение</th><th>Статус</th><th>Тип · раздел</th><th>Суть (ИИ)</th><th>Часы</th><th>Предлагаемое действие (ИИ)</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Каждое старое обращение с датой, аналитиком, сутью и действием. Сортировка — от самого старого.",
                   "Рабочий список на разбор очереди: по каждой строке — решение «закрыть / объединить / срок / в релиз».")
        return (f'<article class="slide" id="s2"><div class="sh"><h2>Очередь на {NOW:%d.%m}: у кого мяч и как её сократить</h2>'
                f'<p class="lead">Открыто {len(opn)}: не решены и не отклонены на момент выгрузки; старше {OLD_DAYS} дней — {len(old)}</p></div>'
                + p1 + p_fc + p_wait + '<div class="grid g21">' + p2 + p3 + "</div>" + p4 + p5 + ai_block("s2") + "</article>")

    # ================================================================ СЛАЙД 3 — инциденты
    def spark(vals, color="#fff"):
        w, h = 120, 34; mx = max(vals + [1])
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: у мини-графика две тонкие линии — ноль и максимум, максимум подписан
        # ПОЧЕМУ: Т-58 — без линий и подписи не читалось значение точки
        # ----------------------------------------------------------------------
        grid = (f'<line x1="0" x2="{w}" y1="{h-5}" y2="{h-5}" stroke="{color}" stroke-opacity=".35" stroke-width="1"/>'
                f'<line x1="0" x2="{w}" y1="7" y2="7" stroke="{color}" stroke-opacity=".35" stroke-width="1"/>'
                f'<text x="{w}" y="6" text-anchor="end" font-size="9" fill="{color}" fill-opacity=".85">{mx}</text>')
        pts = " ".join(f"{6 + i * (w - 12) / (len(vals) - 1):.1f},{h - 5 - (h - 12) * v / mx:.1f}" for i, v in enumerate(vals))
        dots = "".join(f'<circle cx="{6 + i * (w - 12) / (len(vals) - 1):.1f}" cy="{h - 5 - (h - 12) * v / mx:.1f}" r="3" fill="{color}"><title>W{wk[i]["a"].isocalendar()[1]}: {v}</title></circle>' for i, v in enumerate(vals))
        return f'<svg class="spark" viewBox="0 0 {w} {h}">{grid}<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>{dots}</svg>'

    def slide3():
        I = lambda l: [r for r in l if r["type"] == "Инцидент"]
        in_w = [len(I(w["i"])) for w in wk]; sol_w = [len(I(w["s"])) for w in wk]
        ncrit_sol = sum(1 for r in sol if r["ai"].get("crit"))
        tiles = [("Открыто сейчас", M["inc_open"], f"на {NOW:%d.%m}", None, "open"),
                 ("Пришло за период", M["inc_in"], f"{WL}: " + " · ".join(map(str, in_w)), in_w, "in"),
                 ("Решено за период", M["inc_sol"], f"{WL}: " + " · ".join(map(str, sol_w)), sol_w, "sol"),
                 ("По сути инцидентов", M["inc_ai"], f"среди решённых — в {M['hidden_ratio']} раза больше зарегистрированных", None, "ai"),
                 ("Старше 30 дней", M["inc_old"], f"из них у разработки {M['inc_dev']}", None, "open"),
                 ("Критичные", ncrit_sol + len(OPEN_CRIT), f"ИИ: {len(OPEN_CRIT)} открыто · {ncrit_sol} решено", None, "ai")]
        t = "".join(f'<div class="itile t-{k}"><span>{E(a)}</span><b>{v}</b>{spark(sp) if sp else ""}<small>{E(n)}</small></div>' for a, v, n, sp, k in tiles)
        p1 = panel("Инциденты в цифрах", stamps("in", "sol", "open"), f'<div class="itiles">{t}</div>',
                   f"Тип «Инцидент» при регистрации; «по сути» — оценка ИИ по тексту решения. Линии — 4 недели {WL}.",
                   "Сколько сломалось, сколько починили и сколько дефектов прячется под другими типами — от этого зависит план разработки.", "inc-hero")
        # общая картина по разделам (4 недели)
        secs = sorted(set(r["sec"] for r in rows if r["type"] == "Инцидент" and (r["reg_dt"] >= W4S or r["is_open"])),
                      key=lambda s: (-sum(r["sec"] == s and r["type"] == "Инцидент" and r["is_open"] for r in rows), s))
        body = ""
        for s in secs:
            i4 = [r for r in rows if r["sec"] == s and r["type"] == "Инцидент" and r["reg_dt"] >= W4S]
            s4 = [r for r in rows if r["sec"] == s and r["type"] == "Инцидент" and r["is_sol"] and r["done_dt"] and r["done_dt"] >= W4S]
            o = [r for r in opn if r["sec"] == s and r["type"] == "Инцидент"]
            hid = sum(1 for r in sol if r["sec"] == s and r["type_ai"] == "Инцидент" and r["type"] != "Инцидент")
            body += (f'<tr><th>{E(s)}</th><td>{len(i4) or "·"}</td><td>{len(s4) or "·"}</td><td><b>{len(o) or "·"}</b></td>'
                     f'<td>{sum(r["age"] > OLD_DAYS for r in o) or "·"}</td><td class="{"warn" if hid else "mut"}">{hid or "·"}</td><td>{hsum(s4 + o):.0f}</td></tr>')
        p2 = panel("Общая картина: где ломается", stamps("w4", "open", "ai"),
                   f'<div class="tw"><table class="num"><thead><tr><th>Раздел</th><th>▲ Пришло 4 нед.</th><th>▼ Решено 4 нед.</th><th>● Открыто</th><th>из них &gt; 30 дн</th><th>Скрытые инциденты недели</th><th>Часы</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Инциденты по разделам: поток за 4 недели, открытые сейчас, скрытые (зарегистрированы другим типом, по сути — инцидент) и часы на решённые и открытые.",
                   "Раздел-лидер по открытым и скрытым инцидентам — кандидат в архитектурный разбор, а не в очередную заплатку.")
        # ось инцидентов за период
        ii = sorted([r for r in inc if r["type"] == "Инцидент"] + [r for r in sol if r["type_ai"] == "Инцидент" and r["type"] != "Инцидент" and in_per(r["reg_dt"])], key=lambda r: r["reg_dt"])
        w, h = 1100, 200; x0, x1 = 40, w - 20; span = (WE - WS).total_seconds()
        svg = [f'<svg class="chart" viewBox="0 0 {w} {h}"><line x1="{x0}" x2="{x1}" y1="95" y2="95" stroke="#3B4754" stroke-width="2"/>']
        for d in DAYS:
            x = x0 + (x1 - x0) * (d - WS).total_seconds() / span
            svg.append(f'<line x1="{x:.0f}" x2="{x:.0f}" y1="85" y2="105" stroke="#9AA6B2"/><text class="ax day" x="{x+6:.0f}" y="122">{WD[d.weekday()]} {d:%d.%m}</text>')
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: уровень подписи — первый свободный (не ближе 40 px к предыдущей на том же уровне); точка — ссылка, если есть url
        # ПОЧЕМУ: подписи 34989 и 34998 налезали друг на друга; Т-57 — номер открывает карточку
        # ----------------------------------------------------------------------
        levels, last = [(58, True), (140, False), (32, True), (166, False)], {}
        for k, r in enumerate(ii):
            x = x0 + (x1 - x0) * (r["reg_dt"] - WS).total_seconds() / span
            lv = next((L for L in levels if x - last.get(L, -1e9) >= 40), min(levels, key=lambda L: last.get(L, -1e9)))
            last[lv] = x; y, up = lv
            hidden = r["type"] != "Инцидент"
            crit = r.get("ai", {}).get("crit") or r["id"] in OPEN_CRIT
            fill = "#fff" if r["is_open"] else ("#B7800F" if hidden else "#D93025")
            a0, a1 = (f'<a href="{E(r["url"])}">', "</a>") if r.get("url") else ("", "")
            svg.append(f'<line x1="{x:.0f}" x2="{x:.0f}" y1="95" y2="{y:.0f}" stroke="#C3CCD5"/>'
                       f'{a0}<circle cx="{x:.0f}" cy="95" r="{9 if crit else 6}" fill="{fill}" stroke="{"#7A0F0A" if crit else "#D93025"}" stroke-width="{3 if crit else 2}"><title>{r["id"]} · {r["reg_dt"]:%d.%m %H:%M} · {E(r["st"])} · {E(short(r["anl"]))}</title></circle>{a1}'
                       f'<text class="lbl" x="{x+3:.0f}" y="{y - 4 if up else y + 12:.0f}">{r["id"][-5:]}</text>')
        svg.append("</svg>")
        lg = ('<div class="legend"><span><i style="background:#D93025"></i>инцидент решён</span><span><i style="background:#fff;border:2px solid #D93025"></i>открыт</span>'
              '<span><i style="background:#B7800F"></i>скрытый: зарегистрирован другим типом</span><span><i style="background:#D93025;border:3px solid #7A0F0A"></i>критичный</span></div>')
        p3 = panel("Ось инцидентов периода", stamps("in", "ai"), "".join(svg) + lg,
                   f"Все инциденты, зарегистрированные за {PER_S}, плюс скрытые (по сути — инцидент). Точка — момент регистрации, подпись — последние цифры номера.",
                   "Картинка недели: всплески в один день — массовый сбой, а не отдельные обращения.")
        crit = [r for r in sol if r["ai"].get("crit")]
        oc = sorted([BYID[i] for i in OPEN_CRIT], key=lambda r: r["reg_dt"])
        body = (f'<tr class="grp"><th colspan="4">Открытые — {len(oc)}</th></tr>' +
                "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["st"])}<br><small>{E(r["sec"])}</small></td><td>{E(OPEN_CRIT[r["id"]])}</td><td>{E(AIO.get(r["id"], {}).get("a", "Срок решения — на ближайший разбор"))}</td></tr>' for r in oc) +
                f'<tr class="grp"><th colspan="4">Решённые за период — {len(crit)}</th></tr>' +
                "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["st"])}<br><small>{E(r["sec"])}</small></td><td>{E(r["ai"].get("s", ""))}</td><td>{E(r["ai"].get("rec", ""))}</td></tr>' for r in crit))
        p4 = panel(f"Критичные — {len(oc) + len(crit)}", stamps("open", "sol", "ai"),
                   f'<div class="tw"><table><thead><tr><th>Обращение</th><th>Статус · раздел</th><th>Почему критично / что случилось</th><th>Что сделать</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Инциденты, которые ИИ отметил как критичные: остановка оплаты или процесса, налоговый и юридический риск, массовый пользователь. Открытые — без ограничения неделей, решённые — за период.",
                   "Критичное не должно теряться среди рядовых: открытое — срок сегодня, решённое — разбор причины, даже если «уже починили».")
        p5 = panel("Кто сейчас держит открытые инциденты", stamps("open"), holder_rows(inc_types),
                   f"{len(inc_types)} открытых инцидентов по держателю и возрасту.",
                   "Где застряли дефекты: у разработки — план, у поддержки — анализ, у пользователя — ждём ответа.")
        S = AI["slides"].get("s3") or {}
        body = "".join(f'<tr><td><b>{E(x.get("cause", ""))}</b></td><td>{tks(x.get("ids", []))}</td><td>{E(x.get("fix", ""))}</td><td><span class="tag">{E(x.get("kind", ""))}</span></td></tr>' for x in S.get("root", []))
        p6 = panel("Общие первопричины", stamps("ai", "sol", "open"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Первопричина</th><th>Обращения</th><th>Что закроет группу</th><th>Вид</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Несколько обращений — одна причина. ИИ собирает их по тексту решений; номера проверяет код.",
                   "Одна доработка вместо нескольких заплаток: этот список идёт в план разработки.")
        body = "".join(f'<tr><td>{tk(x.get("id", ""))}</td><td>{E(x.get("done", ""))}</td><td>{E(x.get("why", ""))}</td><td><span class="risk {"hi" if x.get("risk") == "высокий" else "md"}">{E(x.get("risk", ""))}</span></td></tr>' for x in S.get("notsolved", []))
        p7 = panel(f"Закрыто, но не решено — вернётся · из решённых {PER_S}, все типы", stamps("ai", "sol"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Обращение</th><th>Что сделали</th><th>Почему вернётся</th><th>Риск</th></tr></thead><tbody>{body}</tbody></table></div>',
                   f"Бывшие «Разовые заплатки» и «Альтернативное мнение ИИ» в одном блоке (Т-48): только обращения, решённые за {PER_S}, до 5 самых рискованных.",
                   "Проблема формально закрыта, причина осталась — через недели придёт такое же обращение. Эти решения надо вернуть или довести.")
        body = ""
        ff = []
        for x in S.get("fix_first", []):
            lst = [BYID[i] for i in x.get("ids", []) if i in BYID]
            ff.append((x, lst, hsum(lst)))
        for x, lst, hh in sorted(ff, key=lambda t: (-len(t[1]), -t[2])):
            body += (f'<tr><td><b>{E(x.get("name", ""))}</b></td><td class="c">{len(lst)}</td><td class="c">{sum(r["is_open"] for r in lst)}</td><td class="c">{hh:.0f}</td>'
                     f'<td>{E(x.get("act", ""))}</td><td>{tks(x.get("ids", []))}</td></tr>')
        p8 = panel("Что чинить первым", stamps("ai", "open", "w4"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Проблема</th><th>Обращ.</th><th>Открыто</th><th>Часов</th><th>Решение</th><th>Обращения</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Проблемы, по которым больше всего обращений всех типов (инциденты, правки, консультации) — решённых и открытых — и часов на них. Сортировка по числу обращений.",
                   "Ответ на вопрос «какой инцидент сделать первым»: одна доработка снимает сразу несколько обращений и часы поддержки.")
        return (f'<article class="slide" id="s3"><div class="sh"><h2>Инциденты: что сломалось и что вернётся</h2>'
                f'<p class="lead">Период {PER}; открытые — на {NOW:%d.%m}; разборы ИИ — по решённым за период и открытым</p></div>'
                + p1 + '<div class="grid g21">' + p2 + p5 + "</div>" + p3 + p4 + p6 + p7 + p8 + ai_block("s3") + "</article>")

    # ================================================================ СЛАЙД 4 — ручные правки и НСИ
    def slide4():
        prs = [r for r in sol if r["cat"] == "Правка данных"]
        pr_open = [r for r in opn if r["cat"] == "Правка данных"]
        sc = (f'<div class="big-claim"><div class="bc-n">{pct(len(prs), len(real))}<span>%</span></div><div class="bc-t"><b>решённого за период — ручные правки данных без НСИ</b><br>'
              f'{len(prs)} из {len(real)} · {hsum(prs):.0f} ч · медиана {c1(med([r["h"] for r in prs]))} раб. ч · ещё {len(pr_open)} открыто · '
              f'{len(set(r["cli"] for r in prs))} разных инициаторов<br><span class="nsi-chip">НСИ отдельно: {M["nsi_n"]} решено · медиана {c1(M["nsi_med"])} ч · {hsum(nsi):.0f} ч</span></div></div>')
        p1 = panel("Масштаб", stamps("sol", "open"), sc,
                   "Тип «Изменение данных в системе» вне раздела «Нормализация». НСИ (весь раздел «Нормализация») — отдельной плашкой и отдельным блоком ниже.",
                   "Самый большой поток и самый дешёвый для устранения: каждая повторяющаяся правка — кандидат на права, проверку при вводе или доработку.", "hero")
        # почему правим — таблица с обоснованием (Т-28)
        wg = by([r for r in prs if r["ai"].get("why")], lambda r: r["ai"]["why"])
        body = ""
        for k, lst in sorted(wg.items(), key=lambda kv: -len(kv[1])):
            act, who = WHY_ACT.get(k, ("", ""))
            args = "; ".join(sorted(set(r["ai"].get("wa") or "" for r in lst) - {""})[:3])
            body += (f'<tr><td><b>{E(k)}</b></td><td class="c">{len(lst)}</td><td class="c">{hsum(lst):.1f}</td><td>{E(args)}</td>'
                     f'<td>{tks([r["id"] for r in lst][:4])}{"<small class=mut> + ещё " + str(len(lst)-4) + "</small>" if len(lst) > 4 else ""}</td><td><b>{E(act)}</b></td><td>{E(who)}</td></tr>')
        p2 = panel("Почему правим — с обоснованием", stamps("ai", "sol"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Причина</th><th>Обращ.</th><th>Часы</th><th>Обоснование ИИ</th><th>Примеры</th><th>Что сделать</th><th>Кому</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "ИИ определил причину по тексту обращения и решения и записал, на что опирался. Причина ≠ формулировка просьбы: «поправьте» бывает и дефектом, и нехваткой прав.",
                   "Каждая строка — отдельное управленческое действие: права — владельцу процесса, дефект — разработке, ошибки — руководителю подразделения.")
        # правки, которые на самом деле дефекты
        dfc = [r for r in prs if r["type_ai"] == "Инцидент" or r["ai"].get("why") == "дефект системы"]
        body = "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["sec"])}</td><td>{E(r["ai"].get("s", ""))}</td><td>{E(r["ai"].get("wa") or r["ai"].get("ta", ""))}</td><td>{E(r["ai"].get("rec", ""))}</td></tr>' for r in dfc)
        p3 = panel(f"Правки, которые на самом деле дефекты — {len(dfc)}", stamps("ai", "sol"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Обращение</th><th>Раздел</th><th>Что поправили</th><th>Почему это дефект</th><th>Что сделать</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Правки, где по решению видно дефект системы: данные исправили руками, а механизм, который их испортил, остался.",
                   "Эти строки — в план разработки. Пока их правят руками, они раздувают поток правок и не видны как дефекты.")
        # кто просит · кто делает · мог бы сам
        cli = Counter(r["cli"] for r in prs).most_common(8)
        anl = Counter(r["anl"] for r in prs).most_common(8)
        ssl = [r for r in sol if r["ai"].get("ss")]
        body = "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["cli"])}</td><td>{E(r["ai"].get("s", ""))}</td><td>{E(r["ai"].get("rec") or "Право или инструкция")}</td></tr>' for r in ssl)
        p4 = panel("Кто просит · кто делает", stamps("sol"),
                   f'<div class="grid g2"><div><div class="ch">Инициаторы</div>{hbars([(c, n, "#5D6B7A") for c, n in cli])}</div>'
                   f'<div><div class="ch">Исполнители</div>{hbars([(short(a) + (" · 1-я линия" if a.startswith(L1_ANALYST) else ""), n, "#3B4754") for a, n in anl])}</div></div>',
                   "Инициаторы и исполнители ручных правок за период (без НСИ).",
                   "Слева — кому нужны права или обучение: у кого правки повторяются. Справа — нагрузка правками по людям.")
        p5 = panel(f"Мог бы сделать сам — {len(ssl)}", stamps("ai", "sol"),
                   f'<div class="tw"><table><thead><tr><th>Обращение</th><th>Инициатор</th><th>Что просил</th><th>Что нужно, чтобы сам</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Решённые обращения всех типов, которые пользователь сделал бы сам при наличии права или инструкции (оценка ИИ).",
                   "Shift-left: каждая строка — обращение, которого могло не быть. Право или памятка снимают поток навсегда.")
        p6 = panel("Кто сейчас держит открытые правки", stamps("open"), holder_rows(pr_open),
                   f"{len(pr_open)} открытых правок данных (без НСИ) по держателю и возрасту.",
                   "Правка не должна висеть неделями: старая открытая правка — признак, что за ней стоит дефект или спор.")
        # НСИ отдельно
        nsi_obj = Counter(str(r["ai"].get("obj") or r["ai"].get("s") or "без разметки ИИ").split(":")[0] for r in nsi).most_common()
        S = AI["slides"].get("s4") or {}
        ne = "".join(f'<tr><td>{tk(x.get("id", ""))}</td><td>{E(BYID.get(x.get("id"), {}).get("type", ""))}</td><td><b>{E(x.get("cls", ""))}</b></td><td>{E(x.get("note", ""))}</td></tr>' for x in S.get("nsi_nonedit", []))
        p7 = panel(f"НСИ отдельно — {M['nsi_n']} решено за период", stamps("sol", "sol4", "ai"),
                   f'<div><div><div class="ch">Что правят в НСИ</div>{hbars([(k, n, CAT_COLOR["НСИ"]) for k, n in nsi_obj])}'
                   f'<p class="cmp">Медиана {c1(M["nsi_med"])} раб. ч, {hsum(nsi):.1f} ч за период; ведёт первая линия — {sum(r["line"] == "L1" for r in nsi)} из {len(nsi)}.</p></div>'
                   f'<div><div class="ch" style="margin-top:14px">Не-правки в НСИ за 4 недели — классификация ИИ</div><div class="tw"><table><thead><tr><th>Обращение</th><th>Тип при регистрации</th><th>Что это по сути</th><th>Комментарий</th></tr></thead><tbody>{ne}</tbody></table></div></div></div>',
                   "НСИ — раздел «Нормализация» целиком. Слева — что правят за период, справа — всё, что в НСИ зарегистрировано не правкой, с классификацией ИИ.",
                   "НСИ дёшева по часам, но это постоянный поток — место для самообслуживания. Инциденты в НСИ — либо бардак в разделе, либо реальный сбой справочника: оба случая требуют разбора.")
        return (f'<article class="slide" id="s4"><div class="sh"><h2>Ручные правки данных: что, почему, кто — и отдельно НСИ</h2>'
                f'<p class="lead">Решённые за {PER}, если не сказано иное. Правки — без НСИ</p></div>'
                + p1 + p2 + p3 + '<div class="grid g2">' + p4 + p6 + "</div>" + p5 + p7 + ai_block("s4") + "</article>")

    # ================================================================ СЛАЙД 5 — повторы
    def slide5():
        body = ""
        for n, (g, lst) in enumerate(top7, 1):
            secs = Counter(r["sec"] for r in lst).most_common()
            sec = secs[0][0] + (f" +{len(secs)-1}" if len(secs) > 1 else "")
            is_nsi = sum(r["cat"] == "НСИ" for r in lst) > len(lst) / 2
            inc_sh = pct(sum(r["type_ai"] == "Инцидент" for r in lst), len(lst))
            gr = Counter(r["ai"].get("gr") for r in lst).most_common(1)[0][0]
            rec = next((r["ai"]["rec"] for r in lst if r["ai"].get("rec")), "—")
            clis = Counter(r["cli"] for r in lst).most_common(1)[0]
            body += (f'<tr class="{"nsi" if is_nsi else ""}"><td class="c rank">{n}</td><td><b>{E(g)}</b>{"<span class=nsi-tag>НСИ</span>" if is_nsi else ""}'
                     f'<br><small class="mut">{E("; ".join(r["ai"].get("s", "") for r in lst[:2]))}</small></td><td>{E(sec)}</td><td class="c"><b>{len(lst)}</b></td>'
                     f'<td class="c">{hsum(lst):.1f}</td><td class="c {"bad" if inc_sh >= 50 else ""}">{inc_sh}%</td><td>{GRADE.get(gr, "—")}</td>'
                     f'<td>{E(short(clis[0]))} · {clis[1]}</td><td>{E(rec)}</td><td>{tks([r["id"] for r in lst][:3])}{"<small class=mut> +" + str(len(lst)-3) + "</small>" if len(lst) > 3 else ""}</td></tr>')
        p1 = panel("Топ-7 точечных проблем", stamps("sol", "ai"),
                   f'<div class="tw"><table class="ai"><thead><tr><th style="width:28px">#</th><th>Проблема</th><th>Раздел</th><th>Обращ.</th><th>Часы</th><th>Инцидентов по сути</th><th>Качество</th><th>Главный инициатор</th><th>Как снять поток</th><th>Обращения</th></tr></thead><tbody>{body}</tbody></table></div>',
                   f"Группы тем решённых за {PER_S}: ИИ сводит разные формулировки одной проблемы. Семь строк, чтобы НСИ входила в топ, но не вытесняла остальные (Т-44); строки НСИ помечены.",
                   f"Одна мера — минус N обращений в неделю. Из 7 групп {M['top7_nsi']} — НСИ: это не проблема качества, но постоянное место для оптимизации.")
        # кто приносит повторы
        cg = by([r for r in sol if r["ai"].get("g")], lambda r: r["cli"])
        reps = sorted([(c, l) for c, l in cg.items() if len(l) >= 3], key=lambda t: -len(t[1]))
        body = ""
        for c, l in reps:
            gc = Counter(r["ai"]["g"] for r in l).most_common(1)[0]
            kinds = Counter(r["ai"].get("why") or TYPE_SHORT.get(r["type_ai"], r["type_ai"]) for r in l).most_common(1)[0][0]
            body += f'<tr><td><b>{E(c)}</b></td><td class="c">{len(l)}</td><td>{E(gc[0])} — {gc[1]}</td><td>{E(kinds)}</td><td>{tks([r["id"] for r in l][:3])}</td></tr>'
        p2 = panel("Кто приносит повторы", stamps("sol", "ai"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Инициатор</th><th>Обращ.</th><th>Что повторяется</th><th>Главная причина</th><th>Обращения</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Инициаторы с тремя и более решёнными обращениями за период; тема — по группе ИИ, а не по точному тексту.",
                   "Повтор от одного человека — это право, инструкция или дефект в его участке. Точечное решение для одного человека снимает весь его поток.")
        # скрытые повторы — эмоции и маркеры (Т-42)
        body = "".join(f'<tr><td>{tk(x["id"])}</td><td>«{E(x.get("q", ""))}»</td><td><span class="tag">{E(x.get("k", ""))}</span></td><td>{E(x.get("a", ""))}</td></tr>' for x in AI["signals"])
        p3 = panel("Скрытые повторы: что пишут пользователи", stamps("in", "sol", "ai"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Обращение</th><th>Цитата</th><th>Сигнал</th><th>Вывод ИИ</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Эмоциональный фон и маркеры «опять», «снова», «уже писал», «вновь» в обращениях периода. ИИ ищет, к какому прошлому обращению относится повтор.",
                   "Раздражение пользователя часто показывает то, чего не видно в данных: проблема не первая, а исправление не помогло. Здесь такие случаи видны сразу.")
        # тепловая карта раздел × неделя
        secs = [s for s, _ in Counter(r["sec"] for r in rows if r["reg_dt"] >= W4S).most_common(12)]
        mx = max([sum(1 for r in w["i"] if r["sec"] == s) for s in secs for w in wk] + [1])
        body = ""
        for s in secs:
            vals = [sum(1 for r in w["i"] if r["sec"] == s) for w in wk]
            body += f'<tr><th>{E(s)}</th>' + "".join(
                f'<td style="background:rgba(29,51,80,{0.08 + 0.8 * v / mx:.2f});color:{"#fff" if v / mx > 0.5 else "var(--ink)"}">{v}</td>' for v in vals) + \
                f'<td class="{"bad" if vals[-1] > vals[0] else "ok"}">{vals[-1] - vals[0]:+d}</td></tr>'
        p4 = panel("Где растёт поток: раздел × неделя", stamps("in4"),
                   f'<div class="tw"><table class="num heat"><thead><tr><th>Раздел</th>' + "".join(f'<th>W{w["a"].isocalendar()[1]}</th>' for w in wk) +
                   f'<th>Изменение</th></tr></thead><tbody>{body}</tbody></table></div>',
                   f"Пришедшие по разделу за 4 недели (W{wk[-1]['a'].isocalendar()[1]} — отчётный период без выходных). Темнее — больше.",
                   "Раздел, где поток растёт, — первым на разбор: рост почти всегда означает новый дефект или релиз.")
        return (f'<article class="slide" id="s5"><div class="sh"><h2>Повторы: что придёт снова</h2>'
                f'<p class="lead">Группы тем ИИ по решённым за {PER}; поток по разделам — 4 недели</p></div>'
                + p1 + p3 + p2 + p4 + ai_block("s5") + "</article>")

    # ================================================================ СЛАЙД 6 — качество и классификация
    def slide6():
        g = Counter(r["ai"].get("gr") for r in sol_ai)
        tot = sum(g.values())
        tw_ = tot or 1                   # ЧТО ИЗМЕНЕНО: нет размеченных (сбой ИИ) — пустая полоса, а не деление на ноль
        bar = (f'<div class="gbar"><i class="g-ex" style="width:{100*g["О"]/tw_:.1f}%"></i><i class="g-ok" style="width:{100*g["Х"]/tw_:.1f}%"></i><i class="g-bad" style="width:{100*g["П"]/tw_:.1f}%"></i></div>'
               f'<div class="glab"><span><b>{g["О"]}</b> Отлично — устранена причина или сделан шаг против повтора</span><span><b>{g["Х"]}</b> Хорошо — причина названа, проблема закрыта</span>'
               f'<span><b class="bad">{g["П"]}</b> Плохо — отписка, причина не названа, ответ не на вопрос</span></div>')
        bad = [r for r in sol_ai if r["ai"].get("gr") == "П"]
        body = "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["sec"])}</td><td>{E(r["ai"].get("s", ""))}</td><td>{E(r["ai"].get("ga", ""))}</td><td><b>{E(r["ai"].get("rec") or "Переделать решение")}</b></td></tr>' for r in bad)
        p1 = panel(f"Оценка решений и все «Плохо» — на переделку ({len(bad)})", stamps("ai", "sol"),
                   bar + f'<div class="tw"><table class="ai"><thead><tr><th>Обращение</th><th>Раздел</th><th>Суть</th><th>Что не так</th><th>Что переделать</th></tr></thead><tbody>{body}</tbody></table></div>',
                   f"Оценка ИИ по ужесточённым критериям для {tot} решённых (служебные карточки исключены). Показаны все «Плохо», без обрезки.",
                   "Список возврата на переделку: по каждой строке — аналитик и что именно исправить. Доля «Плохо» — главный показатель качества недели.")
        S = AI["slides"].get("s6") or {}
        body = "".join(f'<tr><td>{tk(x.get("id", ""))}</td><td>{E(BYID.get(x.get("id"), {}).get("ai", {}).get("s", ""))}</td><td>{E(x.get("why", ""))}</td><td><b>{E(x.get("kb", ""))}</b></td></tr>' for x in S.get("best", []))
        p2 = panel("Лучшие решения — что тиражировать", stamps("ai", "sol"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Обращение</th><th>Суть</th><th>Почему эталон</th><th>Что внести в базу знаний</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Пять решений, где устранена причина или пользователю дан инструмент (Т-47).",
                   "Эталон для команды и пополнение базы знаний: одна статья — меньше обращений на эту тему.")
        # указан → по сути
        TT = ["Изменение данных в системе", "Консультация", "Инцидент", "Права доступа", "Дубль"]
        head = "".join(f"<th>{TYPE_SHORT[t]}</th>" for t in TT)
        body = ""
        for t in TT:
            cells = ""
            for u in TT:
                n = sum(1 for r in sol_ai if r["type"] == t and r["type_ai"] == u)
                cls = "diag" if t == u else ("hot" if n else "")
                st = f' style="background:rgba(217,48,37,{0.25 + 0.6 * min(n, 10) / 10:.2f})"' if cls == "hot" else ""
                cells += f'<td class="{cls}"{st}>{n or "·"}</td>'
            body += f'<tr><th>{TYPE_SHORT[t]}</th>{cells}<td><b>{sum(1 for r in sol_ai if r["type"] == t)}</b></td></tr>'
        body += '<tr class="tot"><th>Итого по сути</th>' + "".join(f'<td>{sum(1 for r in sol_ai if r["type_ai"] == u)}</td>' for u in TT) + f"<td>{len(sol_ai)}</td></tr>"
        # расшифровка ячеек
        TS = lambda t: TYPE_SHORT.get(t, t)
        cells = by(mis, lambda r: (TS(r["type"]), TS(r["type_ai"])))
        dec = "".join(f'<tr><td><b>{a} → {b}</b></td><td class="c">{len(l)}</td><td>{E(CONSEQ.get((a, b), ""))}</td><td>{E(l[0]["ai"].get("ta", ""))}</td><td>{tks([r["id"] for r in l][:4])}</td></tr>'
                      for (a, b), l in sorted(cells.items(), key=lambda kv: -len(kv[1])))
        p3 = panel("Как тип указан и какой он на самом деле", stamps("ai", "sol"),
                   f'<div><div class="tw"><table class="num heat" style="max-width:760px"><thead><tr><th>Указан ↓ · по сути →</th>{head}<th>Всего</th></tr></thead><tbody>{body}</tbody></table>'
                   f'<p class="cmp">Неверный тип у <b>{len(mis)}</b> из {len(sol_ai)} ({M["mis_pct"]}%). По сути инцидентов {M["inc_ai"]}, зарегистрировано {M["inc_sol"]}.</p></div>'
                   f'<div class="tw" style="margin-top:14px"><table class="ai"><thead><tr><th>Ошибка</th><th>Обращ.</th><th>Последствие</th><th>Пример аргумента ИИ</th><th>Обращения</th></tr></thead><tbody>{dec}</tbody></table></div></div>',
                   "Строки — тип при регистрации, колонки — тип по сути по тексту решения. Справа — расшифровка каждой ошибки: сколько, чем опасна, на что опирался ИИ.",
                   "Неверный тип искажает статистику и SLA: дефекты прячутся под правками и консультациями и не попадают в план разработки.")
        # кто ошибается в типе
        am = by(sol_ai, lambda r: r["anl"])
        body = ""
        for a, l in sorted(am.items(), key=lambda kv: -sum(r in mis for r in kv[1])):
            m_ = [r for r in l if r in mis]
            if not m_: continue
            top = Counter((TS(r["type"]), TS(r["type_ai"])) for r in m_).most_common(1)[0][0]
            body += (f'<tr><td><b>{E(short(a))}</b></td><td class="c">{len(l)}</td><td class="c {"bad" if pct(len(m_), len(l)) >= 25 else ""}">{len(m_)} · {pct(len(m_), len(l))}%</td>'
                     f'<td>{top[0]} → {top[1]}</td><td>{tks([r["id"] for r in m_][:4])}</td></tr>')
        p4 = panel("Кто ошибается в типе — кого поправить", stamps("ai", "sol"),
                   f'<div class="tw"><table class="ai"><thead><tr><th>Аналитик</th><th>Решено</th><th>Неверный тип</th><th>Типичная путаница</th><th>Обращения</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Аналитики, у которых тип при регистрации не совпал с сутью; красным — четверть и больше.",
                   "Конкретно: с кем разобрать типы и на каких примерах. Общая доля ошибок этого не показывает.")
        # эмоциональный фон и служебные
        emo = [r for r in sol if _num(r["ai"].get("tone")) > 0]
        body = "".join(f'<tr><td>{tk(r["id"])}</td><td class="c">{r["ai"]["tone"]}</td><td>{E(r["ai"].get("ea", ""))}</td><td>{E(r["ai"].get("s", ""))}</td></tr>' for r in emo)
        p5 = panel(f"Эмоциональный фон — {len(emo)}", stamps("ai", "sol"),
                   f'<div class="tw"><table><thead><tr><th>Обращение</th><th>Уровень 0–3</th><th>Сигнал</th><th>Суть</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Отклонение от делового тона в решённых за период: 1 — скрытое недовольство, 2 — давление, 3 — грубость.",
                   "Раздражение — ранний сигнал повтора и эскалации: оценок пользователей в выгрузке нет, и тон письма — единственная обратная связь.")
        svc = [r for r in sol if r["cat"] == "Служебное"]
        body = "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["ai"].get("s", "") or r["desc"][:90])}</td><td class="c">{r["trud"]:g}</td><td>{E(r["ai"].get("rec", ""))}</td></tr>' for r in svc)
        p6 = panel(f"Служебные карточки в потоке обращений — {len(svc)}", stamps("ai", "sol"),
                   f'<div class="tw"><table><thead><tr><th>Обращение</th><th>Что это</th><th>Часы</th><th>Что сделать</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Карточки, которые не являются обращениями пользователей: списание времени на встречи, внутренние поручения.",
                   f"Они дают {M['svc_pct']}% часов недели и портят медианы и цену обращений — из статистики их надо выводить.")
        return (f'<article class="slide" id="s6"><div class="sh"><h2>Качество решений и классификации</h2>'
                f'<p class="lead">Оценки и тип «по сути» — ИИ по тексту решения; решённые за {PER}</p></div>'
                + p1 + p3 + p4 + p2 + p5 + p6 + ai_block("s6") + "</article>")

    # ================================================================ СЛАЙД 7 — планшеты (Т-41)
    def slide7():
        lead = f'<div class="sh"><h2>Планшеты: как идёт внедрение</h2><p class="lead">4 недели {W4S:%d.%m}–{PER_S[-5:]} и все открытые на {NOW:%d.%m}</p></div>'
        if not pl:
            return (f'<article class="slide" id="s7">{lead}' + panel("Внедрение планшетов", stamps("w4", "open"), '<p class="cmp">Обращений со словом «планшет» за 4 недели и открытых нет.</p>',
                    "Все обращения со словом «планшет» за 4 недели и все открытые.", "Внедрение на контроле руководства: пустой слайд — хороший знак.") + ai_block("s7") + "</article>")
        kinds = Counter(r["pl_kind"] for r in pl)
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: причины — постоянный список PL_KINDS; «Массовый сбой» показывается с датой, которую поставила модель
        # ПОЧЕМУ: в макете цвета и порядок были написаны под «Массовый сбой 02.09»
        # ----------------------------------------------------------------------
        labels = []
        for base in PL_KINDS:
            labels += sorted(k for k in kinds if pl_kind_base(k) == base) or [base]
        labels += sorted(k for k in kinds if k not in labels)
        KC = {k: PL_COLOR.get(pl_kind_base(k), "#5D6B7A") for k in labels}
        colors = dict(CAT_COLOR, **KC)
        wg = []
        for w in wk:
            c = Counter(r["pl_kind"] for r in pl if in_per(r["reg_dt"], w["a"], w["b"]))
            wg.append((f'W{w["a"].isocalendar()[1]}|{w["a"]:%d.%m}', c, False))
        old_c = Counter(r["pl_kind"] for r in pl if r["reg_dt"] < W4S)
        chart = stack_svg(wg, list(KC), w=520, h=220, colors=colors)
        st = [("Открыто", M["pl_open"]), ("Решено", sum(r["is_sol"] for r in pl)), ("Отклонено", M["pl_rej"])]
        places = Counter()
        for r in pl:
            t = r["desc"]
            for lab, rx in PL_PLACES:
                if re.search(rx, t, re.I): places[lab] += 1
        devs = [(f"планшет {k}", v, "#B3261E" if v >= 3 else "#5D6B7A") for k, v in R.devices.most_common(8) if v >= 2]
        p1 = panel("Внедрение планшетов: поток и причины", stamps("w4", "open"),
                   f'<div class="grid g2"><div><div class="ch">Обращения по неделям и причинам</div>{chart}{legend(list(KC), colors)}</div>'
                   f'<div><div class="ch">Причины за 4 недели</div>{hbars([(k, v, KC.get(k)) for k, v in kinds.most_common()])}'
                   f'<div class="strip3">' + "".join(f"<div><b>{v}</b><span>{k}</span></div>" for k, v in st) + '</div>'
                   f'<p class="cmp">Ещё {sum(old_c.values())} открытых зарегистрированы до {W4S:%d.%m} — самое старое с {min(r["reg_dt"] for r in pl):%d.%m.%Y}.</p></div></div>',
                   "Все обращения со словом «планшет» за 4 недели и все открытые; причина — по тексту обращения и решения.",
                   "Внедрение на контроле руководства: видно, падает ли поток и какая причина главная — вход, зависания, связь или массовые сбои.")
        p2 = panel("Где и на каких устройствах", stamps("w4"),
                   f'<div class="grid g2"><div><div class="ch">Места</div>{hbars([(k, v, "#3B4754") for k, v in places.most_common()])}</div>'
                   f'<div><div class="ch">Повторы по одному устройству</div>{hbars(devs)}</div></div>',
                   "Место и номер планшета — из текста обращения (терминал, ремзона, линейка, ID).",
                   "Устройство с тремя и более обращениями — на замену; место с проблемами связи — на карту покрытия.")
        op_ = sorted([r for r in pl if r["is_open"]], key=lambda r: r["reg_dt"])
        body = "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["st"])}</td><td><span class="tt" style="--c:{KC.get(r["pl_kind"], "#5D6B7A")}">{E(r["pl_kind"])}</span></td><td>{E(re.sub(chr(10), " ", r["desc"])[:140])}</td></tr>' for r in op_)
        p3 = panel(f"Открытые по планшетам — {len(op_)}", stamps("open"),
                   f'<div class="tw"><table><thead><tr><th>Обращение</th><th>Статус</th><th>Причина</th><th>Описание</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Все открытые обращения по планшетам, от самого старого.",
                   "Что висит у полевых сотрудников прямо сейчас: каждое — простой инженера на перроне или в ремзоне.")
        return f'<article class="slide" id="s7">{lead}' + p1 + p2 + p3 + ai_block("s7") + "</article>"

    # ================================================================ СЛАЙД 8 — цена в часах (Т-53)
    def slide8():
        s4 = [r for r in rows if r["is_sol"] and r["done_dt"] and r["done_dt"] >= W4S and r["cat"] != "Служебное"]
        secs = by(s4, lambda r: r["sec"])
        items = sorted(((s, hsum(l), len(l)) for s, l in secs.items()), key=lambda t: -t[1])[:12]
        t1 = "".join(f'<tr><th>{E(s)}</th><td>{h:.0f}</td><td>{n}</td><td>{str(round(h / n, 1)).replace(".", ",")}</td></tr>' for s, h, n in items)
        cats = by(s4, lambda r: r["cat"])
        tot_h, tot_n = hsum(s4), len(s4)
        th_ = tot_h or 1                 # ЧТО ИЗМЕНЕНО: часы не списаны совсем — без деления на ноль
        t2 = "".join(f'<div class="pp"><span style="--c:{CAT_COLOR.get(c, "#999")}">{c}</span><div class="pp-b"><i style="width:{100*len(l)/tot_n:.0f}%;background:{CAT_COLOR.get(c, "#999")}66"></i><em>{pct(len(l), tot_n)}% обращений</em></div>'
                     f'<div class="pp-b"><i style="width:{100*hsum(l)/th_:.0f}%;background:{CAT_COLOR.get(c, "#999")}"></i><em>{pct(hsum(l), tot_h)}% часов</em></div></div>'
                     for c, l in sorted(cats.items(), key=lambda kv: -hsum(kv[1])))
        p1 = panel("Цена по разделам и типам — 4 недели", stamps("sol4"),
                   f'<div class="grid g2"><div class="tw"><table class="num"><thead><tr><th>Раздел</th><th>Часов</th><th>Обращ.</th><th>Ч на обращ.</th></tr></thead><tbody>{t1}</tbody></table></div>'
                   f'<div><div class="ch">Доля в обращениях и в часах</div>{t2}</div></div>',
                   f"Трудозатраты (AmountTrud) по решённым за 4 недели, {tot_h:.0f} ч на {tot_n} обращений; служебные карточки исключены.",
                   "Куда уходит время команды. Тип, у которого доля часов больше доли обращений, — дорогой: его устранение даёт больше всего.")
        top = sorted(s4, key=lambda r: -r["trud"])[:10]
        t3 = "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["sec"])}</td><td>{E(r["cat"])}</td><td class="c"><b>{r["trud"]:g}</b></td><td class="c">{r["h"]:g}</td>'
                     f'<td>{E((r["desc"].split(chr(10))[0] if len(r["desc"]) > 5 else r["desc"])[:110])}</td></tr>' for r in top)
        p2 = panel("Самые дорогие решённые — 4 недели", stamps("sol4"),
                   f'<div class="tw"><table><thead><tr><th>Обращение</th><th>Раздел</th><th>Тип</th><th>Трудозатраты, ч</th><th>Срок, раб. ч</th><th>Описание</th></tr></thead><tbody>{t3}</tbody></table></div>',
                   "Десять решённых обращений с наибольшими трудозатратами.",
                   "Дорогие обращения — кандидаты на доработку или на отдельный проект: если такое повторяется, дешевле исправить причину.")
        # трудозатраты против срока
        rat = by([r for r in s4 if r["trud"] > 0], lambda r: r["cat"])
        t4 = "".join(f'<tr><th>{c}</th><td>{c1(med([r["trud"] for r in l]))}</td><td>{c1(med([(r["done_dt"]-r["reg_dt"]).total_seconds()/3600 for r in l]))}</td>'
                     f'<td><b>{round(statistics.median([(r["done_dt"]-r["reg_dt"]).total_seconds()/3600/r["trud"] for r in l]))}</b></td></tr>' for c, l in sorted(rat.items(), key=lambda kv: kv[0]))
        anl4 = by(s4, lambda r: r["anl"])
        t5 = "".join(f'<tr><th>{E(short(a))}</th><td>{len(l)}</td><td class="{"bad" if pct(sum(r["trud"] == 0 for r in l), len(l)) >= 30 else ""}">{pct(sum(r["trud"] == 0 for r in l), len(l))}%</td></tr>'
                     for a, l in sorted(anl4.items(), key=lambda kv: -pct(sum(r["trud"] == 0 for r in kv[1]), len(kv[1]))) if len(l) >= 2)
        wr = M["wait_ratio"]
        p3 = panel("Работали против ждали", stamps("sol4"),
                   f'<div class="grid g2"><div class="tw"><table class="num"><thead><tr><th>Тип</th><th>Работа, ч (медиана)</th><th>Календарно, ч (медиана)</th><th>Часов ожидания на час работы</th></tr></thead><tbody>{t4}</tbody></table></div>'
                   f'<div class="tw"><div class="ch">Дисциплина учёта: доля решённых без часов</div><table class="num"><thead><tr><th>Аналитик</th><th>Решено</th><th>Без часов</th></tr></thead><tbody>{t5}</tbody></table></div></div>',
                   "Слева — сколько обращение реально делали (трудозатраты) и сколько оно шло по календарю. Справа — у кого часы не списаны (от 2 решённых).",
                   (f"Обращение ждёт в {wr} раз дольше, чем над ним работают: ускорять надо очередь и маршрут, а не людей. " if wr is not None else
                    "Часы по решённым за период не списаны — соотношение работы и ожидания не посчитать. ")
                   + "Без списанных часов цена по аналитику недостоверна.")
        zomb = sorted([r for r in old if r["trud"] == 0], key=lambda r: -r["age"])
        heavy = sorted(opn, key=lambda r: -r["trud"])[:5]
        t6 = "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["st"])}</td><td class="c"><b>{r["trud"]:g}</b></td></tr>' for r in heavy)
        t7 = "".join(f'<tr><td>{tk(r["id"])}</td><td>{E(r["st"])}</td><td>{E(r["sec"])}</td></tr>' for r in zomb)
        p4 = panel("Вложено в открытые", stamps("open"),
                   f'<div class="grid g2"><div><div class="ch">Больше всего часов — и всё ещё открыто ({hsum(opn):.0f} ч во всей очереди)</div><div class="tw"><table><tbody>{t6}</tbody></table></div></div>'
                   f'<div><div class="ch">«Зомби»: старше 30 дней и ни одного часа — {len(zomb)}</div><div class="tw"><table><tbody>{t7}</tbody></table></div></div></div>',
                   "Трудозатраты, уже списанные на открытые обращения, и старые обращения, по которым не списано ни часа.",
                   "Слева — дорогие и незаконченные: решать, доводить или останавливать. Справа — за них никто не брался: закрыть или назначить.")
        p5 = ""
        st_ = [r for r in real if r["tab_trud"]]
        if st_:
            per = defaultdict(lambda: [0.0, 0.0, set()])
            for r in st_:
                for who, h in r["tab_trud"]:
                    per[who][0 if who == r["anl"] else 1] += h
                    per[who][2].add(r["id"])
            body = "".join(f'<tr><th>{E(short(w))}</th><td>{len(v[2])}</td><td><b>{f"{v[0] + v[1]:.1f}".replace(".", ",")}</b></td><td>{f"{v[0]:.1f}".replace(".", ",")}</td><td class="{"warn" if v[1] > v[0] else ""}">{f"{v[1]:.1f}".replace(".", ",")}</td></tr>'
                           for w, v in sorted(per.items(), key=lambda kv: -(kv[1][0] + kv[1][1])))
            helped = sum(1 for r in st_ if len(r["tab_trud"]) > 1)
            p5 = panel("Трудозатраты по исполнителям — кто реально работал", stamps("sol", "demo" if DEMO_TAB else "sol"),
                       f'<div class="tw"><table class="num"><thead><tr><th>Исполнитель</th><th>Обращ.</th><th>Часов всего</th><th>На своих</th><th>На чужих</th></tr></thead><tbody>{body}</tbody></table></div>'
                       f'<p class="cmp">Обращений, где работали двое и больше: <b>{helped}</b> из {len(st_)}.</p>',
                       f"Табличная часть tab_trud решённых за период: часы каждого исполнителя. «На чужих» — часы на обращениях, где ответственный — другой человек.",
                       "Нагрузка по людям, а не по ответственному: кто тянет чужие обращения и где ответственный только числится.",
                       "demo" if DEMO_TAB else "")
        return (f'<article class="slide" id="s8"><div class="sh"><h2>Цена поддержки в часах</h2>'
                f'<p class="lead">Трудозатраты по обращениям (AmountTrud); решённые за 4 недели и открытые на {NOW:%d.%m}</p></div>' + p1 + p5 + p2 + p3 + p4 + ai_block("s8") + "</article>")

    # ================================================================ СЛАЙД 9 — аналитики
    def slide9():
        S = AI["slides"].get("s9") or {}
        fix = S.get("fix") if isinstance(S.get("fix"), dict) else {}
        s4a = [r for r in rows if r["is_sol"] and r["done_dt"] and r["done_dt"] >= W4S and r["cat"] != "Служебное"]
        catmed = {c: med([r["h"] for r in l]) for c, l in by(s4a, lambda r: r["cat"]).items()}
        per = by(real, lambda r: r["anl"])
        body = ""
        for a, l4 in sorted(by(s4a, lambda r: r["anl"]).items(), key=lambda kv: -len(kv[1])):
            l = per.get(a, [])
            rel = [r["h"] / catmed[r["cat"]] for r in l4 if catmed.get(r["cat"])]
            k = statistics.median(rel) if rel else None
            mi = sum(r in mis for r in l); bd = sum(r["ai"].get("gr") == "П" for r in l); ex = sum(r["ai"].get("gr") == "О" for r in l)
            cxs = [_num(r["ai"]["cx"]) for r in l if r["ai"].get("cx")]
            z = sum(r["trud"] == 0 for r in l4)
            dim = "" if len(l4) >= 5 else ' class="dim"'
            line = f'{pct(sum(r["line"] == "L1" for r in l4), len(l4))}%'
            body += (f'<tr{dim}><th>{E(short(a))}</th><td>{line}</td><td class="c"><b>{len(l4)}</b></td><td class="c">{len(l) or "·"}</td>'
                     f'<td class="c">{c1(med([r["h"] for r in l4]))}</td>'
                     f'<td class="c {"bad" if k and k > 1.5 else "ok" if k and k < 0.8 else ""}">×{c1(round(k, 1)) if k else "—"}</td>'
                     f'<td class="c">{hsum(l4):.0f}</td><td class="c">{pct(sum(r["cat"] == "Правка данных" for r in l4), len(l4))}%</td>'
                     f'<td class="c {"bad" if pct(z, len(l4)) >= 30 else ""}">{pct(z, len(l4))}%</td>'
                     f'<td class="c">{c1(round(statistics.mean(cxs), 1)) if cxs else "·"}</td>'
                     f'<td class="c {"bad" if bd else ""}">{f"{bd} · {pct(bd, len(l))}%" if bd else "·"}</td><td class="c">{f"{ex} · {pct(ex, len(l))}%" if ex else "·"}</td><td class="c {"bad" if mi and pct(mi, len(l)) >= 25 else ""}">{mi or "·"}</td>'
                     f'<td style="text-align:left">{fmt(fix.get(a, ""))}</td></tr>')
        p1 = panel("Сводная таблица и что поправить", stamps("sol4", "sol", "ai"),
                   f'<div class="tw"><table class="num"><thead><tr><th rowspan="2">Аналитик</th><th rowspan="2">Доля 1-й линии</th><th colspan="7">4 недели — скорость и объём</th><th colspan="4">Период {PER_S} — разбор ИИ</th><th rowspan="2" style="text-align:left">Что поправить (ИИ)</th></tr>'
                   f'<tr><th>Решено</th><th>за период</th><th>Медиана, раб. ч</th><th>К медиане типа</th><th>Часы</th><th>Доля правок</th><th>Без часов</th><th>Сложн. 1–5</th><th>Плохо · доля</th><th>Отлично · доля</th><th>Неверный тип</th></tr></thead><tbody>{body}</tbody></table></div>',
                   f"Скорость, объём и часы — за 4 недели ({W4S:%d.%m}–{PER_S[-5:]}), чтобы доли не прыгали от одного обращения; качество, сложность и тип — разбор ИИ решённых за период. «Доля 1-й линии» — сколько его решений по правилу Т-10 относятся к первой линии. «К медиане типа» — правка сравнивается с правкой, инцидент — с инцидентом. Меньше 5 решённых за 4 недели — серым.",
                   "Один балл не строится: скорость, качество и классификация смотрятся рядом. Последняя колонка — конкретная ошибка человека с номером обращения.")
        cx_l = [r for r in real if r["ai"].get("cx")]
        hard = sorted(cx_l, key=lambda r: (-_num(r["ai"]["cx"]), -r["trud"]))[:5]
        easy = sorted(cx_l, key=lambda r: (_num(r["ai"]["cx"]), r["trud"]))[:5]
        row_ = lambda r: f'<tr><td>{tk(r["id"])}</td><td class="c"><b>{r["ai"]["cx"]}</b></td><td class="c">{str(r["trud"]).replace(".", ",")}</td><td>{E(r["ai"].get("s", ""))}</td></tr>'
        p_cx = panel("Самые сложные и самые простые решения", stamps("sol", "ai"),
                     f'<div class="grid g2"><div><div class="ch">Сложные — 5</div><div class="tw"><table><thead><tr><th>Обращение</th><th>Сложн.</th><th>Часы</th><th>Суть</th></tr></thead><tbody>{"".join(map(row_, hard))}</tbody></table></div></div>'
                     f'<div><div class="ch">Простые — 5</div><div class="tw"><table><thead><tr><th>Обращение</th><th>Сложн.</th><th>Часы</th><th>Суть</th></tr></thead><tbody>{"".join(map(row_, easy))}</tbody></table></div></div></div>',
                     "Сложность 1–5 — оценка ИИ по решению: 1 — кнопка или штатная правка, 3 — анализ и исправление цепочки документов, 5 — перерасчёт регистров (бывшее приложение старого отчёта, Т-51).",
                     "Сложные — эталон для базы знаний и кандидаты в доработку; простые — первые кандидаты на самообслуживание и первую линию.")
        # Т-56: вторая линия решает обращения первой (в решении — ссылка на инструкцию confluence)
        s4 = s4a
        grab = [r for r in s4 if L1_WORD in r["sol"].lower() and not r["anl"].startswith(L1_ANALYST)]
        gb = by(grab, lambda r: r["anl"])
        body = ""
        for a, l in sorted(gb.items(), key=lambda kv: -len(kv[1])):
            own = [r for r in s4 if r["anl"] == a]
            body += (f'<tr><th>{E(short(a))}</th><td class="c"><b>{len(l)}</b></td><td class="c">{sum(in_per(r["done_dt"]) for r in l)}</td>'
                     f'<td class="c">{pct(len(l), len(own))}%</td><td class="c">{str(hsum(l)).replace(".", ",")}</td>'
                     f'<td style="text-align:left">{tks([r["id"] for r in sorted(l, key=lambda r: r["done_dt"], reverse=True)])}</td></tr>')
        p_grab = panel("Вторая линия решает обращения первой — по ФИО", stamps("sol4"),
                       f'<div class="tw"><table class="num"><thead><tr><th>Аналитик</th><th>Обращ. за 4 нед.</th><th>из них за период</th>'
                       f'<th>Доля его решённых</th><th>Часов</th><th style="text-align:left">Обращения</th></tr></thead><tbody>{body}</tbody></table></div>'
                       f'<p class="cmp">Всего за 4 недели: <b>{len(grab)}</b> обращений, <b>{str(hsum(grab)).replace(".", ",")} ч</b> второй линии — это работа, которую могла сделать первая линия.</p>',
                       f"Решённые за 4 недели обращения, где в решении есть ссылка на confluence (значит, есть инструкция), а ответственный — не {L1_ANALYST}. Служебные карточки исключены.",
                       "Показывает, кто из второй линии берёт на себя работу первой. Такие обращения — кандидаты на передачу первой линии: вторая линия освобождает часы для сложных задач (shift-left, Т-56).")
        case = lambda x, cls, lab: (f'<div class="case {cls}"><span>{lab}</span>{tk(x["id"])}<p>{E(BYID.get(x["id"], {}).get("ai", {}).get("s", ""))}</p><b>{E(x.get("why", ""))}</b></div>'
                                    if isinstance(x, dict) and x.get("id") else f'<div class="case {cls}"><span>{lab}</span><p class="mut">Разбор ИИ недоступен.</p></div>')
        p2 = panel("Случай недели", stamps("ai", "sol"),
                   f'<div class="grid g2">{case(S.get("case_best"), "good", "Лучший")}{case(S.get("case_worst"), "badc", "Худший")}</div>',
                   "Вместо номинаций: один лучший и один худший случай недели с номерами (Т-50).",
                   "Пример для команды: что тиражировать и чего не допускать — на реальном обращении, а не на абстрактном балле.")
        return (f'<article class="slide" id="s9"><div class="sh"><h2>Аналитики: скорость, качество, что поправить</h2>'
                f'<p class="lead">Скорость — за 4 недели, качество — разбор ИИ за {PER}; оценки пользователей в выгрузке пока нет</p></div>' + p1 + p_grab + p_cx + p2 + ai_block("s9") + "</article>")

    # ================================================================ СЛАЙД 10 — паспорт данных
    def slide10():
        ids_ai = {x for _, t in _strings(AI["slides"]) for x in ID_RX.findall(t)} | {x for _, t in _strings(AI["signals"]) for x in ID_RX.findall(t)}
        bad_ids = sorted(x for x in ids_ai if x not in RAWID)
        ch = [("Строк в выгрузке = решено + отклонено + открыто + открытые служебные + старая доска" + (" + без даты регистрации" if R.noreg else ""), len(raw),
               sum(r["is_sol"] for r in rows) + sum(r["is_rej"] for r in rows) + len(opn) + len(opn_svc) + len(dropped) + len(R.noreg)),
              ("Решённые за период размечены ИИ", len(sol), len([r for r in sol if r["ai"]])),
              # ЧТО ИЗМЕНЕНО: проверка номеров — по факту, а не постоянная строка «все = все». ПОЧЕМУ: в v5 тексты пишет модель
              ("Номера в разборах ИИ есть в выгрузке", "все", "все" if not bad_ids else f"нет {len(bad_ids)}"),
              ("Сумма «кто держит» = открытые", len(opn), sum(1 for r in opn if r["holder"] in HOLDERS)),
              ("Первая + вторая линия = решённые без служебных", len(real), len(L1) + len(L2))]
        body = "".join(f'<tr><td>{E(a)}</td><td class="c">{b}</td><td class="c">{c}</td><td class="{"ok" if b == c else "bad"}">{"сходится" if b == c else "расхождение"}</td></tr>' for a, b, c in ch)
        sel = [("▲ Пришло", f"дата регистрации в {PER}", len(inc)), ("▼ Решено", f"статус «Закрыто» или «Отработано…», дата решения в {PER}", len(sol)),
               ("✕ Отклонено", f"статус «Отклонено», дата отклонения в {PER}", len(rej)), ("● Открыто", f"не решены и не отклонены на {NOW:%d.%m %H:%M}", len(opn)),
               ("◇ 4 недели", f"{W4S:%d.%m}–{PER_S[-5:]}, по дате регистрации или решения", "—"),
               ("Отброшено при загрузке", "статусы старой доски «Выполнено - …»", len(dropped))]
        s = "".join(f"<tr><td><b>{a}</b></td><td>{E(b)}</td><td class='c'>{c}</td></tr>" for a, b, c in sel)
        ai_rule = ("Сложность 1–5 — поле разметки ИИ. Расход токенов в макете не считается (разметку делал Claude вручную); в отчёте — токены разметки, группировки и разборов из лога прогона."
                   if run_log is None else "Сложность 1–5 — поле разметки ИИ. Расход ИИ этого прогона — таблица «Расход ИИ по этапам» ниже.")
        rules = [("Отчётный период", f"С понедельника недели максимальной даты решения по эту дату ({rule}). Параметр REPORT_WEEK задаёт неделю явно."),
                 ("Первая линия", f"Ответственный — {L1_ANALYST} или в решении есть «{L1_WORD}»; остальное — вторая."),
                 ("НСИ", f"Раздел «{NSI_SECTION}» целиком; «Правка данных» — тип «Изменение данных в системе» вне НСИ."),
                 ("Срок решения", f"Календарные часы рабочих дней от регистрации до решения / {SLA_DIVIDER}: 8 ч в рабочем дне, выходные и праздники РФ не считаются (Т-67, Т-68); позже — настоящий SLA из 1С. Дата решения — «Отработано»; «Закрыто» — формальная."),
                 ("Трудозатраты", "AmountTrud, часы по обращению на момент выгрузки; 0 — не списано."),
                 ("Сложность и расход ИИ", ai_rule),
                 ("Служебные карточки", f"ИИ помечает карточки учёта времени и поручения, плюс явные признаки в тексте ({SVC_RX}) — из скорости и цены исключаются.")]
        r_ = "".join(f"<tr><td><b>{a}</b></td><td>{E(b)}</td></tr>" for a, b in rules)
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: «Решения руководителя недели» убраны из списка — в v5 они хранятся в истории (Т-52);
        #               ссылка и код сотрудника показываются, только пока их нет в выгрузке (Т-57, Т-69)
        # ПОЧЕМУ: список — то, чего не хватает отчёту сейчас
        # ----------------------------------------------------------------------
        miss = [("Оценка пользователя и комментарий", "Настоящий сигнал качества вместо автозакрытия; учёт в рейтинге"),
                ("Дата последнего изменения обращения", "Сколько дней обращение без движения — точнее, чем возраст"),
                ("История статусов и трудозатраты по исполнителям", "Постановка есть — tab_status, tab_trud (vygruzka-1c.md, п. 2.4); в 1С пока не выгружаются"),
                ("Номер релиза, которым закрыт инцидент", "Какие инциденты ждут какой релиз"),
                ("Выгрузка за 6 месяцев (разово)", "Полная динамика по месяцам")]
        if not any(r.get("url") for r in rows):
            miss.append(("Ссылка на обращение (url)", "Номер в отчёте открывает карточку в СППР (Т-57, vygruzka-1c.md, п. 2.5)"))
        if R.merged.get("cli") is None:
            miss.append(("Код сотрудника (cli_id, anl_id)", "Склейка двух написаний одного ФИО (Т-69, vygruzka-1c.md, п. 2.6)"))
        m_ = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in miss)
        p1 = panel("Выборки отчёта", "", f'<div class="tw"><table><thead><tr><th>Выборка</th><th>Правило</th><th>Строк</th></tr></thead><tbody>{s}</tbody></table></div>',
                   "Каждый блок отчёта помечен одной из этих меток.", "Цифры с разными метками нельзя складывать и сравнивать напрямую.")
        p2 = panel("Проверки сходимости", "", f'<div class="tw"><table><thead><tr><th>Проверка</th><th>Слева</th><th>Справа</th><th>Итог</th></tr></thead><tbody>{body}</tbody></table></div>',
                   "Сверка сумм по разным разрезам.", "Красное — ошибка отчёта: такой отчёт не рассылается.")
        p3 = panel("Правила расчёта", "", f'<div class="tw"><table><tbody>{r_}</tbody></table></div>', "Определения, на которых стоят все цифры.", "Одно определение на весь отчёт — нет «57 против 58» на разных слайдах.")
        tb = "".join(f'<tr><td><b>{t}</b></td><td class="c">{TAB_ON[t]}</td><td class="c">{sum(len(r[t]) for r in rows)}</td><td class="c">{TAB_BAD[t] or "·"}</td></tr>' for t in TAB_COLS)
        tchk = (f'<p class="cmp">Сумма tab_trud = AmountTrud: <span class="{"ok" if not TRUD_MISMATCH else "bad"}">{"сходится у всех" if not TRUD_MISMATCH else "расхождений " + str(len(TRUD_MISMATCH))}</span>.'
                + (' <b class="warn">Части в этой выгрузке выдуманы (демо).</b>' if DEMO_TAB else "") + "</p>")
        p5 = panel("Табличные части обращения", stamps("demo") if DEMO_TAB else "",
                   f'<div class="tw"><table class="num"><thead><tr><th>Часть</th><th>Обращений с частью</th><th>Строк</th><th>Отброшено строк</th></tr></thead><tbody>{tb}</tbody></table></div>{tchk}',
                   "Необязательные поля-массивы внутри обращения (data.md, разд. 10). Нет части — нет данных, блоки на ней не показываются.",
                   "Контроль, что доп. данные пришли и сходятся с основными полями.", "demo" if DEMO_TAB else "")
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: в паспорт добавлена панель «Доверие к данным»
        # ПОЧЕМУ: аудит 8а.8: читатель должен видеть, на сколько можно верить цифрам — автозакрытие, нулевые часы, сбои разметки, раздвоенные ФИО
        # ----------------------------------------------------------------------
        cl = [r for r in rows if r["st"] == "Закрыто" and r["cls_dt"]]
        auto = sum(r["cls_dt"].hour == 19 and r["cls_dt"].minute == 30 for r in cl)
        nz = lambda x: re.sub(r"[^a-z]", "", x.lower()).replace("kh", "h")
        clis = sorted({r["cli"] for r in rows})
        cyr = {(nz("".join(TRANSLIT.get(c, c) for c in n.split()[0].lower())), nz("".join(TRANSLIT.get(c, c) for c in n.split()[1].lower()))[:3]): n
               for n in clis if re.match("[А-ЯЁ]", n) and len(n.split()) >= 2}
        dup = sorted(f"{n} = {cyr[(nz(n.split()[-1]), nz(n.split()[0])[:3])]}" for n in clis
                     if re.match("[A-Za-z]", n) and len(n.split()) >= 2 and (nz(n.split()[-1]), nz(n.split()[0])[:3]) in cyr)
        names_row = (("Один человек — два написания ФИО", f"{len(dup)}: " + "; ".join(dup) if dup else "нет", "Топы инициаторов делятся; лечится кодом сотрудника в выгрузке")
                     if R.merged.get("cli") is None else
                     ("Один человек — два написания ФИО", f"склеено по коду сотрудника: инициаторов {R.merged['cli']}, аналитиков {R.merged.get('anl') or 0}", "Т-69: топы считаются по человеку, а не по написанию"))
        trust = [("Файл выгрузки", R.dump_name, "Из него посчитан весь отчёт"),
                 ("«Закрыто» поставлено в 19:30", f"{auto} из {len(cl)} ({pct(auto, len(cl))}%)", "Дата закрытия — автоматическая, поэтому везде берётся дата решения"),
                 ("Решённые за период без трудозатрат", f"{sum(r['trud'] == 0 for r in real)} из {len(real)} ({pct(sum(r['trud'] == 0 for r in real), len(real))}%)", "Цена в часах занижена на эти обращения"),
                 ("Решённые без оценки ИИ (Н/Д)", f"{len([r for r in sol if not r['ai']])} из {len(sol)}", "Сбой разметки: не входят в рейтинг и списки «Плохо» / «Лучшие»"),
                 names_row]
        if not R.cover_ok:
            trust.append(("Выгрузка покрывает 4 недели", f"нет: первое решение {R.first_res:%d.%m}, окно — с {W4S:%d.%m}", "Блоки «4 недели» неполные: нужна выгрузка за 4 недели"))
        if R.warnings:
            trust.append(("Предупреждения вёрстки", "; ".join(sorted(set(R.warnings))), "Разбор ИИ сослался на то, чего нет в данных: проверить журнал запуска"))
        p6 = panel("Доверие к данным", "", '<div class="tw"><table><thead><tr><th>Показатель</th><th>Значение</th><th>Что значит</th></tr></thead><tbody>'
                   + "".join(f"<tr><td><b>{E(a)}</b></td><td>{E(b)}</td><td>{E(c)}</td></tr>" for a, b, c in trust) + "</tbody></table></div>",
                   "Свойства самой выгрузки, которые влияют на точность цифр отчёта.", "Если доля здесь растёт — цифры отчёта хуже отражают реальность, сначала чинить учёт.")
        p4 = panel("Чего нет в выгрузке", "", f'<div class="tw"><table><thead><tr><th>Поле</th><th>Что даст отчёту</th></tr></thead><tbody>{m_}</tbody></table></div>',
                   "Список для доработки выгрузки 1С и истории.", "Каждая строка открывает новый блок аналитики.")
        # ----------------------------------------------------------------------
        # ЧТО ИЗМЕНЕНО: расход ИИ по этапам прогона — в паспорт (Т-51: «сложность и расход ИИ — в паспорт данных»)
        # ПОЧЕМУ: в v4 токены шли только в Google Sheets при IS_DEBUG; время этапов — по HANDOFF, разд. 0
        # ----------------------------------------------------------------------
        p7 = ""
        if run_log:
            rl = "".join(f'<tr><td><b>{E(x.get("stage", ""))}</b></td><td>{E(x.get("model", ""))}</td><td class="c">{x.get("calls", 0)}</td><td class="c">{x.get("cached", 0)}</td>'
                         f'<td class="c">{format(x.get("tokens", 0), ",").replace(",", " ")}</td><td class="c">{x.get("sec", 0):.0f}</td><td>{E(x.get("note", ""))}</td></tr>' for x in run_log)
            p7 = panel("Расход ИИ по этапам", "", f'<div class="tw"><table class="num"><thead><tr><th>Этап</th><th>Модель</th><th>Вызовов</th><th>Из кэша</th><th>Токенов</th><th>Секунд</th><th>Примечание</th></tr></thead><tbody>{rl}</tbody></table></div>',
                       "Вызовы модели в этом прогоне: разметка, группы тем, открытые, разборы слайдов. «Из кэша» — ответы прошлого прогона той же выгрузки, без оплаты.",
                       "Сколько стоит отчёт и где теряется время прогона; рост числа повторов — признак, что модель плохо держит формат ответа.")
        return (f'<article class="slide" id="s10"><div class="sh"><h2>Паспорт данных и проверки</h2><p class="lead">Какие выборки в отчёте и можно ли верить цифрам · генератор report_v5 {VERSION}</p></div>'
                + '<div class="grid g2">' + p1 + p2 + "</div>" + '<div class="grid g2">' + p3 + p4 + "</div>" + p6 + p5 + p7 + "</article>")

    # ================================================================ СБОРКА
    FN = {"s1": slide1, "s2": slide2, "s3": slide3, "s4": slide4, "s5": slide5, "s6": slide6, "s7": slide7, "s8": slide8, "s9": slide9, "s10": slide10, "s11": slide11}
    num = {k: i + 1 for i, k in enumerate(ORDER)}
    # ссылки меню идут в порядке ORDER — JS сопоставляет их со слайдами по индексу
    nav = [(g, [(k, t.format(WEEK=WEEK, NOW=f"{NOW:%d.%m}")) for k, t in items]) for g, items in NAV]
    rail_links = {k: t for _, items in nav for k, t in items}
    rail = "".join(f'<div class="act">{g}</div><ol>' + "".join(f'<li><a href="#{k}"><span>{num[k]}</span>{E(t)}</a></li>' for k, t in sorted(items, key=lambda kt: num[kt[0]])) + "</ol>"
                   for g, items in [(g, [(k, rail_links[k]) for k in ORDER if k in dict(it)]) for g, it in nav])
    slides = {k: FN[k]() for k in ORDER}
    return rail, slides


def render(R, template_text, title=None, banner=None, run_log=None, strict=False):
    """Готовый HTML отчёта: слайды модуля в оболочке template_v5.html (Jinja2, autoescape)."""
    from jinja2 import Environment
    check_template(template_text)
    R.warnings = []
    rail, slides = _build(R, with_ai=True, strict=strict, run_log=run_log)
    if R.warnings:
        R.say(f"⚠️ Предупреждения вёрстки: {sorted(set(R.warnings))}")
    return Environment(autoescape=True).from_string(template_text).render(
        title=title or f"Качество 1С-поддержки · Неделя {R.WEEK}", banner=banner,
        period=f"Неделя {R.WEEK} · {R.PER} · срез {R.NOW:%d.%m %H:%M}", rail=rail, slides="".join(slides[k] for k in ORDER))


def report_file_name(R):
    """Имя файла отчёта — как в v4: «Отчет по качеству W{N} ({первая дата решения за период}).html»."""
    first = min((r["done_dt"] for r in R.sol), default=R.WS)
    return f"Отчет по качеству W{R.WEEK} ({first:%d.%m.%Y})"


# ================================================================ ТЕКСТ СЛАЙДА ДЛЯ ПРОМПТА
class _Text(HTMLParser):
    """HTML слайда → текст: заголовки, абзацы, строки таблиц «ячейка | ячейка»; из графиков — только подсказки <title>,
    у полос с подсказкой (title) — подсказка вместо голого числа."""
    BLOCK = {"div", "p", "section", "header", "article", "table", "thead", "tbody", "ol", "li", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.line, self.svg, self.title, self.skip, self.hint = [], [], 0, False, 0, 0

    def flush(self):
        t = re.sub(r"\s+", " ", "".join(self.line)).strip(" |·")
        if t: self.out.append(t)
        self.line = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.skip += 1
        if tag == "svg":
            self.flush(); self.svg += 1
        if self.svg:
            if tag == "title": self.flush(); self.title = True; self.line.append("• ")
            return
        if tag in self.BLOCK or tag == "tr": self.flush()
        if tag in ("h2", "h3", "h4"): self.line.append({"h2": "# ", "h3": "## ", "h4": "### "}[tag])
        if tag in ("td", "th") and self.line: self.line.append(" | ")
        if tag == "br": self.line.append(" · ")
        if tag == "i" and dict(attrs).get("title"):
            self.line.append(f" [{dict(attrs)['title']}] "); self.hint += 1
        if tag in ("span", "small", "b", "i", "em", "a"): self.line.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"): self.skip -= 1
        if tag == "svg":
            self.svg -= 1; self.flush(); return
        if self.svg:
            if tag == "title": self.title = False; self.flush()
            return
        if tag == "i" and self.hint: self.hint -= 1
        if tag in self.BLOCK or tag == "tr": self.flush()
        if tag in ("span", "small", "b", "i", "em", "a"): self.line.append(" ")

    def handle_data(self, data):
        if self.skip or self.hint: return
        if self.svg and not self.title: return
        self.line.append(data)


def html_text(h):
    p = _Text(); p.feed(h); p.flush()
    return "\n".join(p.out)


def slide_texts(R, keys=None):
    """{ключ: текст слайда без блока «Разбор ИИ по слайду»} — что видит читатель; для промпта разбора."""
    saved, R.warnings = getattr(R, "warnings", []), []
    _, slides = _build(R, with_ai=False)
    R.warnings = saved
    return {k: html_text(v) for k, v in slides.items() if keys is None or k in keys}
