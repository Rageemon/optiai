# Adaptive Logic Engine

A neuro-symbolic optimization platform for solving complex combinatorial problems through intelligent conversational interfaces.

## Overview

This is a full-stack application that combines LLM-powered constraint extraction with specialized optimization solvers. Users interact through a chat interface to solve real-world problems in routing, scheduling, packing, and more.

## Features

- 🤖 **Chat-based Optimization** – Natural language problem description via LLM integration
- 🗺️ **Map Routing** – Route optimization with OSM/Nominatim integration
- 📊 **Scheduling** – Job shop, project scheduling, workforce timetables
- 📦 **Bin Packing** – Knapsack and cutting stock problems
- 💾 **Session Management** – Persistent optimization sessions with draft support
- 🚀 **REST API** – Fully documented OpenAPI endpoints

## Tech Stack

**Backend:**
- FastAPI with async/await
- Python 3.9+
- LangChain for LLM integration
- Specialized optimization libraries

**Frontend:**
- Next.js 15+ with TypeScript
- Leaflet for map visualization
- Real-time UI components

## Quick Start

### Backend Setup

```bash
cd adaptive-logic-engine
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:3000

## Project Structure

```
adaptive-logic-engine/
├── app/
│   ├── api/              # REST endpoints
│   ├── core/             # LLM, dispatcher, session logic
│   ├── models/           # Pydantic schemas
│   └── solvers/          # Optimization algorithms
│       ├── scheduling/
│       ├── routing/
│       ├── packing/
│       └── map_routing/
└── main.py              # FastAPI app entry point

frontend/
├── src/
│   ├── app/             # Pages (routing, scheduling, packing)
│   ├── components/      # Reusable UI components
│   └── lib/            # API client
```

## Deployment

Deployed on Render. Make sure to set host binding:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## How to Use

### 1. Chat-based Optimization
Start the conversation at http://localhost:3000 and describe your problem:
```
"I need to schedule 20 employees across 5 days with specific constraints..."
```
The LLM extracts constraints and routes to the appropriate solver.

### 2. Direct Solver API
Use `/api/solve` for structured problems:
```json
{
  "algo_id": "job_shop_scheduling",
  "inputs": {
    "jobs": [...],
    "machines": [...],
    "constraints": [...]
  }
}
```

### 3. Interactive Visualizations
- **Map Routing**: View optimized routes on Leaflet maps
- **Scheduling**: Gantt charts + timetable grids
- **Packing**: Visual bin allocation

## API Endpoints

- `POST /api/chat` – Conversational optimization
- `POST /api/solve` – Structured solver invocation
- `POST /api/solve/substitute` – Teacher substitution solver  
- `GET /api/health` – Health check

All endpoints documented at `/docs` (Swagger UI)

## Supported Problem Types

| Type | Module | Example |
|------|--------|---------|
| Job Shop Scheduling | `scheduling/job_shop.py` | Manufacturing optimization |
| Workforce Scheduling | `scheduling/workforce.py` | Employee timetables |
| Vehicle Routing | `routing/node_routing.py` | Delivery route optimization |
| Map-based Routing | `map_routing/osm_router.py` | Real-world navigation |
| Bin Packing | `packing/bin_packing.py` | Container optimization |
| Knapsack | `packing/knapsack.py` | Resource allocation |

## Configuration

### Backend (.env)
```env
OPENAI_API_KEY=your_key_here
LLM_MODEL=gpt-4
SOLVER_TIMEOUT=300
```

### Frontend (.env.local)
```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

## Development

### Adding a New Solver
1. Create solver class in `app/solvers/`
2. Register in `ALGO_BY_ID` in `core/dispatcher.py`
3. Add endpoint in `api/routes.py`

### Testing
```bash
# Run backend tests
pytest tests/

# Test API endpoints
curl http://localhost:8000/api/health
```

## Performance Tips

- Use caching for repeated optimizations (session store)
- Adjust `SOLVER_TIMEOUT` based on problem complexity
- For large datasets, use batch processing via `/api/solve`

## Troubleshooting

**Port already in use:**
```bash
lsof -i :8000  # Find process
kill -9 <PID>  # Kill it
```

**CORS issues:**
Check `CORSMiddleware` configuration in `main.py`

**LLM timeout:**
Increase `SOLVER_TIMEOUT` or check API key validity

## Demo

> [📹 Watch Demo Video Here](https://www.youtube.com/watch?v=demo) *(See instructions below)*

### Uploading Your Demo Video

Since GitHub has a 100MB file limit, use one of these approaches:

#### Option 1: YouTube (Recommended)
1. Upload video to YouTube (unlisted or public)
2. Link in README:
   ```markdown
   [📹 Watch Demo](https://youtube.com/watch?v=your_video_id)
   ```

#### Option 2: GitHub Releases
1. Go to Releases → Create New Release
2. Upload `.mp4` as an attachment
3. Link in README:
   ```markdown
   [📹 Download Demo](https://github.com/yourusername/optiai/releases/download/v1.0.0/demo.mp4)
   ```

#### Option 3: Git LFS (Large File Storage)
```bash
git lfs install
git lfs track "*.mp4"
git add .gitattributes demo.mp4
git commit -m "Add demo video"
git push
```

---

## License

MIT

## Author

Built as a neuro-symbolic optimization engine combining LLM intelligence with classical optimization solvers.
