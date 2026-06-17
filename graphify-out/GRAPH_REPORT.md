# Graph Report - .  (2026-06-16)

## Corpus Check
- Corpus is ~11,622 words - fits in a single context window. You may not need a graph.

## Summary
- 100 nodes · 195 edges · 8 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Pipeline orchestrator|Pipeline orchestrator]]
- [[_COMMUNITY_Financial Schema Definitions|Financial Schema Definitions]]
- [[_COMMUNITY_PDF Extractor|PDF Extractor]]
- [[_COMMUNITY_Auto Mapper|Auto Mapper]]
- [[_COMMUNITY_Answer Engine|Answer Engine]]
- [[_COMMUNITY_Calculation Engine|Calculation Engine]]
- [[_COMMUNITY_Comparators and Utils|Comparators and Utils]]
- [[_COMMUNITY_Financial Summary Utils|Financial Summary Utils]]

## God Nodes (most connected - your core abstractions)
1. `calculate_answer()` - 12 edges
2. `run_full_pipeline()` - 9 edges
3. `process_company()` - 9 edges
4. `generate_financial_analysis()` - 8 edges
5. `build_normalized_metrics()` - 8 edges
6. `percentage_change()` - 8 edges
7. `margin()` - 8 edges
8. `format_money()` - 8 edges
9. `format_percent()` - 8 edges
10. `setup_company_rag()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `run_full_pipeline()` --calls--> `get_or_create_mapping()`  [EXTRACTED]
  pipeline.py → src/auto_mapper.py
- `run_full_pipeline()` --calls--> `get_target_pages()`  [EXTRACTED]
  pipeline.py → src/auto_mapper.py
- `run_full_pipeline()` --calls--> `build_financial_summary()`  [EXTRACTED]
  pipeline.py → src/calculation_engine.py
- `run_full_pipeline()` --calls--> `generate_financial_analysis()`  [EXTRACTED]
  pipeline.py → src/calculation_engine.py
- `run_full_pipeline()` --calls--> `process_company()`  [EXTRACTED]
  pipeline.py → src/extractor.py

## Import Cycles
- None detected.

## Communities (8 total, 0 thin omitted)

### Community 0 - "Pipeline orchestrator"
Cohesion: 0.12
Nodes (22): ask(), PipelineResult, pipeline.py ----------- THE MASTER PIPELINE — the only file you need to call f, Full pipeline: PDF -> metrics -> ratios -> vector store -> ready for Q&A., Ask any financial question about a company.      HOW IT WORKS (two-step decisi, Everything produced by run_full_pipeline() for one company + year.      Think, run_full_pipeline(), extract_text_by_page() (+14 more)

### Community 1 - "Financial Schema Definitions"
Cohesion: 0.16
Nodes (14): financial_schema.py ------------------- Defines the STANDARD canonical financi, Check that all required standard keys are present in *metrics*.      This is c, validate_metrics(), generate_llm_financial_interpretation(), Ask the LLM to interpret a financial summary produced by     :func:`~src.calcula, interpret_liabilities_ratio(), Return a plain-English interpretation of the liabilities-to-assets ratio.      P, build_normalized_metrics() (+6 more)

### Community 2 - "PDF Extractor"
Cohesion: 0.17
Nodes (15): assign_years(), extract_financial_lines(), _extract_label_from_line(), _extract_numbers_from_line(), process_company(), extractor.py ------------ Reusable PDF extraction pipeline.  Entry point: pr, Pull all numeric values out of a line in left-to-right order.      Handles:, Extract the text label from the start of a reconstructed row.     Returns every (+7 more)

### Community 3 - "Auto Mapper"
Cohesion: 0.21
Nodes (11): auto_generate_mapping(), detect_financial_pages(), extract_raw_labels(), get_or_create_mapping(), get_target_pages(), auto_mapper.py -------------- Two jobs: 1. AUTO-DETECT which pages of a 10-K, Return the combined list of income statement + balance sheet pages.     This is, Read the target pages and collect all unique text labels that appear     alongs (+3 more)

### Community 4 - "Answer Engine"
Cohesion: 0.27
Nodes (9): answer_financial_question(), calculate_answer(), detect_calculation_intent(), answer_engine.py ---------------- Functions that detect calculation intent from, Map a natural-language *question* to a calculation intent string.      Returns, Answer *question* by combining a deterministic calculation (when possible)     w, Attempt to answer *question* deterministically using *metrics*.      Parameters, get_value() (+1 more)

### Community 5 - "Calculation Engine"
Cohesion: 0.32
Nodes (7): generate_financial_analysis(), calculation_engine.py ---------------------- Functions that load financial metri, Calculate key financial ratios and growth metrics for *year*.      Parameters, margin(), Return *part* as a percentage of *total*., Round *value* to *decimals* decimal places., safe_round()

### Community 6 - "Comparators and Utils"
Cohesion: 0.32
Nodes (6): comparator.py ------------- Cross-company financial comparison.  Takes metri, format_percent(), percentage_change(), utils.py -------- Pure helper functions for number cleaning and formatting. No b, Return the percentage change from *previous* to *current*., Format a numeric value as a percentage string, e.g. '25.31%'.

### Community 7 - "Financial Summary Utils"
Cohesion: 0.50
Nodes (4): build_financial_summary(), Build a human-readable text summary from an *analysis* dict produced by     :fun, format_money(), Format a numeric value as a USD-millions string, e.g. '$383,285 million'.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `calculate_answer()` connect `Answer Engine` to `Pipeline orchestrator`, `Financial Schema Definitions`, `Calculation Engine`, `Comparators and Utils`, `Financial Summary Utils`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Why does `process_company()` connect `PDF Extractor` to `Pipeline orchestrator`, `Financial Schema Definitions`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **What connects `pipeline.py ----------- THE MASTER PIPELINE — the only file you need to call f`, `Everything produced by run_full_pipeline() for one company + year.      Think`, `Full pipeline: PDF -> metrics -> ratios -> vector store -> ready for Q&A.` to the rest of the system?**
  _49 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Pipeline orchestrator` be split into smaller, more focused modules?**
  _Cohesion score 0.12318840579710146 - nodes in this community are weakly interconnected._