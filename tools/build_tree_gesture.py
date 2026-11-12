"""Rebuild the bundled pinch helper. Build tools stay under ignored build/.

Uses Eclipse's Java compiler, Google's D8 and Android API stubs, and an Azul
JRE. The desktop bot needs only the resulting assets/tree-gesture.jar.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "build/tree-gesture"


def fetch(url, path):
    if not path.is_file():
        temporary = path.with_suffix(".download")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as target:
            while data := response.read(1024 * 1024):
                target.write(data)
        temporary.replace(path)
    return path


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    # Pinned official Azul Zulu portable JRE; no system installation or PATH edits.
    jre_url = "https://cdn.azul.com/zulu/bin/zulu17.70.113-ca-jre17.0.21.0.3-win_x64.zip"
    jre_hash = "c5a32fe9b1d2ff07ac4991b57a72d707ad97d54a9cc1bd2f8f005bfd1498d460"
    urls = [(jre_url, WORK / "jre.zip"),
            ("https://repo.maven.apache.org/maven2/org/eclipse/jdt/ecj/3.38.0/ecj-3.38.0.jar", WORK / "ecj.jar"),
            ("https://dl.google.com/dl/android/maven2/com/android/tools/r8/8.3.37/r8-8.3.37.jar", WORK / "r8.jar"),
            ("https://repo.maven.apache.org/maven2/com/google/android/android/4.1.1.4/android-4.1.1.4.jar", WORK / "android.jar")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda item: fetch(*item), urls))
    if hashlib.sha256((WORK / "jre.zip").read_bytes()).hexdigest() != jre_hash:
        raise ValueError("JRE checksum mismatch")
    jre = WORK / "jre"
    if not jre.exists():
        with zipfile.ZipFile(WORK / "jre.zip") as archive:
            for name in archive.namelist():
                if not (jre / name).resolve().is_relative_to(jre.resolve()):
                    raise ValueError("Invalid archive path")
            archive.extractall(jre)
    java = next(jre.glob("*/bin/java.exe"))
    classes = WORK / "classes"
    classes.mkdir(exist_ok=True)
    source = ROOT / "tools/android/TreeGesture.java"
    subprocess.run([str(java), "-jar", str(WORK / "ecj.jar"), "-8", "-classpath", str(WORK / "android.jar"),
                    "-d", str(classes), str(source)], check=True)
    output = ROOT / "roguebot/assets/tree-gesture.jar"
    subprocess.run([str(java), "-cp", str(WORK / "r8.jar"), "com.android.tools.r8.D8", "--release", "--min-api", "21",
                    "--lib", str(WORK / "android.jar"), "--output", str(output),
                    str(classes / "com/roguebot/input/TreeGesture.class")], check=True)
    output.with_suffix(".json").write_text(json.dumps({
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "jar_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "main_class": "com.roguebot.input.TreeGesture", "min_api": 21,
    }, indent=2) + "\n", encoding="utf-8")
    print("Built", output, output.stat().st_size, "bytes; sha256", hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
