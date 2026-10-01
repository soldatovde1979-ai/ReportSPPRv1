# ----------------------------------------------------------------------
# make_demo_tab.py — ДЕМО-копия выгрузки с табличными частями (Т-54/Т-55)
# ЧТО: копирует выгрузку 29.09 и добавляет в каждое обращение
#      tab_trud   — AmountTrud, разложенный по исполнителям из журнала решения;
#      tab_status — правдоподобную историю статусов карточки и требования.
# ПОЧЕМУ: 1С ещё не выгружает табличные части, а формат и отчёт надо
#      проверить сейчас. Части ВЫДУМАНЫ (детерминированно, от номера
#      обращения); остальные поля — настоящие.
# Запуск (Linux / Bash):  python3 examples/make_demo_tab.py
# ----------------------------------------------------------------------
VERSION = "1.0"
DUMP_FILE = "data/sppr_dump_20260929_180748_842rec.json"
OUT_FILE = "examples/sppr_dump_20260929_180748_842rec_demo_tab.json"

import json, re, os, hashlib
from datetime import datetime, timedelta

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOLVED = ["Отработано, требует подтверждения", "Закрыто"]
NAME_RX = re.compile(r"\d{2}\.\d{2}\.\d{4} \d{1,2}:\d{2}:\d{2} ([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+(?: [А-ЯЁ][а-яё]+)?):")
DEV_CHAIN = ["Планирование разработки", "Разработка", "Внутреннее тестирование", "Проверка релиза"]
NOW = datetime(2026, 9, 29, 18, 7, 48)


def rnd(key, n):
    """Детерминированное «случайное» число 0..n-1 от строки."""
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % n


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S")


raw = json.load(open(DUMP_FILE, encoding="utf-8"))
FULL = sorted({r["anl"].strip() for r in raw if r["anl"].strip()})


def full_name(who):
    """«Бердников Игорь» из журнала решения → «Бердников Игорь Викторович», если однозначно."""
    c = [n for n in FULL if n.startswith(who)]
    return c[0] if len(c) == 1 else who
n_trud = n_st = 0
for r in raw:
    i, anl, st = r["id"].strip(), r["anl"].strip(), r["st"].strip()
    reg = datetime.fromisoformat(r["reg"])
    res = datetime.fromisoformat(r["res"]) if r["res"] else None
    cls = datetime.fromisoformat(r["cls"]) if r["cls"] else None
    # ---- tab_trud: AmountTrud по исполнителям (ответственный — 70%, остальное поровну)
    total = float(r.get("AmountTrud") or 0)
    ppl = []
    for who in map(full_name, NAME_RX.findall(r["sol"])):
        if who not in ppl:
            ppl.append(who)
    if anl and anl not in ppl:
        ppl.insert(0, anl)
    if total > 0 and ppl:
        shares = [1.0] if len(ppl) == 1 else [0.7] + [0.3 / (len(ppl) - 1)] * (len(ppl) - 1)
        rows_, left = [], total
        for k, (who, sh) in enumerate(zip(ppl, shares)):
            v = round(total * sh, 2) if k < len(ppl) - 1 else round(left, 2)
            left -= v
            rows_.append([who, v])
        r["tab_trud"] = rows_
        n_trud += len(rows_)
    # ---- tab_status: история карточки и требования
    if st.startswith("Выполнено - "):
        continue
    chain = [("Ожидает анализа", anl)]
    if rnd(i + "a", 3):
        chain.append(("Анализ", anl))
    if rnd(i + "u", 4) == 0:                         # уточнение у пользователя, иногда дважды
        chain += [("Уточнение", anl), ("Анализ", anl)]
        if rnd(i + "u2", 3) == 0:
            chain += [("Уточнение", anl), ("Анализ", anl)]
    if (r["type"] == "Инцидент" and rnd(i + "d", 2) == 0) or st in DEV_CHAIN + ["Внутреннее тестирование на Предпроде"]:
        chain += [(s, "Разработчик") for s in DEV_CHAIN]
    end = res or (cls if st == "Отклонено" else None) or NOW
    if st not in SOLVED and st != "Отклонено":        # открытые: цепочка обрывается на текущем статусе
        names = [c[0] for c in chain]
        chain = chain[: names.index(st) + 1] if st in names else chain + [(st, anl)]
        end = NOW
    step = max((end - reg).total_seconds() / (len(chain) + (0 if r["st"] not in SOLVED else 1)), 60)
    tab = [[iso(reg + timedelta(seconds=step * k)), who, "карточка", s] for k, (s, who) in enumerate(chain)]
    if res:
        tab.append([iso(res), anl, "требование", "Отработано, требует подтверждения"])
    if cls and st == "Закрыто":
        who = "Регламентное задание" if cls.strftime("%H:%M") == "19:30" else r["cli"].strip()
        tab.append([iso(cls), who, "требование", "Закрыто"])
    if st == "Отклонено" and cls:
        tab.append([iso(cls), anl, "требование", "Отклонено"])
    r["tab_status"] = tab
    n_st += len(tab)

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in raw) + "\n]\n")
print(f"Записан {OUT_FILE}: {len(raw)} обращений, строк tab_trud {n_trud}, tab_status {n_st} (ДЕМО)")
