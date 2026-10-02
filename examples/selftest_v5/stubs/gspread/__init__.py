# ----------------------------------------------------------------------
# Заглушка gspread для стенда самопроверки (examples/selftest_v5)
# ЧТО: таблица «Logs» в памяти — ячейка 8 (лог в Sheets) пишет в неё строки, стенд потом проверяет, что записалось.
# ----------------------------------------------------------------------


class exceptions:
    class WorksheetNotFound(Exception):
        pass


class _Sheet:
    def __init__(self, title):
        self.title, self.rows = title, []

    def append_row(self, row):
        self.rows.append(list(row))


class _Book:
    def __init__(self):
        self.sheets = {}

    def worksheet(self, title):
        if title not in self.sheets:
            raise exceptions.WorksheetNotFound(title)
        return self.sheets[title]

    def add_worksheet(self, title, rows, cols):
        self.sheets[title] = _Sheet(title)
        return self.sheets[title]


BOOK = _Book()


def authorize(creds):
    class _Client:
        def open(self, name):
            if name != "Logs":
                raise Exception(f"SpreadsheetNotFound: {name}")
            return BOOK
    return _Client()
