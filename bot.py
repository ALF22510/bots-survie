#!/usr/bin/env python3
"""Bots de survie : simulation quotidienne (paper trading, argent fictif)
sur de vraies données (crypto via Binance, or via Yahoo Finance).
Réglages : config.json. Résultats : state.json (lu par index.html)."""
import bisect, datetime as dt, json, os, random, statistics, sys
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG, STATE = os.path.join(ROOT, "config.json"), os.path.join(ROOT, "state.json")
UA = {"User-Agent": "Mozilla/5.0"}


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def utc_day(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


def D(s):
    return dt.date.fromisoformat(s)


# ---------- Données réelles ----------
def fetch_binance(symbol):
    # data-api.binance.vision : données publiques, non bloquées depuis les serveurs GitHub
    for host in ("https://data-api.binance.vision", "https://api.binance.com"):
        try:
            r = requests.get(host + "/api/v3/klines", headers=UA, timeout=20,
                             params={"symbol": symbol, "interval": "1d", "limit": 500})
            r.raise_for_status()
            return {utc_day(k[0] / 1000): float(k[4]) for k in r.json()}
        except Exception as e:
            print("Binance", host, "échec :", e)
    return None


def fetch_yahoo(symbol):
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}",
                             headers=UA, timeout=20, params={"range": "2y", "interval": "1d"})
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            closes = res["indicators"]["quote"][0]["close"]
            return {utc_day(t): float(c) for t, c in zip(res["timestamp"], closes) if c is not None}
        except Exception as e:
            print("Yahoo", host, symbol, "échec :", e)
    return None


def fetch_asset(a):
    data = (fetch_binance if a["source"] == "binance" else fetch_yahoo)(a["symbol"])
    if not data and a.get("fallback"):
        data = fetch_yahoo(a["fallback"])
    return data


# ---------- Bots ----------
def random_genes(cfg, names):
    return dict(asset=random.choice(names), kind=random.choice(["mom", "rev"]),
                lb=random.randint(2, 30), thr=round(random.uniform(0, 0.03), 4),
                risk=round(random.uniform(0.1, cfg["max_risk"]), 2),
                sl=round(random.uniform(0.02, 0.12), 3))


def mutate(g, cfg, names):
    s = cfg["mutation"] / 0.2  # 0.2 = mutation « normale »
    g = dict(g)
    g["lb"] = int(min(60, max(2, g["lb"] + round(random.uniform(-3, 3) * s))))
    g["thr"] = round(min(0.05, max(0, g["thr"] + random.uniform(-.005, .005) * s)), 4)
    g["risk"] = round(min(cfg["max_risk"], max(0.05, g["risk"] + random.uniform(-.1, .1) * s)), 2)
    g["sl"] = round(min(0.2, max(0.01, g["sl"] + random.uniform(-.02, .02) * s)), 3)
    if random.random() < cfg["mutation"] * 0.25:
        g["asset"] = random.choice(names)
    if random.random() < cfg["mutation"] * 0.15:
        g["kind"] = "rev" if g["kind"] == "mom" else "mom"
    return g


def make_bot(genes, gen, born, state, cfg):
    state["next_id"] += 1
    c = cfg["start_capital"]
    return dict(genes, id=state["next_id"], gen=gen, born=born, E=c, peak=c, ws=c,
                neg=0, age=0, pos=0, entry=0)


def asset_view(prices):
    v = {}
    for n, p in prices.items():
        ds = sorted(p)
        v[n] = (ds, [p[x] for x in ds], {x: i for i, x in enumerate(ds)})
    return v


def price_asof(view, n, d):
    ds, cl, _ = view[n]
    i = bisect.bisect_right(ds, d) - 1
    return cl[max(i, 0)]


def step_day(state, cfg, view, d):
    """Une journée : on applique le rendement du jour aux positions ouvertes,
    puis chaque bot décide (à la clôture, sans regarder le futur)."""
    for b in state["bots"]:
        ds, cl, idx = view[b["asset"]]
        i = idx.get(d)
        if i is None:
            continue
        if b["pos"] and i > 0:
            b["E"] *= 1 + b["risk"] * (cl[i] / cl[i - 1] - 1)
        b["peak"] = max(b["peak"], b["E"])
        if i < b["lb"]:
            continue
        m, t = cl[i] / cl[i - b["lb"]] - 1, b["thr"]
        if b["pos"]:
            lost = cl[i] / b["entry"] - 1 < -b["sl"]
            out = m < -t if b["kind"] == "mom" else m > 0
            if lost or out:
                b["pos"] = 0
                b["E"] *= 1 - cfg["fee"] * b["risk"]
        else:
            go = m > t if b["kind"] == "mom" else m < -max(t, 0.01)
            if go:
                b["pos"], b["entry"] = 1, cl[i]
                b["E"] *= 1 - cfg["fee"] * b["risk"]


def week_check(state, cfg, d, names):
    state["weeks"] += 1
    rule, dead = cfg["death_rule"], []
    for b in state["bots"]:
        b["age"] += 1
        wr = b["E"] / b["ws"] - 1
        state["wk_total"] += 1
        state["wk_hits"] += wr >= cfg["weekly_target"]
        b["neg"] = b["neg"] + 1 if wr < 0 else 0
        b["ws"] = b["E"]
        why = None
        if rule == "drawdown" and b["E"] < b["peak"] * (1 - cfg["max_drawdown"]):
            why = "perte de %d %% depuis le pic" % round(cfg["max_drawdown"] * 100)
        elif rule == "two_negative_weeks" and b["neg"] >= 2:
            why = "2 semaines négatives"
        elif rule == "any_negative_week" and wr < 0:
            why = "semaine négative"
        if why:
            dead.append((b, why))
    deadids = {b["id"] for b, _ in dead}
    alive = sorted((b for b in state["bots"] if b["id"] not in deadids), key=lambda b: -b["E"])
    parents = alive[:cfg["top_k"]]
    for b, why in dead:
        state["deaths"] += 1
        state["log"].append(dict(d=d, id=b["id"], asset=b["asset"], kind=b["kind"],
                                 E=round(b["E"], 1), age=b["age"], why=why))
        if parents:
            p = random.choice(parents)
            nb = make_bot(mutate({k: p[k] for k in ("asset", "kind", "lb", "thr", "risk", "sl")},
                                 cfg, names), p["gen"] + 1, d, state, cfg)
        else:
            nb = make_bot(random_genes(cfg, names), 1, d, state, cfg)
        state["bots"][state["bots"].index(b)] = nb
    state["log"] = state["log"][-200:]


def snapshot(state, view, d):
    es = sorted(b["E"] for b in state["bots"])
    mk = {n: round(price_asof(view, n, d) / state["base"][n] * 100, 2) for n in view}
    state["history"].append(dict(d=d, best=round(es[-1], 2),
                                 med=round(statistics.median(es), 2), mkt=mk))
    state["history"] = state["history"][-500:]


def main():
    cfg, state = load(CFG), load(STATE)
    names = list(cfg["assets"])
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    prices = state["prices"] if state else {n: {} for n in names}
    for n, a in cfg["assets"].items():
        data = fetch_asset(a)
        if data:  # on ignore la journée en cours (bougie pas terminée)
            prices.setdefault(n, {}).update({k: v for k, v in data.items() if k < today})
        else:
            print("ATTENTION : pas de données pour", n)
    if any(not prices.get(n) for n in names):
        sys.exit("Données manquantes : arrêt.")
    for n in prices:
        prices[n] = dict(sorted(prices[n].items())[-600:])
    view = asset_view(prices)
    dates = sorted({d for p in prices.values() for d in p})

    if not state:  # premier lancement
        bf = int(cfg.get("backfill_days", 0))
        start = dates[max(0, len(dates) - 1 - bf)]
        state = dict(prices=prices, last_date=start, anchor=start, wk=0, weeks=0, deaths=0,
                     wk_hits=0, wk_total=0, next_id=0, history=[], log=[], bots=[],
                     live_from=dates[-1], base={n: price_asof(view, n, start) for n in names})
        state["bots"] = [make_bot(random_genes(cfg, names), 1, start, state, cfg)
                         for _ in range(cfg["population"])]
        snapshot(state, view, start)
        print("Départ des bots au", start, "(backfill : %d jours)" % bf)
    state["prices"] = prices

    # le nombre de bots suit la config
    while len(state["bots"]) < cfg["population"]:
        state["bots"].append(make_bot(random_genes(cfg, names), 1, state["last_date"], state, cfg))
    if len(state["bots"]) > cfg["population"]:
        state["bots"] = sorted(state["bots"], key=lambda b: -b["E"])[:cfg["population"]]

    for d in [x for x in dates if x > state["last_date"]]:
        w = (D(d) - D(state["anchor"])).days // 7
        if w > state["wk"]:
            week_check(state, cfg, d, names)
            state["wk"] = w
        step_day(state, cfg, view, d)
        snapshot(state, view, d)
        state["last_date"] = d

    state["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    save(STATE, state)
    best = max(state["bots"], key=lambda b: b["E"])
    print("Jour %s | semaines %d | morts %d | meilleur %.1f (%s)" % (
        state["last_date"], state["weeks"], state["deaths"], best["E"], best["asset"]))


if __name__ == "__main__":
    main()
