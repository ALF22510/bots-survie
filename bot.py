#!/usr/bin/env python3
"""Bots de survie : paper trading (argent fictif) sur de vraies données
(crypto via Binance, or via Yahoo Finance), bougies de 1 minute à 1 jour.
Réglages : config.json. Résultats : state.json (lu par index.html).
À chaque lancement, le script traite TOUTES les bougies terminées depuis le
dernier lancement : un lancement toutes les 5 minutes suffit donc pour que les
bots décident à chaque bougie d'une minute, sans rien rater."""
import bisect, datetime as dt, json, os, random, statistics, sys, time
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG, STATE = os.path.join(ROOT, "config.json"), os.path.join(ROOT, "state.json")
UA = {"User-Agent": "Mozilla/5.0"}
STEP_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "1d": 1440}
LB = {"1m": (10, 240), "5m": (6, 144), "15m": (4, 96), "1h": (3, 72), "1d": (2, 30)}
Y_INT = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "60m", "1d": "1d"}
Y_RNG = {"1m": "5d", "5m": "1mo", "15m": "1mo", "1h": "6mo", "1d": "2y"}


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")


def T(s):
    return dt.datetime.fromisoformat(s)


# ---------- Données réelles ----------
def keyed(pairs, step_min):
    """(timestamp, clôture) -> {'AAAA-MM-JJTHH:MM': clôture}, bougies terminées seulement."""
    step, now, out = step_min * 60, time.time(), {}
    for ts, c in pairs:
        o = int(ts) - int(ts) % step
        if o + step <= now:
            out[iso(o)] = c
    return out


def fetch_binance(symbol, iv):
    # data-api.binance.vision : données publiques, non bloquées depuis les serveurs GitHub
    for host in ("https://data-api.binance.vision", "https://api.binance.com"):
        try:
            r = requests.get(host + "/api/v3/klines", headers=UA, timeout=20,
                             params={"symbol": symbol, "interval": iv, "limit": 1000})
            r.raise_for_status()
            return keyed([(k[0] / 1000, float(k[4])) for k in r.json()], STEP_MIN[iv])
        except Exception as e:
            print("Binance", host, "échec :", e)
    return None


def fetch_yahoo(symbol, iv):
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}",
                             headers=UA, timeout=20,
                             params={"range": Y_RNG[iv], "interval": Y_INT[iv]})
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            closes = res["indicators"]["quote"][0]["close"]
            return keyed([(t, float(c)) for t, c in zip(res["timestamp"], closes)
                          if c is not None], STEP_MIN[iv])
        except Exception as e:
            print("Yahoo", host, symbol, "échec :", e)
    return None


def fetch_asset(a, iv):
    data = (fetch_binance if a["source"] == "binance" else fetch_yahoo)(a["symbol"], iv)
    if not data and a.get("fallback"):
        data = fetch_yahoo(a["fallback"], iv)
    return data


# ---------- Bots ----------
def params(cfg):
    iv = cfg["interval"]
    sc = (STEP_MIN[iv] / 1440) ** 0.5  # les mouvements d'une bougie courte sont plus petits
    lo, hi = LB[iv]
    return sc, cfg.get("lb_min", lo), cfg.get("lb_max", hi), cfg["fee"] * 3


def random_genes(cfg, names):
    sc, lo, hi, f = params(cfg)
    return dict(asset=random.choice(names), kind=random.choice(["mom", "rev"]),
                lb=random.randint(lo, hi), thr=round(random.uniform(0, 0.03 * sc), 5),
                risk=round(random.uniform(0.1, cfg["max_risk"]), 2),
                sl=round(random.uniform(max(0.02 * sc, f), 0.12 * sc + f), 5))


def mutate(g, cfg, names):
    sc, lo, hi, f = params(cfg)
    s = cfg["mutation"] / 0.2  # 0.2 = mutation « normale »
    g = dict(g)
    st = max(1, round(hi * 0.1 * s))
    g["lb"] = int(min(hi * 2, max(lo, g["lb"] + random.randint(-st, st))))
    g["thr"] = round(min(0.05 * sc, max(0, g["thr"] + random.uniform(-.005, .005) * sc * s)), 5)
    g["risk"] = round(min(cfg["max_risk"], max(0.05, g["risk"] + random.uniform(-.1, .1) * s)), 2)
    g["sl"] = round(min(0.2 * sc + f, max(max(0.01 * sc, f),
                                         g["sl"] + random.uniform(-.02, .02) * sc * s)), 5)
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


def step_candle(state, cfg, view, d):
    """Une bougie : on applique son rendement aux positions ouvertes, puis chaque
    bot décide à la clôture (sans regarder le futur)."""
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
            go = m > t if b["kind"] == "mom" else m < -max(t, 0.01 * params(cfg)[0])
            if go:
                b["pos"], b["entry"] = 1, cl[i]
                b["E"] *= 1 - cfg["fee"] * b["risk"]


def period_check(state, cfg, d, names):
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
            why = "2 périodes négatives"
        elif rule == "any_negative_week" and wr < 0:
            why = "période négative"
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


def snapshot(state, view, d, cfg, force=False):
    h = state["history"]
    gap_min = max(STEP_MIN[cfg["interval"]], cfg.get("history_step_min", 15))
    if h and not force and (T(d) - T(h[-1]["d"])).total_seconds() / 60 < gap_min:
        return
    es = sorted(b["E"] for b in state["bots"])
    mk = {n: round(price_asof(view, n, d) / state["base"][n] * 100, 2) for n in view}
    h.append(dict(d=d, best=round(es[-1], 2), med=round(statistics.median(es), 2), mkt=mk))
    state["history"] = h[-1000:]


def main():
    cfg, state = load(CFG), load(STATE)
    iv, names = cfg["interval"], list(cfg["assets"])
    if iv not in STEP_MIN:
        sys.exit("interval doit être l'un de : " + ", ".join(STEP_MIN))
    # réinitialisation : changer reset_id (ou l'intervalle) dans config.json
    if state and (state.get("reset_id", 0) != cfg.get("reset_id", 0) or state.get("interval") != iv):
        print("Réinitialisation de l'expérience.")
        state = None
    prices = state["prices"] if state else {n: {} for n in names}
    for n, a in cfg["assets"].items():
        data = fetch_asset(a, iv)
        if data:
            prices.setdefault(n, {}).update(data)
        else:
            print("ATTENTION : pas de données pour", n)
    if any(not prices.get(n) for n in names):
        sys.exit("Données manquantes : arrêt.")
    for n in prices:
        prices[n] = dict(sorted(prices[n].items())[-1200:])
    view = asset_view(prices)
    dates = sorted({d for p in prices.values() for d in p})

    if not state:  # premier lancement
        n_back = int(float(cfg.get("backfill_days", 0)) * 1440 / STEP_MIN[iv])
        start = dates[max(0, len(dates) - 1 - n_back)]
        state = dict(prices=prices, last_ts=start, anchor=start, wk=0, weeks=0, deaths=0,
                     wk_hits=0, wk_total=0, next_id=0, history=[], log=[], bots=[],
                     live_from=dates[-1], interval=iv, reset_id=cfg.get("reset_id", 0),
                     base={n: price_asof(view, n, start) for n in names})
        state["bots"] = [make_bot(random_genes(cfg, names), 1, start, state, cfg)
                         for _ in range(cfg["population"])]
        snapshot(state, view, start, cfg, force=True)
        print("Départ des bots au", start, "(%d bougies simulées sur le passé)" % n_back)
    state["prices"] = prices

    while len(state["bots"]) < cfg["population"]:  # le nombre de bots suit la config
        state["bots"].append(make_bot(random_genes(cfg, names), 1, state["last_ts"], state, cfg))
    if len(state["bots"]) > cfg["population"]:
        state["bots"] = sorted(state["bots"], key=lambda b: -b["E"])[:cfg["population"]]

    period = float(cfg.get("period_days", 7)) * 86400
    new = [x for x in dates if x > state["last_ts"]]
    for d in new:
        w = int((T(d) - T(state["anchor"])).total_seconds() // period)
        if w > state["wk"]:
            period_check(state, cfg, d, names)
            state["wk"] = w
        step_candle(state, cfg, view, d)
        snapshot(state, view, d, cfg)
        state["last_ts"] = d

    state["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    save(STATE, state)
    best = max(state["bots"], key=lambda b: b["E"])
    print("%d nouvelles bougies | jusqu'à %s | périodes %d | morts %d | meilleur %.1f (%s)" % (
        len(new), state["last_ts"], state["weeks"], state["deaths"], best["E"], best["asset"]))


if __name__ == "__main__":
    main()
