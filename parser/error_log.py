import pandas as pd
from datetime import datetime


class ParseErrorLog:
    LEVELS = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}

    def __init__(self):
        self.errors = []

    def log(self, level: str, line_no: int, roll: str, message: str, raw_line: str = ""):
        self.errors.append({
            "Timestamp": datetime.now().strftime("%H:%M:%S"),
            "Level": level.upper(),
            "Line No": line_no,
            "Roll No": roll,
            "Message": message,
            "Raw Content": raw_line[:120],
        })

    def has_critical(self):
        return any(e["Level"] == "CRITICAL" for e in self.errors)

    def summary(self):
        if not self.errors:
            return "No errors found."
        counts = {}
        for e in self.errors:
            counts[e["Level"]] = counts.get(e["Level"], 0) + 1
        return " | ".join(f"{k}: {v}" for k, v in counts.items())

    def to_dataframe(self):
        if not self.errors:
            return pd.DataFrame(columns=["Timestamp", "Level", "Line No", "Roll No", "Message", "Raw Content"])
        return pd.DataFrame(self.errors)

    def __len__(self):
        return len(self.errors)
