from harness import *
from fastapi import FastAPI
from fastapi.testclient import TestClient
mini = FastAPI()
@mini.get("/f/{d}/{p:path}")
def f(d: str, p: str): return {"d": d, "p": p}
with TestClient(mini) as t:
    print("mini TestClient %2520 ->", t.get("/f/x/a%2520b.png").json(), " %20 ->", t.get("/f/x/a%20b.png").json())
