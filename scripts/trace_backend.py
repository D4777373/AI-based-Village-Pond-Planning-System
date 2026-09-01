from __future__ import annotations

import inspect
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any


# =========================================================
# PROJECT PATH
# =========================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

BACKEND_ROOT = (
    PROJECT_ROOT
    / "backend"
)

# Needed because this script lives inside scripts/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


# =========================================================
# TERMINAL OUTPUT LOCK
# =========================================================

print_lock = (
    threading.Lock()
)

thread_data = (
    threading.local()
)


# =========================================================
# TRACE CONFIGURATION
# =========================================================

# Set this to False if you want a smaller output.
SHOW_ARGUMENTS = True

# Ignore extremely uninteresting functions.
IGNORE_FUNCTIONS = {
    "__init__",
    "__repr__",
    "__str__",
}


# =========================================================
# MODULE CATEGORY
# =========================================================

def get_category(
    filename: str,
) -> str:
    """
    Convert backend path into a readable pipeline category.
    """

    path = filename.replace(
        "\\",
        "/",
    )

    if "/backend/api/" in path:
        return "API"

    if "/backend/services/" in path:
        return "SERVICE"

    if "/backend/terrain/" in path:
        return "TERRAIN"

    if "/backend/hydrology/" in path:
        return "HYDROLOGY"

    if "/backend/pond/" in path:
        return "POND"

    if "/backend/schemas/" in path:
        return "SCHEMA"

    if path.endswith(
        "/backend/main.py"
    ):
        return "APP"

    return "BACKEND"


# =========================================================
# DETERMINE WHETHER WE WANT TO TRACE FILE
# =========================================================

def should_trace(
    filename: str,
) -> bool:

    try:

        path = (
            Path(filename)
            .resolve()
        )

        return (
            path == BACKEND_ROOT
            or
            BACKEND_ROOT in path.parents
        )

    except Exception:

        return False


# =========================================================
# FORMAT VALUES SAFELY
# =========================================================

def safe_value(
    value: Any,
) -> str | None:
    """
    Only display small/simple argument values.

    We deliberately avoid printing:

        uploaded file bytes
        NumPy arrays
        DEM matrices
        large dictionaries
        API credentials
    """

    if value is None:
        return "None"

    if isinstance(
        value,
        bool,
    ):
        return str(value)

    if isinstance(
        value,
        int,
    ):
        return str(value)

    if isinstance(
        value,
        float,
    ):
        return f"{value:.6g}"

    if isinstance(
        value,
        Path,
    ):
        return str(value)

    if isinstance(
        value,
        str,
    ):

        # Do not accidentally print secrets.
        lowered = value.lower()

        if (
            "api_key" in lowered
            or
            "token" in lowered
        ):
            return "<hidden>"

        if len(value) > 100:
            return (
                repr(
                    value[:97]
                )
                + "..."
            )

        return repr(
            value
        )

    # Avoid dumping large data into terminal.
    if isinstance(
        value,
        bytes,
    ):
        return (
            f"<bytes: "
            f"{len(value)} bytes>"
        )

    if isinstance(
        value,
        list,
    ):
        return (
            f"<list: "
            f"{len(value)} items>"
        )

    if isinstance(
        value,
        tuple,
    ):

        if len(value) <= 4:

            try:
                return repr(
                    value
                )
            except Exception:
                pass

        return (
            f"<tuple: "
            f"{len(value)} items>"
        )

    if isinstance(
        value,
        dict,
    ):
        return (
            f"<dict: "
            f"{len(value)} keys>"
        )

    # NumPy / GIS / custom objects.
    type_name = (
        type(value)
        .__name__
    )

    shape = getattr(
        value,
        "shape",
        None,
    )

    if shape is not None:

        return (
            f"<{type_name} "
            f"shape={shape}>"
        )

    return (
        f"<{type_name}>"
    )


# =========================================================
# GET FUNCTION ARGUMENTS
# =========================================================

def get_function_arguments(
    frame,
) -> str:
    """
    Extract only arguments declared in the function
    signature.
    """

    if not SHOW_ARGUMENTS:
        return ""

    try:

        args_info = (
            inspect.getargvalues(
                frame
            )
        )

    except Exception:

        return ""

    values = []

    for name in args_info.args:

        # Never print these automatically.
        if name in {
            "self",
            "cls",
            "api_key",
            "token",
        }:
            continue

        value = (
            frame.f_locals.get(
                name
            )
        )

        formatted = (
            safe_value(
                value
            )
        )

        if formatted is None:
            continue

        values.append(
            f"{name}={formatted}"
        )

    if not values:
        return ""

    # Don't make a single log line enormous.
    text = ", ".join(
        values
    )

    if len(text) > 220:

        text = (
            text[:217]
            + "..."
        )

    return text


# =========================================================
# THREAD STATE
# =========================================================

def get_depth() -> int:

    return getattr(
        thread_data,
        "depth",
        0,
    )


def set_depth(
    value: int,
) -> None:

    thread_data.depth = max(
        0,
        value,
    )


def get_timers() -> dict:

    timers = getattr(
        thread_data,
        "timers",
        None,
    )

    if timers is None:

        timers = {}

        thread_data.timers = (
            timers
        )

    return timers


# =========================================================
# PROFILER CALLBACK
# =========================================================

def trace_backend(
    frame,
    event,
    arg,
):
    """
    Python profiler callback.

    We only display calls originating from the project's
    backend directory.
    """

    filename = (
        frame
        .f_code
        .co_filename
    )

    if not should_trace(
        filename
    ):
        return

    function_name = (
        frame
        .f_code
        .co_name
    )

    if (
        function_name
        in IGNORE_FUNCTIONS
    ):
        return

    category = (
        get_category(
            filename
        )
    )

    module_name = (
        Path(filename)
        .stem
    )

    # =====================================================
    # FUNCTION ENTER
    # =====================================================

    if event == "call":

        depth = (
            get_depth()
        )

        indent = (
            "  " * depth
        )

        arguments = (
            get_function_arguments(
                frame
            )
        )

        if arguments:

            call_text = (
                f"{function_name}"
                f"({arguments})"
            )

        else:

            call_text = (
                f"{function_name}()"
            )

        with print_lock:

            print(
                f"{indent}"
                f"[{category:<9}] "
                f"{module_name}."
                f"{call_text}",
                flush=True,
            )

        get_timers()[
            id(frame)
        ] = time.perf_counter()

        set_depth(
            depth + 1
        )

    # =====================================================
    # FUNCTION EXIT
    # =====================================================

    elif event == "return":

        depth = max(
            0,
            get_depth() - 1,
        )

        set_depth(
            depth
        )

        start = (
            get_timers()
            .pop(
                id(frame),
                None,
            )
        )

        if start is None:
            return

        elapsed = (
            time.perf_counter()
            - start
        )

        indent = (
            "  " * depth
        )

        # Only display timing for functions that took
        # meaningful time.
        if elapsed >= 0.010:

            with print_lock:

                print(
                    f"{indent}"
                    f"└─ finished "
                    f"{function_name} "
                    f"in {elapsed:.3f}s",
                    flush=True,
                )


# =========================================================
# ENABLE PROFILING
# =========================================================

sys.setprofile(
    trace_backend
)

# FastAPI may execute normal `def` endpoints in worker
# threads, so profile new threads as well.
threading.setprofile(
    trace_backend
)


# =========================================================
# LOAD FASTAPI
# =========================================================

from backend.main import app


# =========================================================
# REQUEST-LEVEL LOGGER
# =========================================================

@app.middleware(
    "http"
)
async def backend_request_debugger(
    request,
    call_next,
):

    started = (
        time.perf_counter()
    )

    with print_lock:

        print(
            "\n"
            + "=" * 75
        )

        print(
            "BACKEND REQUEST"
        )

        print(
            "-" * 75
        )

        print(
            f"Method : "
            f"{request.method}"
        )

        print(
            f"Path   : "
            f"{request.url.path}"
        )

        if request.url.query:

            print(
                f"Query  : "
                f"{request.url.query}"
            )

        print(
            "-" * 75,
            flush=True,
        )

    try:

        response = await call_next(
            request
        )

    except Exception as exc:

        elapsed = (
            time.perf_counter()
            - started
        )

        with print_lock:

            print(
                "-" * 75
            )

            print(
                "REQUEST FAILED"
            )

            print(
                f"Error  : "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            print(
                f"Time   : "
                f"{elapsed:.3f}s"
            )

            print(
                "=" * 75
                + "\n",
                flush=True,
            )

        raise

    elapsed = (
        time.perf_counter()
        - started
    )

    with print_lock:

        print(
            "-" * 75
        )

        print(
            "REQUEST COMPLETE"
        )

        print(
            f"Status : "
            f"{response.status_code}"
        )

        print(
            f"Time   : "
            f"{elapsed:.3f}s"
        )

        print(
            "=" * 75
            + "\n",
            flush=True,
        )

    return response


# =========================================================
# START UVICORN
# =========================================================

if __name__ == "__main__":

    import uvicorn

    print(
        "\n"
        "AI-Based Village Pond Planning System\n"
        "BACKEND STEP-BY-STEP TRACE MODE\n"
    )

    print(
        "Open the application at:\n"
        "http://127.0.0.1:8000\n"
    )

    print(
        "FastAPI documentation:\n"
        "http://127.0.0.1:8000/docs\n"
    )

    print(
        "Every backend function call will "
        "be shown below.\n"
    )

    print(
        "=" * 75
    )

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="warning",

        # IMPORTANT:
        #
        # Do not use reload here because the reload process
        # would start a separate interpreter and interfere
        # with this profiler.
        reload=False,
    )
