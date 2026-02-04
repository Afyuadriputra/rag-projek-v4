class RequestIdFilter:
    """
    Menambahkan request_id ke record log.
    Jika belum ada, isi dengan '-'.
    """
    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        if not hasattr(record, "user"):
            record.user = "-"
        if not hasattr(record, "ip"):
            record.ip = "-"
        if not hasattr(record, "method"):
            record.method = "-"
        if not hasattr(record, "path"):
            record.path = "-"
        if not hasattr(record, "status"):
            record.status = "-"
        if not hasattr(record, "duration_ms"):
            record.duration_ms = "-"
        if not hasattr(record, "agent"):
            record.agent = "-"
        if not hasattr(record, "referer"):
            record.referer = "-"
        if not hasattr(record, "status_color"):
            record.status_color = ""
        # Color by status code (2xx green, 4xx yellow, 5xx red)
        try:
            st = int(record.status)
            if 200 <= st < 300:
                record.status_color = "\x1b[32m"  # green
            elif 400 <= st < 500:
                record.status_color = "\x1b[33m"  # yellow
            elif 500 <= st < 600:
                record.status_color = "\x1b[31m"  # red
        except Exception:
            pass
        return True
