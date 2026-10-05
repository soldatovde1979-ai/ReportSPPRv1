# compare_dumps v1.0 (05.10.2026)
# Сверка двух выгрузок СППР (JSON) — прежней и новой версии функции 1С — по количественным показателям.
# Запуск:  py tools\compare_dumps_v1.py старая.json новая.json        (Windows)
#          python3 tools/compare_dumps_v1.py старая.json новая.json   (Linux/macOS)
# Только чтение: файлы не меняет, ничего не пишет. Нужен только стандартный Python 3.8+.
# Код возврата: 0 — базовые поля совпали; 1 — есть расхождения в базовой части (новые поля не в счёт).
# Описание — src/vygruzka-1c.md, п. 3.1.
import json
import sys
from collections import Counter

BASE = ["st", "id", "reg", "res", "cls", "sec", "desc", "sol", "anl", "cli", "type", "AmountTrud"]
NEW_FIELDS = ["url", "cli_id", "anl_id", "parent"]
TABS = ["tab_trud", "tab_status", "tab_sla", "tab_rate", "tab_chat"]
SOLVED = {"Закрыто", "Отработано, требует подтверждения"}


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        sys.exit(f"{path}: ожидался массив объектов JSON")
    return data


def norm(v):
    return v.strip() if isinstance(v, str) else v


def groups(rows):
    c = Counter()
    for r in rows:
        st = norm(r.get("st") or "")
        c["решено" if st in SOLVED else "отклонено" if st == "Отклонено" else "открыто"] += 1
    return c


def main(old_path, new_path):
    old, new = load(old_path), load(new_path)
    o = {norm(r.get("id")): r for r in old}
    n = {norm(r.get("id")): r for r in new}
    bad = False

    print(f"Старая: {old_path} — {len(old)} строк, уникальных id {len(o)}")
    print(f"Новая:  {new_path} — {len(new)} строк, уникальных id {len(n)}")
    if len(o) != len(old) or len(n) != len(new):
        print("  ! есть повторяющиеся id"); bad = True

    print("\n1. Состав обращений")
    only_o, only_n = sorted(set(o) - set(n)), sorted(set(n) - set(o))
    print(f"  общих {len(set(o) & set(n))}; только в старой {len(only_o)}; только в новой {len(only_n)}")
    if only_o: print("  только в старой:", ", ".join(only_o[:20]), "…" if len(only_o) > 20 else ""); bad = True
    if only_n: print("  только в новой: ", ", ".join(only_n[:20]), "…" if len(only_n) > 20 else ""); bad = True

    print("\n2. Группы и статусы (старая → новая)")
    go, gn = groups(old), groups(new)
    for g in ("решено", "отклонено", "открыто"):
        mark = "" if go[g] == gn[g] else "  !"
        print(f"  {g:10} {go[g]:5} → {gn[g]:5}{mark}")
        bad |= go[g] != gn[g]
    so, sn = Counter(norm(r.get("st")) for r in old), Counter(norm(r.get("st")) for r in new)
    for st in sorted(set(so) | set(sn), key=lambda s: -(so[s] + sn[s])):
        if so[st] != sn[st]:
            print(f"  ! статус «{st}»: {so[st]} → {sn[st]}"); bad = True

    print("\n3. Базовые поля по общим обращениям (сколько обращений отличается)")
    for f in BASE[2:]:
        diff = [i for i in set(o) & set(n) if norm(o[i].get(f)) != norm(n[i].get(f))]
        mark = "" if not diff else "  ! например " + ", ".join(sorted(diff)[:5])
        print(f"  {f:11} {len(diff):5}{mark}")
        bad |= bool(diff)
    to = sum(float(r.get("AmountTrud") or 0) for r in old)
    tn = sum(float(r.get("AmountTrud") or 0) for r in new)
    print(f"  сумма AmountTrud: {to:.1f} → {tn:.1f}" + ("" if abs(to - tn) < 0.05 else "  !"))

    print("\n4. Новые поля в новой выгрузке (у скольких строк заполнено)")
    for f in NEW_FIELDS:
        cnt = sum(1 for r in new if r.get(f))
        print(f"  {f:11} {cnt:5} из {len(new)}")
    ids = Counter(r.get("anl_id") for r in new if r.get("anl_id"))
    names = {}
    for r in new:
        if r.get("anl_id"):
            names.setdefault(r["anl_id"], set()).add(norm(r.get("anl")))
    multi = {k: v for k, v in names.items() if len(v) > 1}
    print(f"  разных anl_id {len(ids)}; один id — разные написания ФИО: {len(multi)}")
    cnames = {}
    for r in new:
        if r.get("cli_id"):
            cnames.setdefault(r["cli_id"], set()).add(norm(r.get("cli")))
    cmulti = {k: v for k, v in cnames.items() if len(v) > 1}
    print(f"  разных cli_id {len(cnames)}; один id — разные написания ФИО: {len(cmulti)}")
    for v in list(cmulti.values())[:5]:
        print("    ", " | ".join(sorted(v)))
    par = [r.get("parent") for r in new if r.get("parent")]
    print(f"  parent ссылается на обращение из этой же выгрузки: {sum(1 for p in par if p in n)} из {len(par)}")

    print("\n5. Табличные части (строк с частью / всего строк части / неверное число колонок)")
    ncol = {"tab_trud": 2, "tab_status": 4, "tab_sla": 5, "tab_rate": 5, "tab_chat": 3}
    for t in TABS:
        have = [r for r in new if r.get(t)]
        total = sum(len(r[t]) for r in have)
        wrong = sum(1 for r in have for row in r[t] if not isinstance(row, list) or len(row) != ncol[t])
        print(f"  {t:11} {len(have):5} строк, {total:6} записей, кривых {wrong}")
    mism = [r["id"] for r in new if r.get("tab_trud")
            and abs(sum(float(x[1]) for x in r["tab_trud"]) - float(r.get("AmountTrud") or 0)) > 0.05]
    no_trud = [r["id"] for r in new if float(r.get("AmountTrud") or 0) > 0 and not r.get("tab_trud")]
    print(f"  tab_trud: сумма ≠ AmountTrud у {len(mism)} {mism[:5]}; AmountTrud > 0 без tab_trud у {len(no_trud)} {no_trud[:5]}")
    rates = Counter(row[1] for r in new for row in (r.get("tab_rate") or []) if len(row) > 1)
    if rates:
        print("  tab_rate, оценки:", ", ".join(f"{k} — {v}" for k, v in rates.most_common()))
    solved = [r for r in new if norm(r.get("st")) in SOLVED]
    if solved:
        rated = sum(1 for r in solved if r.get("tab_rate"))
        print(f"  решённые с оценкой: {rated} из {len(solved)}")
    sla = [r for r in solved if r.get("tab_sla")]
    if sla:
        hrs = sorted(sum(float(x[2]) for x in r["tab_sla"] if len(x) > 3 and not x[3]) / 3600 for r in sla)
        print(f"  tab_sla, решённые: {len(sla)}; медиана суммы секунд без пауз — {hrs[len(hrs) // 2]:.1f} ч")

    print("\nИТОГ:", "РАСХОЖДЕНИЯ в базовой части — см. строки с «!»" if bad else "базовая часть совпала")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Запуск: py tools\\compare_dumps_v1.py старая.json новая.json")
    sys.exit(main(sys.argv[1], sys.argv[2]))
