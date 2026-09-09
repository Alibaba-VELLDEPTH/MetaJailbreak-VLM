import os
import sys
import datetime


class Logger(object):
    def __init__(self):
        if not os.path.exists("logs"):
            os.makedirs("logs")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_filename = os.path.join("logs", f"run_optimize_{timestamp}.txt")
        self.terminal = sys.stdout
        self.log = open(self.log_filename, "a", encoding="utf-8")

        print(f"=======================================================")
        print(f"LOGGING STARTED: Output will be saved to {self.log_filename}")
        print(f"=======================================================")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def reconfigure(self, **kwargs):
        reconfigure = getattr(self.terminal, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(**kwargs)
        return self

    def isatty(self):
        return bool(getattr(self.terminal, "isatty", lambda: False)())

    @property
    def encoding(self):
        return getattr(self.terminal, "encoding", "utf-8")

    def fileno(self):
        return self.terminal.fileno()

    def close(self):
        self.log.close()
        return None
