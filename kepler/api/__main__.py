"""Entrypoint del dashboard: python -m kepler.api"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("DASHBOARD_PORT", "8080"))
    uvicorn.run("kepler.api.app:app", host="0.0.0.0", port=port, log_level="warning")
