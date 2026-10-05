# ----------------------------------------------------------------------
# Заглушка google.colab для стенда самопроверки (examples/selftest_v5)
# ЧТО: окно загрузки отдаёт файлы из переменной окружения NB_UPLOAD (пути через «;»), скачивание запоминается,
#      Диск «монтируется» в рабочую папку прогона, ключи — фиктивные (сеть стенду не нужна).
# ----------------------------------------------------------------------
import os


class _Files:
    downloaded = []

    def upload(self):
        out = {}
        for p in filter(None, os.environ.get("NB_UPLOAD", "").split(";")):
            out[os.path.basename(p)] = open(p, "rb").read()
        print(f"[стенд] окно загрузки: {list(out)}")
        return out

    def download(self, p):
        _Files.downloaded.append(p)


class _Userdata:
    def get(self, key):
        return "stand-key-" + key


class _Drive:
    def mount(self, path, force_remount=False):
        os.makedirs(os.path.join(path, "MyDrive"), exist_ok=True)


class _Auth:
    def authenticate_user(self):
        pass


files, userdata, drive, auth = _Files(), _Userdata(), _Drive(), _Auth()
