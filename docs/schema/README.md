# Meeting reports — schema contract

Canonical JSON Schema + concrete examples for the JSONB columns of the
`meeting_reports` table (Supabase project `SUPABASE_MEETINGS_URL`).

| File | What it is |
|---|---|
| `meeting_report.schema.json` | JSON Schema (draft 2020-12) for the `report` column. Generated from `agents.teams_agent.MeetingReport`. |
| `meeting_transcript.schema.json` | JSON Schema for the `transcript` column. Generated from `agents.teams_agent.MeetingTranscript`. |
| `example_meeting_report.json` | A realistic, valid `report` payload. |
| `example_meeting_transcript.json` | A realistic, valid `transcript` payload. |

## Source of truth

The Pydantic models in `agents/teams_agent.py` are the source of truth.
Everything in this folder is derived from them. **Do not edit by hand** — re-generate.

## Re-generate after schema changes

From the project root, with the project's venv active:

```bash
python -c "import json; from agents.teams_agent import MeetingReport, MeetingTranscript; \
  open('docs/schema/meeting_report.schema.json','w',encoding='utf-8').write(json.dumps(MeetingReport.model_json_schema(),ensure_ascii=False,indent=2)); \
  open('docs/schema/meeting_transcript.schema.json','w',encoding='utf-8').write(json.dumps(MeetingTranscript.model_json_schema(),ensure_ascii=False,indent=2))"
```

## Frontend usage

### Zod (TypeScript)

```bash
npx json-schema-to-zod -i docs/schema/meeting_report.schema.json -o src/schemas/meeting-report.ts
npx json-schema-to-zod -i docs/schema/meeting_transcript.schema.json -o src/schemas/meeting-transcript.ts
```

### TypeScript types only

```bash
npx json-schema-to-typescript docs/schema/meeting_report.schema.json > src/types/meeting-report.d.ts
```

### Or — full Supabase TS types (covers the whole table, not just JSONB)

```bash
supabase gen types typescript --project-id <meetings-project-id> --schema public > meetings.types.ts
```

## Notes on nullability

- All `Optional[str]` fields appear in the schema as `anyOf: [{type: string}, {type: null}]` with `default: null`.
- LLM is instructed not to invent values — if not stated in the meeting, the field is `null`.
- The `participants` / `discussion_items` / `open_questions` / `risks` arrays are always present (may be empty `[]`).
- `status` on `DiscussionItem` is one of: `Новый` / `В работе` / `Выполнено` / `Отложено` (defaults to `Новый`). Not enforced by the JSON Schema yet — kept as free string for forward compatibility.
