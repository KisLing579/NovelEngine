# AI Novel Generation System

**A state-driven, multi-agent narrative engine with human-in-the-loop story planning.**

[中文 README](README_zh.md)

Most LLMs can write a chapter. Maintaining a coherent story across dozens or hundreds of chapters is a different problem.

This project explores a structured approach to long-form fiction generation, separating story planning, text generation, review, and persistent world-state management.

Instead of asking an LLM to write an entire novel autonomously, the system proposes alternative story directions, lets the author make creative decisions, and updates the fictional world only after a chapter has been reviewed and approved.

Built with Flask and Vue, the current implementation includes the core story-state workflow, Story Dashboard, and Phase 3 Narrative Planning. It uses `MockLLMProvider` by default, so no API key is required to try the workflow.

## Key Features

- **Multi-Agent Workflow:** Separate responsibilities for orchestration, chapter generation, review, and state updates.
- **Persistent World State:** Track characters, inventory, locations, world rules, and story outlines across chapters.
- **Human-in-the-Loop Approval:** Generated drafts do not modify the official story state until the author approves them.
- **Narrative Planning:** Generate three alternative story directions—Progression, Escalation, and Revelation—and let the author choose before generating a chapter.
- **Story Dashboard:** Visualize chapter progress, drafts, review feedback, committed world state, and recent state changes.
- **Snapshots and Rollback:** Restore previous story states when a narrative direction does not work out.
- **Pluggable LLM Providers:** Support mock testing and OpenAI-compatible model APIs.
- **Project Library:** Create isolated projects, browse saved stories, and load a project to resume its drafts, plans, and world state.

## Architecture

The original multi-agent architecture establishes the foundation for story-state management and controlled chapter generation.

```text
Director
   ↓
Generator
   ↓
Review
   ↓
Human Approval
   ↓
StateUpdate
   ↓
Committed World State
   ├── Roles
   ├── Inventory
   ├── Maps
   └── Lore
```

The Narrative Planning layer extends this workflow by separating the decision about *what happens next* from the generation of the chapter itself.

```text
Committed World State
        +
Current Chapter Goal
        +
Previous Story
        ↓
    Story Planner
        ↓
 Three Candidate Branches
        ↓
   Human Selection
        ↓
 Selected Story Plan
        ↓
     Generator
        ↓
 Review → Approval
        ↓
   State Update
```

## Getting Started

Run the following commands from the `novel_engine` directory in Windows PowerShell. Install Miniconda or Anaconda first; the frontend also requires Node.js with npm.

Create and activate a dedicated Python 3.13 environment before installing dependencies:

```powershell
conda create -n novel_engine python=3.13 pip -y
conda activate novel_engine
```

Create the environment only once. In a new terminal, run `conda activate novel_engine` before running backend commands.

Start the backend:

```powershell
python -m pip install -r backend/requirements.lock.txt
python -m backend.app
```

In another terminal, also starting from `novel_engine`, start the frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The backend listens at http://127.0.0.1:5000.

## Using the Story Dashboard

### Creating and Loading Projects

Use **新建项目** (New Project) in the project library, enter a project name and premise, and click **创建项目** (Create Project). Each new project is stored in its own `backend/data/<project_id>/` directory, including its `state.json`, chapter files, snapshots, and world-state exports. Project IDs are unique, so projects with the same display name remain separate. `NOVEL_DATA_DIR`, when configured, replaces `backend/data` as the library root.

The project history shows names, premise previews, approved chapter counts, saved draft counts, and last-save times. Click **加载项目** (Load Project) to resume a story. Switching preserves saved drafts and narrative plans. The server remembers the last loaded project across restarts; open dashboard tabs send an explicit project ID so another tab's selection cannot redirect their operations.

Existing immediate subdirectories containing `state.json` are discovered automatically. An older project stored directly in the data root appears as **旧版项目（data 根目录）** and remains loadable without moving or overwriting its files. Unreadable projects are marked unavailable in the library.

Project APIs:

- `GET /api/projects`: list saved projects and the last selected project ID.
- `POST /api/project/init`: create a new project with `{ "name": "Story title", "prompt": "Story premise" }`; returns `project_id`. The name is optional for existing API clients and defaults to a premise excerpt. Repeated calls create separate projects.
- `POST /api/project/load`: load a saved project with `{ "project_id": "..." }`.
- Existing chapter, planning, rollback, status, dashboard, and export APIs accept an `X-Project-ID` header (URL-encoded for non-ASCII IDs), or a `project_id` query parameter. Without either, they use the last selected project. The dashboard response also includes `project_id` and `projects`.

### Chapter Workflow

The implemented workflow is: initialize a project → generate three candidate directions → select a direction → generate a draft → automated review and bounded rewrites → human approval → commit state and create a snapshot → roll back when needed.

For each chapter, click **Generate Story Options**, select **Progression**, **Escalation**, or **Revelation**, and then click **Generate Chapter**. If a draft already exists, use **Discard Draft** before changing or regenerating the story direction. Uncommitted plans do not change the official world state.

The dashboard provides a project overview, chapter navigation, a chapter text and automated review workspace, read-only views of characters, inventory, maps, and lore, recent state changes, and snapshot history. Drafts remain separate from committed state.

### Exporting Chapters

Click the top **下载到txt** (Download as TXT) button to export saved chapter `text` from `chapters`, sorted by chapter number. Each TXT contains up to three chapters, including any remaining chapters in the final group. A single group downloads as a TXT file; multiple groups download as a ZIP containing the TXT files.

Exports include both approved chapters and saved drafts, with their statuses labeled. Files use UTF-8 with BOM for compatibility with Chinese text in Windows Notepad. The button is disabled when no chapter text is available. The endpoint is `GET /api/project/export/txt`; exporting does not modify project data.

## Testing and Building

Run from the `novel_engine` directory:

```powershell
conda activate novel_engine
python -m pytest -q
cd frontend
npm test
npm run build
```

## Implementation Reports and Limitations

- [Phase 1 Implementation Report](docs/baseline_report.md): full data models, APIs, model configuration, validation results, and limitations.
- [Story Dashboard Report](docs/phase2_story_dashboard_report.md): Phase 2 API additions, data compatibility, test results, and browser acceptance limitations.
- [Narrative Planning Report](docs/phase3_narrative_planning_report.md): Phase 3 schemas, lifecycle, APIs, and validation results.

These reports are currently in Chinese. Legacy unapproved drafts have no story-plan binding and must be discarded and replanned after upgrading. Existing approved history remains readable.

The mock provider uses a fixed story about a traveler collecting waymarker stones, while preserving user settings in the lore and outline premise. It validates the workflow and does not represent actual novel interpretation or generation capabilities. To use a real model, configure an OpenAI-compatible provider as described in the Phase 1 report.

## Development Roadmap

Phases 1–3 are implemented; Phase 4 and the subsequent items describe future directions.

- Phase 1 — Multi-Agent workflow and persistent world-state management
- Phase 2 — Story Dashboard, state-change tracking, and snapshot management
- Phase 3 — Narrative Planning with three candidate story branches and human selection
- Phase 4 — Character Mind: goals, fears, beliefs, misconceptions, and evolving cognitive states
- Causal Narrative Planning: character choices, costs, and consequences
- Story Graph and long-term narrative memory
- Knowledge-driven storytelling
- Mindawaker integration for transforming generated stories into images and videos

A longer-term goal is to explore how cognitive modeling and ideas from knowledge tracing can support consistent character development and more meaningful narrative decisions.

## Acknowledgements

Special thanks to [**@dreamerriver**](https://github.com/dreamerriver/NovelEngine) for contributing the original concept, architecture, and initial requirements and design documents for this project.

The original design established the Coordinator–Workers multi-agent architecture, including orchestration, chapter generation, review, character and world-state management, human approval, state updates, snapshots, rollback, and the direction for long-term memory.

This project was subsequently implemented and extended with a Story Dashboard, structured narrative planning, alternative story branches, and human-guided story development.

The current work builds upon that original architecture while exploring character cognition, causal storytelling, and knowledge-driven narrative generation.
#   N o v e l E n g i n e 
 
