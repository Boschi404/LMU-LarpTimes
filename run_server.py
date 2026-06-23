"""Run the LMU Pit Strategist FastAPI server."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("web.server:app", host="127.0.0.1", port=8000, reload=True)
