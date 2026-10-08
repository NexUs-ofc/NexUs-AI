import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from app.core.receipt_agent import scan_receipt

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).with_name("nota_exemplo.png"))
    t = time.time()
    result = scan_receipt(Path(path).read_bytes())
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    print(f"\n{time.time() - t:.2f}s", file=sys.stderr)
