# PRD: PMAO GitHub CLI Template

## 1. Product Overview

### Product name
PMAO CLI Template

### Objective
Create a company- and project-agnostic GitHub package that turns an LLM into a structured project management assistant through a CLI-first workflow

The package should help users generate and maintain a PMAO-style project management workbook with clear initiative tracking, next steps, last-touch communications, meeting requests, and optional milestone planning

### Core concept
This is not a Python script workflow. The package should behave like a CLI tool that guides an LLM to act as a project manager

The CLI should provide structured prompts, templates, schemas, and operating instructions that can be used by Claude, Codex, or similar LLM coding / agent tools to set up and run a repeatable PMAO process

### Target users
- Strategy / operations / PMO teams managing cross-functional initiatives
- Consultants managing complex workstreams
- Business operators coordinating leadership updates, syndication, and meeting preparation
- Project leads who need a lightweight but rigorous initiative management system

---

## 2. Product Goals

### Primary goals
- Create a reusable PMAO GitHub template that is not tied to any specific company, project, executive team, or confidential context
- Package the strongest reusable concepts from the 20260604 workbook into a general-purpose CLI workflow
- Enable users to initialize a PMAO workspace from the command line
- Guide users through setup questions that customize the PMAO system to their project
- Generate and maintain a structured workbook with standard PMAO tabs
- Help users distinguish between high-level coordination next steps and detailed execution logs
- Preserve clear last-touch history from emails, Teams, Slack, or other communication sources
- Support project-specific syndication schedules, meeting requests, outstanding questions, and milestones

### Non-goals
- Do not hardcode company-specific terms, confidential names, internal project details, or one-off stakeholder structures
- Do not require users to run raw Python scripts manually
- Do not make the tool specific to Excel only if a broader markdown / CSV / workbook abstraction is useful
- Do not assume every project has the same executive stakeholders, milestone cadence, or syndication schedule
- Do not overload the initiative tracker with every detailed action item

---

## 3. Core User Experience

### Desired workflow
A user should be able to install or clone the GitHub package, run a CLI command, answer setup questions, and generate a reusable PMAO workspace

Example user journey:

1. User installs or clones the PMAO CLI template
2. User runs a command such as:

```bash
pmao init
```

3. CLI asks setup questions about the project, initiatives, owners, syndication process, materials, communication sources, and milestones
4. CLI generates a PMAO workspace with:
   - Workbook template
   - Project configuration file
   - Prompt library
   - Operating instructions for the LLM
   - Example inputs and outputs
   - README with usage instructions
5. User updates source materials over time
6. User runs commands such as:

```bash
pmao update
pmao ingest
pmao summarize
pmao export
```

7. CLI guides the LLM to maintain the PMAO workbook and produce concise project-management outputs

---

## 4. Boilerplate Workbook Structure

The standard PMAO workbook should include the following core tabs:

### 4.1 Initiatives
Purpose: Provide a clear, succinct executive-level view of all active initiatives

This should be the primary working tab for project leadership

Recommended columns:
- Initiative ID
- Initiative
- Initiative description
- Coordination owner
- Responsible owner
- Status
- Priority
- Current state / latest update
- Coordination next steps
- Tagged owner for each coordination next step
- Outstanding questions
- Outstanding meetings
- Last touch comment
- Last touch timestamp
- Syndication notes
- Materials / source links
- Notes

Key requirements:
- The initiatives tab should be clear, succinct, and easy to scan
- It should show what the initiatives are, who owns them, what the next steps are, and who is tagged against each next step
- Only high-level coordination next steps should be shown here
- Detailed next steps should live in the full next steps log
- “Outstanding meeting questions” should be generalized to “Outstanding questions”
- “Last touch comments” should remain prominent because they are useful for understanding the most recent stakeholder interaction
- Syndication notes should remain included because they help track who needs to review, align, or approve materials

Customization logic:
- Do not hardcode project-specific columns like ELT presenters unless the user requests them
- Coordination owner should be configurable
- Responsible owner should be configurable
- Stakeholder / presenter columns should be generated only after asking the user what stakeholder model applies
- Syndication schedule should be generated after asking who needs to see what and when
- Materials/source-link columns should be generated after asking whether initiative materials come from links, files, documents, meeting notes, or another source

---

### 4.2 Full Next Steps Log
Purpose: Maintain the detailed action-item history across all initiatives

Recommended columns:
- Next step ID
- Initiative ID
- Initiative
- Next step
- Owner
- Tagged stakeholders
- Source
- Source type
- Source timestamp
- Due date
- Status
- Dependency
- Notes
- Date added
- Date closed

Key requirements:
- This tab should hold the detailed next steps
- The initiatives tab should only surface the clear, high-level coordination next steps
- Each next step should be mapped back to an initiative
- Next steps should preserve source references wherever possible
- Source type should support email, meeting transcript, Teams, Slack, document comment, or manual entry
- The log should be detailed enough to audit where a next step came from

---

### 4.3 Last Touch Log
Purpose: Track the most recent meaningful interaction, comment, or communication by initiative and stakeholder

Recommended columns:
- Last touch ID
- Initiative ID
- Initiative
- Stakeholder / person
- Source type
- Source timestamp
- Channel
- Last touch summary
- Implication
- Follow-up required
- Owner
- Source link / reference

Key requirements:
- Email timestamps should be supported from the start
- Future support should include Teams and Slack timestamps and message references
- Last touch should capture the substance of the interaction, not just the existence of a message
- Last touch should be useful for project managers trying to understand who has been recently contacted, what they said, and what needs follow-up

---

### 4.4 Meeting Requests
Purpose: Track meetings needed to advance initiatives, resolve questions, or complete syndication

Recommended columns:
- Meeting request ID
- Initiative ID
- Initiative
- Meeting purpose
- Required attendees
- Optional attendees
- Owner
- Status
- Target timing
- Scheduling notes
- Outstanding questions to resolve
- Materials needed
- Source / rationale
- Notes

Key requirements:
- Meeting requests should be mapped at the initiative level
- High-level meeting requests should likely be derived from the initiatives tab, especially outstanding meetings and outstanding questions
- Meeting requests should distinguish between:
  - Meetings already requested
  - Meetings that need to be requested
  - Meetings that are blocked pending materials or stakeholder input
  - Meetings that are optional or lower priority

---

### 4.5 Milestones
Purpose: Provide optional workback planning for major project events

Recommended columns:
- Milestone ID
- Milestone
- Description
- Target date
- Initiative IDs affected
- Required materials
- Required decisions
- Required syndication
- Owner
- Status
- Workback notes

Key requirements:
- Milestones should be optional
- The tool should ask the user whether milestones are needed
- If milestones are used, limit to five or six maximum
- Milestones should represent major meetings, decision points, executive reviews, board meetings, client readouts, or other large events that require workback planning
- Do not assume a milestone structure without user input

---

## 5. Required CLI Commands

### `pmao init`
Initializes a new PMAO workspace

Expected behavior:
- Ask setup questions
- Generate project configuration
- Generate workbook structure
- Generate prompt library
- Generate README and usage instructions
- Create sample folder structure

### `pmao config`
Displays the current project configuration

Expected behavior:
- Print the contents of project-config.yaml for the given vault
- Edit the file directly to change project name, owner, LLM backend, or timeout

### `pmao ingest`
Ingests source material into the PMAO workspace

Supported source types:
- Email exports
- Meeting notes
- Meeting transcripts
- Teams messages
- Slack messages
- Document comments
- Manual notes
- Source links

Expected behavior:
- Parse source materials
- Extract initiatives, next steps, last touches, questions, and meeting requests
- Preserve timestamps and source references when available
- Flag ambiguous items for user review

### `pmao update`
Updates the workbook or structured PMAO outputs using new source material

Expected behavior:
- Refresh initiative-level summaries
- Add detailed next steps to full next steps log
- Update last touch log
- Add or update meeting requests
- Update outstanding questions
- Preserve historical records unless the user explicitly asks to overwrite them

### `pmao export`
Exports the PMAO workspace to a user-friendly format

Potential outputs:
- Excel workbook
- CSV folder
- Markdown summary
- JSON project state
- Executive summary
- Meeting prep brief

### `pmao summarize`
Produces a concise project management summary

Expected outputs:
- Executive summary
- Biggest changes since last update
- Initiative-level risks
- Open questions
- Upcoming meetings
- Required follow-ups
- Items requiring user attention

---

## 6. Setup Questions

The CLI should ask the user a structured set of setup questions during initialization

### Project context
- What is the project name?
- What is the project objective?
- What level of detail should the PMAO track?
- What output format do you want to maintain?
- Who is the primary user or project manager?

### Initiatives
- What are the initial initiatives?
- Do you want initiative IDs generated automatically?
- Should initiatives be grouped by workstream, function, stakeholder, or another dimension?
- Who is the coordination owner for each initiative?
- Is there also a responsible owner, accountable owner, or business owner?
- Are there stakeholder-specific roles that should be tracked?

### Syndication
- Who needs to review or approve materials?
- Who needs to be informed but not approve?
- What is the syndication cadence?
- Are there recurring syndication meetings?
- Are there specific stakeholder groups that need tailored updates?
- Should syndication notes appear in the initiatives tab?

### Materials
- Where do materials come from?
- Are materials stored as links, files, documents, folders, or mixed sources?
- Should the PMAO track source links at the initiative level?
- Should the PMAO track whether materials are drafted, reviewed, approved, or sent?

### Next steps
- Should all next steps be captured in the full log?
- Which next steps should be elevated to the initiatives tab?
- What owner model should be used for next steps?
- Should tagged stakeholders be tracked separately from owners?

### Last touch
- Which communication channels should be tracked?
- Should email timestamps be captured?
- Should Teams or Slack messages be captured?
- Should last touch be tracked by initiative, stakeholder, or both?
- What counts as a meaningful last touch?

### Meeting requests
- Should meeting requests be generated from outstanding questions?
- Should meeting requests be generated from initiative-level meeting needs?
- What fields are required for scheduling?
- Should the PMAO distinguish requested, scheduled, completed, and blocked meetings?

### Milestones
- Are milestones needed for this project?
- What are the major meetings or decision points?
- Limit milestones to five or six maximum
- What needs to be ready for each milestone?
- Which initiatives map to each milestone?
- What syndication or approvals are required before each milestone?

---

## 7. Folder Structure

The repository structure as implemented:

```text
pmao-cli/
  README.md
  pyproject.toml
  pmao/
    cli.py          — flat CLI entry point (init, ingest, update, status, summarize, export, config)
    models.py       — generic Initiative dataclass (17 fields, no project-specific content)
    vault.py        — vault init, load/save initiatives, seed from CSV
    ingest.py       — LLM workflow functions (run_ingest, run_update, run_status, run_summarize)
    transcript.py   — WebVTT and plain-text preprocessor
    llm.py          — Claude Code / Codex CLI backend with JSON parsing
    excel.py        — openpyxl workbook generator (5 tabs)
  skills/
    ingest.md       — LLM prompt: structured extraction from source material
    update.md       — LLM prompt: interactive initiative field update
    status.md       — LLM prompt: status dashboard rendering
    summarize.md    — LLM prompt: executive summary generation
  templates/
    project-config.yaml        — annotated config template
    workbook-schema.yaml       — workbook tab and column reference
    initiative-template.csv    — CSV seed template for --roster
  examples/
    example-project-config.yaml   — filled-out configuration
    example-source-notes.md       — sample meeting notes for ingestion
    example-output-summary.md     — representative pmao summarize output
  tests/
    test_models.py
    test_vault.py
    test_ingest.py
    test_transcript.py
    test_llm.py
    test_excel.py
```

The repository separates:
- CLI dispatch layer (pmao/)
- LLM reasoning layer (skills/) — edit these without touching Python
- Vault data (JSON files written to user's vault directory at runtime)
- Derived artifacts (workbook.xlsx, regenerated on each ingest or export)

---

## 8. LLM Operating Instructions

The package should include a reusable operating prompt that instructs the LLM to behave as a project manager

Core LLM behavior:
- Act as a structured PMAO / project management assistant
- Extract project-management-relevant information from source materials
- Maintain initiative-level clarity
- Separate high-level coordination next steps from detailed execution next steps
- Preserve timestamps and source references
- Avoid inventing owners, dates, or decisions
- Flag ambiguity instead of guessing
- Keep outputs company- and project-agnostic unless the user configures otherwise
- Generate concise, executive-ready project management language
- Prioritize clarity, traceability, and actionability

The LLM should classify information into:
- Initiative updates
- Coordination next steps
- Detailed next steps
- Last touch comments
- Outstanding questions
- Meeting requests
- Syndication notes
- Milestone dependencies
- Risks or blockers

---

## 9. Data Model Principles

### Initiative-level data
Initiatives are the primary organizing unit

Every major item should map to an initiative where possible:
- Next steps
- Last touches
- Outstanding questions
- Meeting requests
- Milestones
- Materials
- Syndication needs

### Separation of summary and detail
The initiatives tab should remain succinct

Detailed logs should hold audit-level information:
- Full next steps log for detailed actions
- Last touch log for communication history
- Meeting requests tab for scheduling and meeting needs
- Milestones tab for workback planning

### Traceability
The system should preserve:
- Source type
- Source timestamp
- Source link or reference
- Person / stakeholder
- Initiative mapping
- Date added
- Status

### Customizability
The system should not assume:
- Company-specific roles
- Project-specific executive structures
- Fixed milestone cadence
- Fixed syndication path
- Fixed material source format
- Fixed communication channels

---

## 10. Acceptance Criteria

### Initialization
- User can run `pmao init`
- CLI asks structured setup questions
- CLI creates a PMAO workspace with templates, prompts, config, and documentation
- Output is usable without hardcoded company-specific terms

### Workbook generation
- System creates the five standard tabs:
  - Initiatives
  - Full Next Steps Log
  - Last Touch Log
  - Meeting Requests
  - Milestones
- Milestones can be disabled or omitted
- Initiatives tab remains concise and executive-readable
- Detailed next steps are stored in the full next steps log

### Source ingestion
- System can ingest project notes, meeting notes, emails, Teams messages, Slack messages, and document comments as source materials
- System extracts next steps, last touches, outstanding questions, meeting requests, and syndication notes
- System preserves timestamps and references when available
- System flags ambiguous items for user review

### Update workflow
- System updates project state without deleting historical logs
- System maps new information to initiatives
- System elevates only coordination-level next steps to the initiatives tab
- System logs detailed next steps separately
- System updates last touch comments based on the most recent meaningful interaction

### Export workflow
- User can export the PMAO state into a workbook, CSVs, markdown, or JSON
- Exported outputs are clean, readable, and project-manager-ready

### Documentation
- README explains what the tool does, who it is for, and how to use it
- Documentation explains the PMAO workflow
- Documentation includes setup, customization, and example usage
- Documentation explains how to use the tool with Claude, Codex, or another LLM agent

---

## 11. Implementation Notes

### CLI-first requirement
The tool should feel like a proper CLI package

Users should not need to run scripts like:

```bash
python update_workbook.py
```

Preferred usage should be:

```bash
pmao init
pmao ingest
pmao update
pmao export
```

### Skill-First Architecture
All LLM reasoning lives in plain-text skill files (`skills/*.md`), not in Python code. Python handles only:
- Vault scaffolding (directory creation, JSON read/write, backup)
- Placeholder substitution (`{initiatives}`, `{source}`, `{project_state}`)
- Subprocess invocation of the LLM backend
- JSON parsing of structured responses
- Excel workbook generation via openpyxl

This means users can change how the LLM interprets transcripts, formats its output, or classifies information by editing a markdown file — no Python changes required.

### LLM-first architecture
The CLI does not need to perform all reasoning itself

The main value of the package is:
- Skill file prompts (editable by non-engineers)
- Project-management operating model
- Workbook schema
- Repeatable CLI workflow
- Clear data contracts
- Instructions that help an LLM behave like a project manager

### Confidentiality requirement
The GitHub package must not include:
- Company names
- Internal project names
- Executive names
- Confidential workbook content
- Client-specific terms
- Proprietary strategy details
- Real emails, Teams messages, Slack messages, or meeting transcripts

Use generic examples only

---

## 12. Design Decisions

The following questions were resolved during implementation:

**Canonical project state format:** JSON files (`initiatives.json`, `actions.json`, `questions.json`, `decisions.json`) are the source of truth. `workbook.xlsx` is a derived artifact regenerated on each `pmao ingest` or `pmao export`. JSON is machine-readable by the LLM; Excel is human-readable for stakeholders.

**Workbook export:** Core feature, not optional. `pmao export` regenerates the workbook from current JSON state. The workbook is also refreshed automatically after every `pmao ingest` run.

**LLM handoff:** The CLI invokes `claude -p <prompt>` or `codex -q <prompt>` as a subprocess. Auto-detection checks PATH for `claude` first, then `codex`. Backend can be overridden per-command with `--backend` or set permanently in `project-config.yaml`.

**Prompt-only vs. file management:** Both. Skill files (`skills/*.md`) define all LLM reasoning. Python manages vault files (JSON, YAML, Excel). Users edit skill files to change LLM behavior; they edit vault JSON to change project state directly.

**Source reference format:** Free-text `last_touch_comment` field in each initiative. The ingest skill instructs the LLM to prefix comments with the source type (e.g., `[email]`, `[teams]`, `[notes]`). No structured tagging schema is enforced at the data layer.

**Ambiguous items:** The ingest skill instructs the LLM to leave fields blank rather than guess. Extraction results are printed before applying and require user confirmation (`y/N`), unless `--yes` is passed.

**Milestones tab:** Always included in the workbook (5-tab structure is fixed). The tab is empty by default; users populate it manually or via future tooling.

---

## 13. Success Metrics

The PMAO CLI Template is successful if:

- A new user can initialize a project in under 10 minutes
- The generated PMAO structure is useful across different companies and project types
- The initiatives tab gives a clear executive-level view of initiative status, ownership, next steps, open questions, meetings, and last touch
- The full next steps log provides traceable detail without cluttering the initiatives tab
- The last touch log helps users quickly understand recent stakeholder communications
- Meeting requests are clearly mapped to initiatives and outstanding questions
- Milestones support workback planning without becoming overly project-specific
- The package can be used effectively with Claude, Codex, or another LLM agent as a CLI-driven project management system
