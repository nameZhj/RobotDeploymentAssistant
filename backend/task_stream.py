import json
import queue
import time
from typing import Dict
from flask import Response

stream_queues: Dict[str, queue.Queue] = {}


def push_stream_msg(task_id: str, text: str, is_err: bool = False):
    if task_id in stream_queues:
        stream_queues[task_id].put({"text": text, "is_err": is_err, "time": time.time()})


def stream_events_handler(task_id: str):
    if task_id not in stream_queues:
        return Response("Task not found", status=404)

    def event_stream():
        q = stream_queues[task_id]
        while True:
            try:
                msg = q.get(timeout=30.0)
                text = msg["text"]
                is_err = msg["is_err"]
                yield f"data: {json.dumps({'text': text, 'is_err': is_err})}\n\n"
                if "__TASK_DONE__" in text:
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'text': '', 'ping': True})}\n\n"

        stream_queues.pop(task_id, None)

    return Response(event_stream(), mimetype="text/event-stream")

