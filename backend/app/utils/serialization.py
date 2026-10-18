"""Make pandas/numpy values JSON-safe (NaN -> null, numpy scalars -> python, timestamps -> ISO)."""
from __future__ import annotations

import math
from datetime import date, datetime

import numpy as np
import pandas as pd


def jsonable(obj):
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if obj is pd.NaT:
        return None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, int):
        return obj
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [jsonable(v) for v in obj.tolist()]
    if hasattr(obj, "to_dict"):
        return jsonable(obj.to_dict())
    return str(obj)
