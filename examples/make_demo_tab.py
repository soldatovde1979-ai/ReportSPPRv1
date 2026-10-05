# ----------------------------------------------------------------------
# make_demo_tab.py — ДЕМО-копия выгрузки с табличными частями (Т-54/Т-55)
# ЧТО: копирует выгрузку 29.09 и добавляет в каждое обращение
#      tab_trud   — AmountTrud, разложенный по исполнителям из журнала решения;
#      tab_status — правдоподобную историю статусов карточки и требования;
#      tab_sla    — время по статусам карточки с паузами (1.1);
#      tab_rate   — оценку пользователя у части решённых (1.1);
#      parent     — связь с прошлым обращением того же инициатора (1.1).
# ПОЧЕМУ: 1С ещё не выгружает табличные части, а формат и отчёт надо
#      проверить сейчас. Части ВЫДУМАНЫ (детерминированно, от номера
#      обращения); остальные поля — настоящие.
# Запуск (Linux / Bash):  python3 examples/make_demo_tab.py
# ----------------------------------------------------------------------
VERSION = "1.3"   # 1.3 — name из причёсанного описания (clean_text); 1.2 — name у части обращений (1С v1.8, З-6.2)
DUMP_FILE = "data/sppr_dump_20260929_180748_842rec.json"
OUT_FILE = "examples/sppr_dump_20260929_180748_842rec_demo_tab.json"

import json, re, os, hashlib, importlib.util
from datetime import datetime, timedelta

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# clean_text из общего модуля: name демо — первая фраза причёсанного текста (Т-80),
# тот же, что видит report_v5
spec = importlib.util.spec_from_file_location("report_v5", "src/report_v5.py")
rv5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv5)
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
n_trud = n_st = n_sla = n_rate = n_par = n_name = 0
# parent: предыдущее по дате регистрации обращение того же инициатора — главное всегда раньше дочернего
prev_of, last_by_cli = {}, {}
for r in sorted(raw, key=lambda r: r["reg"] or ""):
    c = r["cli"].strip()
    if c in last_by_cli: prev_of[r["id"].strip()] = last_by_cli[c]
    last_by_cli[c] = r["id"].strip()
for r in raw:
    i, anl, st = r["id"].strip(), r["anl"].strip(), r["st"].strip()
    reg = datetime.fromisoformat(r["reg"])
    res = datetime.fromisoformat(r["res"]) if r["res"] else None
    cls = datetime.fromisoformat(r["cls"]) if r["cls"] else None
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО (1.3): name — первая фраза причёсанного описания (clean_text), не сырца:
    # в сыром описании первая фраза — почти всегда приветствие («Добрый день!»).
    # ПОЧЕМУ: Т-80 — краткое описание без приветствий; причёсанный текст пуст — name не ставим
    # ----------------------------------------------------------------------
    if rnd(i + "name", 3) == 0 and r["desc"]:
        first = re.split(r"[.!?\n]", rv5.clean_text(r["desc"]), maxsplit=1)[0]
        if first:
            r["name"] = (first[:60] + "…") if len(first) > 60 else first
            n_name += 1
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
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО (1.1): tab_sla, tab_rate, parent — как их отдаёт выгрузка 1С v1.7 (src/vygruzka-1c.md, п. 2.4)
    # ПОЧЕМУ: модуль 5.2 показывает срок по 1С, оценки и связи — макету и стенду нужны эти данные
    # ----------------------------------------------------------------------
    # tab_sla [дата, статус, секунд, пауза, дата смены]: по статусам карточки; «Уточнение» — пауза; работа — часть шага
    sla = []
    for k, (s, who) in enumerate(chain):
        a = reg + timedelta(seconds=step * k)
        b = reg + timedelta(seconds=step * (k + 1))
        pause = s == "Уточнение"
        sec = int(step * (1 if pause else (2 + rnd(i + s + str(k), 7)) / 10))
        sla.append([iso(a), s, sec, pause, iso(b)])
    if sla:
        r["tab_sla"] = sla
        n_sla += len(sla)
    # tab_rate [дата, оценка, заявитель, ответственный, комментарий]: примерно у каждого пятого решённого
    if st in SOLVED and res and rnd(i + "r", 5) == 0:
        v = [5, 5, 5, 5, 5, 5, 4, 4, 3, 2][rnd(i + "rv", 10)]
        com = {4: "В целом решили, но долго", 3: "Пришлось писать повторно", 2: "Проблема осталась"}.get(v, "")
        r["tab_rate"] = [[iso(res + timedelta(hours=2 + rnd(i + "rt", 40))), str(v), r["cli"].strip(), anl, com]]
        n_rate += 1
    # parent: примерно у каждого восьмого — прошлое обращение того же инициатора
    if i in prev_of and rnd(i + "p", 8) == 0:
        r["parent"] = prev_of[i]
        n_par += 1

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in raw) + "\n]\n")
print(f"Записан {OUT_FILE}: {len(raw)} обращений, строк tab_trud {n_trud}, tab_status {n_st}, tab_sla {n_sla}, "
      f"оценок {n_rate}, связей parent {n_par}, name {n_name} (ДЕМО)")
