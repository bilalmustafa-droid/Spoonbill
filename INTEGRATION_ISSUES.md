# Integration issues

Contract mismatches and upstream problems found while integrating Track 1 / Track 2 output into the Track 3 UI.
Track 3 never edits another track's files; issues are recorded here for the owning track.

Entries marked `[auto]` are appended (deduplicated) by the running app when real data is loaded.
Fixture data never writes here.

## Known contract defect: six numeric fields have no null option (2026-10-18)

`contract/anomaly.schema.json` requires `baseline_vv_db`, `current_vv_db`, `delta_vv_db`,
`baseline_ndwi`, `current_ndwi`, `delta_ndwi` as plain `number` on every feature, with no
`null` option -- unlike `chip_before_png`/`chip_after_png`, which are genuinely nullable.
This matches the original kickoff brief's description of the frozen contract ("unknown
values are null"), but the schema as actually written and committed diverges from that: it
locks every anomaly to a two-sensor (SAR + optical) design.

Consequence: a detector that only produces optical evidence (the one that actually works
today, `spatial/ruhan code.py`, built on `cv2`-style true-colour crops with a magenta
change-flag mask) cannot emit a schema-valid anomaly feature, because it has no radar
numbers to put in those six fields and the schema will not accept `null` there. Verified
directly against the frontend's Pydantic model (`frontend/track3_app/core/models.py`), not
just the raw JSON Schema -- `AnomalyProperties` rejects `None` for all six with:

```
6 validation errors for AnomalyProperties
baseline_vv_db
  Input should be a valid number [type=float_type, input_value=None, input_type=NoneType]
current_vv_db
  Input should be a valid number [type=float_type, input_value=None, input_type=NoneType]
delta_vv_db
  Input should be a valid number [type=float_type, input_value=None, input_type=NoneType]
baseline_ndwi
  Input should be a valid number [type=float_type, input_value=None, input_type=NoneType]
current_ndwi
  Input should be a valid number [type=float_type, input_value=None, input_type=NoneType]
delta_ndwi
  Input should be a valid number [type=float_type, input_value=None, input_type=NoneType]
```

`AnomalyCollection` builds every feature into one Pydantic model at once, so a single feature
failing this check would fail the *entire* collection, not just that feature -- the whole map
would go blank, not degrade gracefully.

Decided NOT to fix tonight (2026-10-18, this close to submission): too large and risky a
contract change for the time remaining, since two other modules (the JSON Schema itself and
the Pydantic model) would both need coordinated updates. Worked around instead by never
emitting a schema-validated anomaly feature from the optical-only detector's output -- real
crops from it are shown in a separate, un-linked evidence gallery (`build_demo_chips.py`,
`data/evidence_chips/`) instead. Real long-term fix: make these six fields nullable in both
`contract/anomaly.schema.json` and `core/models.py`, consistent with how chip paths already
work, so a single-sensor detector can emit a valid (if less certain) detection.
