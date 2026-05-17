"""
predictor/transformers.py
=========================
Custom sklearn transformers used inside the saved ML pipeline.

This module exists separately from ml_engine.py so that the class can be
imported and re-registered on `sys.modules["__main__"]` before joblib.load,
which is required because the pipeline was originally pickled while
`test.py` was running as `__main__`.
"""

import logging
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import LabelEncoder

logger = logging.getLogger("predictor")

NUMERIC_COLS = ["duration", "days_left"]


class MultiColumnLabelEncoder(BaseEstimator, TransformerMixin):
    """Apply sklearn LabelEncoder to each categorical column independently."""

    def __init__(self, columns):
        self.columns = columns
        self.encoders_ = {}

    def fit(self, X, y=None):
        df = pd.DataFrame(X, columns=self.columns + NUMERIC_COLS) \
            if not isinstance(X, pd.DataFrame) else X
        for col in self.columns:
            le = LabelEncoder()
            le.fit(df[col].astype(str))
            self.encoders_[col] = le
        return self

    def transform(self, X, y=None):
        df = X.copy() if isinstance(X, pd.DataFrame) else pd.DataFrame(
            X, columns=self.columns + NUMERIC_COLS
        )
        for col in self.columns:
            df[col] = self.encoders_[col].transform(df[col].astype(str))
        return df.values.astype(float)
