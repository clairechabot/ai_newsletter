from briefing.config import load_config
from briefing.pipeline import run

if __name__ == "__main__":
    cfg = load_config("config.yaml")
    run(cfg, history_path="history.json")
