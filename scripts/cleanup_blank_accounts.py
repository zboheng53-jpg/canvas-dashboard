"""Run the conservative 90-day blank-account cleanup from a daily timer."""
import json
import auth


if __name__ == "__main__":
    print(json.dumps({"deleted": auth.purge_blank_inactive_accounts()}, ensure_ascii=False))
