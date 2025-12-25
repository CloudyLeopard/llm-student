# Teaching Simulator

## Play Online
Visit https://teaching-simulator.onrender.com/

## Local Deploy
Or if that doesn't work, here's the local option

Requirements
- **Docker Desktop** installed and running.
- An **OpenAI API Key**.

### 1. Set your API Key

You must have the key set in your terminal session before starting Docker.

**Mac/Linux:**

```bash
export OPENAI_API_KEY="sk-proj-..."

```

**Windows (PowerShell):**

```powershell
$env:OPENAI_API_KEY="sk-proj-..."

```

### 2. Run the App

Run this

```bash
docker compose up --build

```

Open your browser to:
👉 **http://localhost:8000**

Other commands
* **Stop the app:** Press `Ctrl+C` in the terminal.
* **Run in background:** `docker compose up -d`
* **Stop background app:** `docker compose down`

