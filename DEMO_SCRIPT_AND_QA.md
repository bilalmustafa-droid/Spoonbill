# Project Spoonbill — Demo Script and Q&A Prep

## 3-minute demo script

Timed for a live walkthrough. Practice it once against the real app before presenting — the click targets below match the actual UI.

**0:00–0:20 — The problem (no clicking yet)**
> "Hong Kong committed to 'no net loss of wetland' for the Deep Bay fishpond belt. That commitment is unenforceable without someone actually checking — satellite monitoring plus a citation-backed legal brief, automatically, is what Spoonbill does."

**0:20–0:50 — The map**
- Point at the map, three colored polygons visible.
- Click one polygon (pick the "high" confidence one — red/orange).
> "Each shape is a detected change. Color and the glyph both encode confidence — high, medium, low — so it still reads without color vision. This one shows a radar backscatter increase and a water-index drop, together, persisting for several months — that combination is what separates a real conversion from a pond that was just drained for winter."

**0:50–1:30 — The brief**
- Point to the right-hand detail panel, scroll to the brief section.
> "Every detection gets a bilingual legal brief, generated against Hong Kong's actual planning guidelines — not a generic LLM answer, a retrieval step pulls the real statutory text first, then the model has to cite it. If it can't verify its own citation against the source text, it's programmed to abstain and flag for human review instead of guessing. Personal data — HKIDs, phone numbers — gets redacted automatically before anything is shown."
- Switch language toggle (sidebar) to show the Chinese version briefly.

**1:30–2:00 — The honest negative result (say this confidently, don't rush it)**
> "The three anomalies you're looking at are labeled synthetic in the data — they prove the full pipeline end-to-end. Our actual detector ran against live Sentinel-1 and Sentinel-2 imagery over two real site boxes, and it returned zero persistent detections there. We know why: a deliberately strict rule — a location has to be flagged in at least 4 of the last 6 months, and in both of the most recent two — and we have the diagnostic numbers to back that up. A system that always finds something would worry me more than one that gave an honest zero."

**2:00–2:30 — Export**
- Click the PDF or DOCX export button.
> "Every brief exports to PDF or DOCX in the same format a planning officer already expects, bilingually, in one click."

**2:30–3:00 — Close**
> "The pipeline runs end to end today: live satellite detection, retrieval-grounded legal brief generation with a cite-or-abstain guardrail, and a dashboard — all free-tier, no paid services. What's next is simply more satellite passes and site coverage, the hard integration work is done."

---

## Q&A prep

### "Is this real data?"
> "The three anomalies on screen are explicitly labeled synthetic in the underlying data — they're placeholder examples that conform exactly to our production schema, used to prove the pipeline end-to-end. Everything downstream of them — retrieval, citation-backed brief generation, redaction — is fully live; we verified that with a real Gemini call before building the rest of the UI."

### "Your detector found nothing. Does it work?"
> "It ran against live satellite data over two real site boxes and returned zero persistent detections — that's a diagnosed result, not a crash. We logged flagged hectares per month and the overlap before and after our cleanup step; the overlap satisfying our persistence rule was near-zero before cleanup even ran, meaning no single location stayed flagged long enough across six months to count. A strict rule that sometimes finds nothing is more trustworthy than one that always finds something."

### "Which orbit direction / sensor settings did you use?"
> "We don't hardcode it — the script scans both ascending and descending Sentinel-1 passes at the start of every run and uses whichever actually has coverage for the AOI. For Deep Bay that turned out to be ascending; an earlier hardcoded descending pass returned zero scenes for the entire date range, which is exactly the kind of silent failure the auto-detection now catches."

### "How is this different from someone just looking at Google Earth?"
> "Three things: it's systematic and repeatable, not eyeballing — same thresholds applied every time. It fuses two independent signals — radar, which sees through cloud cover, and an optical water index — and requires both to agree for several months, which filters out a pond that's just seasonally drained, something a single before/after image comparison would false-positive on. And every detection becomes a cited legal brief in the right regulatory language automatically, which nobody is doing by eye."

### "Why Gemini specifically?"
> "Free tier, strong structured-JSON output, good enough bilingual generation. The retrieval and guardrail logic isn't model-specific — swapping models would mean changing one client call, not the pipeline."

### "What happens if the brief can't find a good citation?"
> "It abstains — the status flips to 'abstained, human review required' instead of asserting something unverified. That's a programmatic check: every citation the model returns gets validated against the actual retrieved text before the brief is accepted as 'cited.'"

### "Is personal data handled safely?"
> "Yes — two layers. The brief generator redacts Hong Kong ID numbers, emails, and phone numbers before anything is written to disk, and a second content filter on the UI side independently withholds any text pattern it doesn't recognize as safe, as a last line of defense."

### "Why only two site boxes tested?"
> "Time. The methodology generalizes to any AOI — it's the same code, different coordinates. Two boxes were enough to prove the pipeline runs correctly against live data and to get a real, diagnosed result either way."

### "What would you do with more time?"
> "Run the detector against a wider area to actually find a real detection, link real chip imagery to real anomaly IDs once Track 1 has them, and wire the BM25 sparse retriever back into the live retrieval path — it's built but not currently called."
