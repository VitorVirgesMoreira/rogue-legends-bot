"""Read-only live validation: connection, package, PNG, crop, OCR and template scores.

python -m tools.check_emulator --provider google_play_games --ocr
Never sends taps, launches levels or completes account setup.
"""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import cv2

from roguebot import config, labels
from roguebot.device import Device
from roguebot.diagnostics import inspect_emulator
from roguebot.providers import PROVIDERS, create_provider
from roguebot.request import RunRequest
from roguebot.screens import Mode, parse_lobby, footer_visible
from roguebot.vision import Ocr


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=PROVIDERS, default="google_play_games")
    parser.add_argument("--adb", default="")
    parser.add_argument("--serial", default="")
    parser.add_argument("--mumu-folder", default="")
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("captures/emulator_check"))
    args = parser.parse_args()
    request = RunRequest(Mode.NORMAL, None, provider=args.provider, adb_path=args.adb,
                         device_serial=args.serial, mumu_folder=args.mumu_folder)
    status = inspect_emulator(request)
    provider = create_provider(request)
    device = Device(status.serial, adb=provider.adb)
    raw = device.capture_raw()
    normalized = device.viewport.normalize(raw)
    args.output.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.output / "raw.png"), raw)
    cv2.imwrite(str(args.output / "normalized.png"), normalized)
    report = {"provider": args.provider, "serial": status.serial, "installed": status.installed,
              "viewport": asdict(device.viewport), "normalized_size": list(config.SCREEN_SIZE)}
    if args.ocr:
        ocr = Ocr()
        reading = ocr.read_result(normalized)
        texts, scores = reading.texts, reading.scores
        labels.set_language(None)
        lobby = parse_lobby(texts)
        report.update(language=labels.detect_language(texts), texts=[asdict(t) for t in texts],
                      ocr_confidence_min=min(scores) if scores else None,
                      ocr_confidence_mean=sum(scores) / len(scores) if scores else None,
                      footer_visible=footer_visible(normalized),
                      lobby=None if lobby is None else {"mode": lobby.mode.value, "level": lobby.level_title,
                          "energy": lobby.energy, "start_reference": lobby.start_button.center,
                          "start_device": device.viewport.to_device(*lobby.start_button.center)})
        report["template_scores"] = {}
        for name in ("close_x", "back_arrow", "tutorial_hand"):
            template = cv2.imread(str(Path(__file__).parent.parent / "roguebot/templates" / f"{name}.png"))
            report["template_scores"][name] = float(cv2.matchTemplate(normalized, template, cv2.TM_CCOEFF_NORMED).max())
    report_path = args.output / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "texts"}, ensure_ascii=True, indent=2))
    print(f"Saved raw.png, normalized.png and report.json in {args.output}")


if __name__ == "__main__":
    main()
