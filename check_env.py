# check_env.py
import os
from dotenv import load_dotenv
load_dotenv()
t = os.getenv("DISCORD_TOKEN")
print("¿Token cargado?:", t is not None)
print("Largo del token:", 0 if t is None else len(t))
print("Prefijo visible:", "" if t is None else repr(t[:12]))