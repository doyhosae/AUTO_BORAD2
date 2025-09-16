#!/usr/bin/env python3
import csv, sys, math, argparse, hashlib, os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

def load_yaml(path):
    if yaml is None:
        raise RuntimeError("PyYAML not available; please install pyyaml or provide JSON instead.")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def parse_tick(s: str) -> timedelta:
    s = s.strip().lower()
    if s.endswith("h"):
        hours = float(s[:-1])
        return timedelta(hours=hours)
    if s.endswith("m"):
        minutes = float(s[:-1])
        return timedelta(minutes=minutes)
    if s.endswith("s"):
        seconds = float(s[:-1])
        return timedelta(seconds=seconds)
    raise ValueError(f"Unsupported tick_duration: {s} (use like '1h', '30m', '15s')")

def rng_from_seed(seed_int: int):
    # Simple LCG for deterministic ints without numpy
    class RNG:
        def __init__(self, seed):
            self.state = (seed & 0xFFFFFFFFFFFFFFFF) or 0xDEADBEEFCAFEBABE
        def randint_inclusive(self, a: int, b: int) -> int:
            # advance state
            self.state = (6364136223846793005 * self.state + 1) & 0xFFFFFFFFFFFFFFFF
            # map to range [a,b]
            span = b - a + 1
            return a + int((self.state / 2**64) * span)
        def rand(self) -> float:
            self.state = (6364136223846793005 * self.state + 1) & 0xFFFFFFFFFFFFFFFF
            return self.state / 2**64
    return RNG(seed_int)

def seed_for_post(global_seed: int, post_id: str, seed_offset: int) -> int:
    h = hashlib.sha256(f"{global_seed}|{post_id}|{seed_offset}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False)

def normalize_weights(wdict: dict) -> dict:
    # keys are strings "0".."23" ; values floats
    total = sum(float(v) for v in wdict.values())
    if total <= 0:
        # uniform
        return {str(h): 1.0/24 for h in range(24)}
    return {str(k): float(v)/total for k,v in wdict.items()}

def mean_weight_norm() -> float:
    # when normalized to sum=1 across 24 hours, mean is 1/24
    return 1.0/24.0

def isoformat_tz(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def simulate(posts_path: str, stages_path: str, engine_path: str, out_path: str, seed: int):
    # Load configs
    stages_cfg = load_yaml(stages_path)
    engine_cfg = load_yaml(engine_path)

    tz = ZoneInfo(engine_cfg.get("timezone", "UTC"))
    tick_cfg = engine_cfg.get("tick_duration", "1h")
    tick_fixed = None
    tick_min = None
    tick_max = None
    if isinstance(tick_cfg, dict):
        tick_min = parse_tick(str(tick_cfg.get("min", "1h")))
        tick_max = parse_tick(str(tick_cfg.get("max", "1h")))
        if tick_max < tick_min:
            tick_min, tick_max = tick_max, tick_min
    else:
        tick_fixed = parse_tick(str(tick_cfg))
    inc_min = int(engine_cfg["increment"]["min"])
    inc_max = int(engine_cfg["increment"]["max"])
    weights_norm = normalize_weights(engine_cfg["hourly_weights"])
    max_hours = int(engine_cfg.get("limits", {}).get("max_hours", 336))
    system_hour_cap = engine_cfg.get("limits", {}).get("system_hour_cap", None)
    if system_hour_cap is not None:
        system_hour_cap = int(system_hour_cap)

    stage_map = stages_cfg["stages"]

    # Read posts
    rows = []
    with open(posts_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    # Prepare writer
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    out_f = open(out_path, "w", encoding="utf-8", newline="")
    writer = csv.writer(out_f)
    writer.writerow(["No", "post_id", "views_inc", "cum_views", "datetime"])

    MW = mean_weight_norm()
    row_no = 1

    for r in rows:
        post_id = r["post_id"]
        stage = str(r["stage"]).strip()
        start_dt = datetime.fromisoformat(r["start_datetime"])
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=tz)  # assume tz if missing
        seed_offset = int(r.get("seed_offset", 0))

        # RNG
        post_seed = seed_for_post(seed, post_id, seed_offset)
        rng = rng_from_seed(post_seed)

        # Target for this post
        stage_cfg = stage_map[stage]
        target_min = int(stage_cfg["views_min"])
        target_max = int(stage_cfg["views_max"])
        target = rng.randint_inclusive(target_min, target_max)

        cum = 0
        t = start_dt
        for k in range(max_hours):
            hour_local = t.astimezone(tz).hour
            w = weights_norm.get(str(hour_local), 1.0/24)
            base = rng.randint_inclusive(inc_min, inc_max)
            inc_raw = base * (w / MW)
            inc = int(math.floor(max(0.0, inc_raw)))
            if system_hour_cap is not None:
                inc = min(inc, system_hour_cap)
            remaining = target - cum
            if remaining <= 0:
                break
            # enforce bounds except when finishing with remaining < inc_min
            if remaining <= inc_min:
                inc = remaining
            else:
                inc = max(inc, inc_min)
                inc = min(inc, inc_max)
                inc = min(inc, remaining)
            if inc > 0:
                next_cum = cum + inc
                writer.writerow([row_no, post_id, inc, next_cum, isoformat_tz(t)])
                row_no += 1
                cum = next_cum
                if cum >= target:
                    break
            # 다음 간격 계산: 고정 간격 또는 범위 랜덤
            if tick_fixed is not None:
                step = tick_fixed
            else:
                span_seconds = (tick_max - tick_min).total_seconds()
                step_seconds = tick_min.total_seconds() + rng.rand() * span_seconds
                step = timedelta(seconds=int(step_seconds))
            t = t + step

    out_f.close()
    return out_path

# If run as a script inside this notebook environment, run once with sample data
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    posts_default = os.path.join(base_dir, "data/posts.csv")
    stages_default = os.path.join(base_dir, "config/stages.yml")
    engine_default = os.path.join(base_dir, "config/engine.yml")
    out_dir_default = os.path.join(base_dir, "out")
    ts_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_default = os.path.join(out_dir_default, f"simulated_{ts_name}.csv")

    parser.add_argument("--posts", default=posts_default, help=f"경로 미지정 시 기본값: {posts_default}")
    parser.add_argument("--stages", default=stages_default, help=f"경로 미지정 시 기본값: {stages_default}")
    parser.add_argument("--engine", default=engine_default, help=f"경로 미지정 시 기본값: {engine_default}")
    parser.add_argument("--seed", type=int, default=20250916, help="랜덤 시드(기본: 20250916)")
    parser.add_argument("--out", default=out_default, help="미지정 시 out/simulated_YYYYMMDD_HHMMSS.csv 자동 생성")
    args = parser.parse_args()
    simulate(args.posts, args.stages, args.engine, args.out, args.seed)
