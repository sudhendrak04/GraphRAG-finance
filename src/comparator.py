"""
comparator.py
-------------
Cross-company financial comparison.

Takes metrics dicts (from PipelineResult.metrics) for multiple
companies and produces side-by-side comparisons as DataFrames
and LLM-generated narrative summaries.

Design principle: this module only needs metrics dicts — it has
no dependency on the pipeline, PDF, or vector store.
"""

import pandas as pd
import ollama

from src.calculation_engine import get_value
from src.utils import margin, percentage_change, format_percent, format_money
