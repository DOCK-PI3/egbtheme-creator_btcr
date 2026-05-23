import requests
import tempfile
from packaging import version

REPO = "DOCK-PI3/egbtheme-creator_btcr"

def get_latest_release():
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()

    version_remote = data["tag_name"].lstrip("v")

    # buscamos el exe correcto
    for asset in data["assets"]:
        if asset["name"].lower().endswith(".exe"):
            return version_remote, asset["browser_download_url"]

    raise RuntimeError("No se encontró ningún .exe en la release")


def hay_nueva_version(local, remoto):
    return version.parse(remoto) > version.parse(local)


def descargar_actualizacion(url):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".exe")
    r = requests.get(url, stream=True)
    for chunk in r.iter_content(chunk_size=8192):
        if chunk:
            tmp.write(chunk)
    tmp.close()
    return tmp.name