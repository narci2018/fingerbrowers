import uvicorn
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fingerprint Browser Engine API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8998, help="Port to bind (default: 8998)")
    args = parser.parse_args()

    print(f"==================================================")
    print(f"  Fingerprint Browser Engine (REST API & Control)")
    print(f"  API Docs : http://{args.host}:{args.port}/docs")
    print(f"==================================================")
    uvicorn.run("api.server:app", host=args.host, port=args.port, reload=False)
