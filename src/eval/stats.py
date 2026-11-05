"""Statistics for P3/P4 (spec v1 tie rule, v1.2 S10): clustered bootstrap by document, 2,000 resamples, 95% intervals.
The same seed and the same document order give every setting the same resamples (paired comparisons)."""
import numpy as np

RESAMPLES, LEVEL, SEED = 2000, 0.95, 42


def document_means(frame, value="recall"):
    """Question values averaged per document (S9), in document order."""
    return frame.groupby("doc_id")[value].mean().sort_index()


def bootstrap_interval(document_values, resamples=RESAMPLES, seed=SEED):
    """(mean, low, high): the mean of the document values and its 95% interval from resampling documents."""
    values = np.asarray(document_values, dtype=float)
    picks = np.random.default_rng(seed).integers(0, len(values), size=(resamples, len(values)))
    means = values[picks].mean(axis=1)
    tail = (1 - LEVEL) / 2
    return float(values.mean()), float(np.quantile(means, tail)), float(np.quantile(means, 1 - tail))