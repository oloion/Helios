from helios.engine import run_scan

r = run_scan()
print("elapsed", r["meta"]["elapsedMs"])
print("score", r["score"])
print("identity", r["identity"])
for c in r["checks"]:
    print(f"{c['status']:5} {c['id']:12} {c['value']}")
