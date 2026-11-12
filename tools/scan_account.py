"""Inspect the account, optionally applying observed fields to the bot settings."""

import argparse
from dataclasses import asdict
import json

from roguebot import settings
from roguebot.account_scan import scan_account
from roguebot.account_state import save_snapshot
from roguebot.combat_context import Loadout
from roguebot.request import RunRequest
from roguebot.screens import Mode


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider",choices=("mumu","google_play_games"),default="google_play_games")
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    saved=settings.load()
    connection=saved.get("provider_connections",{}).get(args.provider,{})
    request=RunRequest(Mode.NORMAL,None,provider=args.provider,mumu_folder=saved.get("mumu_folder",""),
                       adb_path=connection.get("adb_path",""),device_serial=connection.get("device_serial",""))
    result=scan_account(request,progress=lambda name:print("Reading:",name,flush=True))
    save_snapshot(result)
    if args.apply:
        loadout,facts=result.merge(Loadout.from_dict(saved.get("loadout",{})),saved.get("planner_facts",{}),
                                   previous_account=saved.get("scanned_account",""))
        settings.save({"loadout":asdict(loadout),"planner_facts":facts,"scanned_account":result.account,
                       "build_profile":result.profile,"strategy":result.strategy})
    print(json.dumps(asdict(result),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
