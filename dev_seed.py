from __future__ import annotations
import os
from dotenv import load_dotenv
import db

load_dotenv()
GUILD_ID = os.getenv("GUILD_ID", "1524635551804686486")

def main() -> None:
    #...
    print("Run: python -m uvicorn server.api:app --port 3000")

if __name__ == "__main__":
    main()
