# Task Plan: Analyze Arm vs AMD pyperformance regressions against CPython

## Goal
Create a detailed, evidence-backed analysis plan for comparing this repository's current branch against upstream CPython and use the code differences to assess likely causes of regressions in specific pyperformance benchmarks, prioritized by impact.

## Current Phase
Phase 1

## Phases
### Phase 1: Requirements & Discovery
- [ ] Confirm repository state and comparison targets
- [ ] Identify benchmark list, priority, and expected deliverable format
- [ ] Document initial findings in findings.md
- **Status:** complete

### Phase 2: Code Difference Mapping
- [ ] Map current branch against upstream CPython base
- [ ] Identify subsystems and files with the largest or hottest-path deltas
- [ ] Correlate code differences with listed benchmarks
- **Status:** complete

### Phase 3: Regression Hypothesis Analysis
- [ ] Build per-benchmark hypotheses for Arm vs AMD divergence
- [ ] Rank hypotheses by likelihood and expected impact
- [ ] Note missing evidence and validation steps
- **Status:** in_progress

### Phase 4: Detailed Plan Authoring
- [ ] Produce an execution-ready investigation plan
- [ ] Include commands, files, metrics, and decision points
- [ ] Prioritize benchmarks and shared root-cause clusters
- [ ] Reshape the execution plan around one-click script generation for the isolated Linux Arm environment
- **Status:** in_progress

### Phase 5: Delivery
- [ ] Summarize findings and assumptions
- [ ] Call out risks, unknowns, and next validation steps
- [ ] Deliver plan and code-difference analysis to user
- **Status:** pending

## Key Questions
1. Which source-level deltas most plausibly affect interpreter hot paths used by the listed benchmarks?
2. Which regressions are likely architecture-sensitive versus benchmark-specific?
3. What ordering of investigation will maximize shared learning across the benchmark set?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Compare this repo's current HEAD to upstream CPython commit `ebf955df7a89ed0c7968f79faec1de49f61ed7cb` and nearby lineage in `~/Repo/cpython` | Matches the user-provided benchmark baseline |
| Focus first on runtime/interpreter/object-model/import/startup deltas before benchmark-specific code | These areas can explain multiple regressions at once |
| Treat this as a cross-repo extension-vs-upstream comparison, not a same-history git diff | `cinderx` is not a full CPython checkout and the upstream commit is not reachable from its history |
| Use existing local plans/findings as prior evidence, but keep current conclusions grounded in current-branch code | The repo already contains verified ARM investigations for `raytrace`, `float`, `generators`, and interpreter overhead |
| Use isolated Linux Arm as the only source of performance truth | Matches the user's environment constraint |
| Use local macOS Arm only to pierce functionality and prepare narrower remote checks | Reduces remote iteration cost without polluting final perf conclusions |
| Prioritize generating one-click scripts after diff-point analysis | Fits the network-isolated workflow and minimizes manual steps on the target host |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| planning-with-files `session-catchup.py` not found in expected path | 1 | Proceed with manual initialization of planning files and note the missing helper script |

## Notes
- Keep findings grounded in local repository evidence.
- Distinguish confirmed diffs from inferred performance hypotheses.
- Prefer shared root-cause clusters over isolated benchmark narratives where possible.
