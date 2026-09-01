from __future__ import annotations

import json
import sys
import threading
import time
from collections import OrderedDict, defaultdict
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from fastapi.testclient import TestClient


# ============================================================
# PROJECT
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Import normal production FastAPI app.
from backend.main import app


# ============================================================
# INPUT / OUTPUT
# ============================================================

CONTOUR_FILE = PROJECT_ROOT / "contours_1m.kml"

JSON_OUTPUT = Path("/tmp/phase2_response.json")

RAW_BACKEND_LOG = Path(
    "/tmp/phase2_backend_raw.log"
)


# ============================================================
# PIPELINE STAGES
# ============================================================
#
# IMPORTANT:
#
# We match EXACT Python source files.
#
# Therefore:
#
# candidate.py
#
# means backend/pond/candidate.py,
#
# NOT response.PondCandidate.
#
# This fixes the false-positive problem in the earlier tracer.
# ============================================================

STAGES = OrderedDict(
    [
        (
            "API Endpoint",
            PROJECT_ROOT
            / "backend/api/contour_routes.py",
        ),
        (
            "Analysis Service",
            PROJECT_ROOT
            / "backend/services/analysis_service.py",
        ),
        (
            "KML Parsing",
            PROJECT_ROOT
            / "backend/services/kml_service.py",
        ),
        (
            "DEM Generation",
            PROJECT_ROOT
            / "backend/terrain/dem_generator.py",
        ),
        (
            "Slope Calculation",
            PROJECT_ROOT
            / "backend/terrain/slope.py",
        ),
        (
            "Sink Filling",
            PROJECT_ROOT
            / "backend/hydrology/sink_fill.py",
        ),
        (
            "Flow Direction D8",
            PROJECT_ROOT
            / "backend/hydrology/flow_direction.py",
        ),
        (
            "Flow Accumulation",
            PROJECT_ROOT
            / "backend/hydrology/flow_accumulation.py",
        ),
        (
            "Land Filtering",
            PROJECT_ROOT
            / "backend/services/land_service.py",
        ),
        (
            "Pond Candidates",
            PROJECT_ROOT
            / "backend/pond/candidate.py",
        ),
        (
            "Catchment Delineation",
            PROJECT_ROOT
            / "backend/hydrology/catchment.py",
        ),
        (
            "Historical Rainfall",
            PROJECT_ROOT
            / "backend/services/rainfall_service.py",
        ),
        (
            "Pond / Runoff Metrics",
            PROJECT_ROOT
            / "backend/pond/metrics.py",
        ),
    ]
)


# ============================================================
# NORMALIZED FILE -> STAGE LOOKUP
# ============================================================

FILE_TO_STAGE = {
    str(path.resolve()): stage
    for stage, path in STAGES.items()
}


# ============================================================
# PER-STAGE RUNTIME DATA
# ============================================================

stage_data = {}

for stage in STAGES:

    stage_data[stage] = {
        "reached": False,
        "total_seconds": 0.0,
        "calls": 0,
        "functions": set(),
        "depth": defaultdict(int),
        "start": {},
    }


# ============================================================
# SHARED STATE
# ============================================================

state_lock = threading.RLock()

request_active = threading.Event()

request_start_time = None

current_stage = "Waiting"

stop_progress = threading.Event()


# ============================================================
# PRINT DIRECTLY TO REAL TERMINAL
# ============================================================
#
# Backend print() output is redirected into a raw log.
#
# Our progress output still goes to the user's terminal.
# ============================================================

def console(
    text: str = "",
    end: str = "\n",
):
    sys.__stdout__.write(
        text + end
    )
    sys.__stdout__.flush()


# ============================================================
# CLEAR CURRENT LIVE BAR
# ============================================================

def clear_live_line():
    console(
        "\r"
        + (" " * 150)
        + "\r",
        end="",
    )


# ============================================================
# PROGRESS
# ============================================================

def reached_count():
    with state_lock:
        return sum(
            1
            for value in stage_data.values()
            if value["reached"]
        )


def progress_percent():

    total = len(
        STAGES
    )

    reached = reached_count()

    if total == 0:
        return 0

    return int(
        reached
        /
        total
        *
        100
    )


def draw_progress():

    if not request_active.is_set():
        return

    with state_lock:

        percent = progress_percent()

        stage = current_stage

        if request_start_time is None:
            elapsed = 0.0
        else:
            elapsed = (
                time.perf_counter()
                -
                request_start_time
            )

    width = 38

    filled = int(
        width
        *
        percent
        /
        100
    )

    bar = (
        "#"
        *
        filled
        +
        "-"
        *
        (
            width
            -
            filled
        )
    )

    message = (
        f"\r[{bar}] "
        f"{percent:3d}%  "
        f"ACTIVE: {stage:<24} "
        f"Elapsed: {elapsed:7.2f}s"
    )

    console(
        message,
        end="",
    )


def progress_worker():

    while not stop_progress.is_set():

        if request_active.is_set():

            draw_progress()

        time.sleep(
            0.20
        )


# ============================================================
# PYTHON PROFILER
# ============================================================
#
# This captures actual functions executed from the selected
# backend source files.
#
# Timing behaviour:
#
# If a module function calls helper functions from the SAME
# module, we count the outer execution once so nested helper
# calls are not double-counted.
#
# If catchment is called 20 times for 20 candidates, all
# invocation times are accumulated.
# ============================================================

def backend_profiler(
    frame,
    event,
    arg,
):

    global current_stage

    if not request_active.is_set():
        return

    filename = str(
        Path(
            frame.f_code.co_filename
        ).resolve()
    )

    stage = FILE_TO_STAGE.get(
        filename
    )

    if stage is None:
        return

    function_name = (
        frame.f_code.co_name
    )

    # Ignore module loading / class setup noise.
    if (
        function_name == "<module>"
        or function_name.startswith("__")
    ):
        return

    thread_id = (
        threading.get_ident()
    )

    info = stage_data[
        stage
    ]

    # --------------------------------------------------------
    # FUNCTION ENTER
    # --------------------------------------------------------

    if event == "call":

        with state_lock:

            old_depth = (
                info["depth"][
                    thread_id
                ]
            )

            # This is the outermost call in this module
            # for this thread.
            if old_depth == 0:

                info["start"][
                    thread_id
                ] = (
                    time.perf_counter()
                )

                info["calls"] += 1

            info["depth"][
                thread_id
            ] = (
                old_depth + 1
            )

            info["functions"].add(
                function_name
            )

            if not info[
                "reached"
            ]:

                info[
                    "reached"
                ] = True

            current_stage = stage

    # --------------------------------------------------------
    # FUNCTION RETURN
    # --------------------------------------------------------

    elif event == "return":

        with state_lock:

            depth = (
                info["depth"].get(
                    thread_id,
                    0,
                )
            )

            if depth <= 0:
                return

            depth -= 1

            info["depth"][
                thread_id
            ] = depth

            # Outermost call from this module has completed.
            if depth == 0:

                started = (
                    info["start"]
                    .pop(
                        thread_id,
                        None,
                    )
                )

                if started is not None:

                    info[
                        "total_seconds"
                    ] += (
                        time.perf_counter()
                        -
                        started
                    )


# ============================================================
# FINAL TABLE
# ============================================================

def print_final_report(
    *,
    status_code: int,
    total_seconds: float,
    candidate_count,
):

    clear_live_line()

    console()
    console(
        "=" * 112
    )

    console(
        "PHASE 2 - LIVE BACKEND TERRAIN & CATCHMENT PIPELINE RESULT"
    )

    console(
        "=" * 112
    )

    console(
        f"{'STAGE':<25}"
        f"{'ACTUAL FUNCTION(S)':<45}"
        f"{'CALLS':>8}"
        f"{'TIME':>14}"
        f"{'RESULT':>12}"
    )

    console(
        "-" * 112
    )

    all_found = True

    for stage in STAGES:

        info = stage_data[
            stage
        ]

        if info[
            "reached"
        ]:

            functions = ", ".join(
                sorted(
                    info[
                        "functions"
                    ]
                )
            )

            if len(
                functions
            ) > 42:

                functions = (
                    functions[:39]
                    +
                    "..."
                )

            result = "PASS"

            timing = (
                f"{info['total_seconds']:.4f}s"
            )

        else:

            functions = (
                "NOT EXECUTED"
            )

            result = "CHECK"

            timing = "-"

            all_found = False

        console(
            f"{stage:<25}"
            f"{functions:<45}"
            f"{info['calls']:>8}"
            f"{timing:>14}"
            f"{result:>12}"
        )

    console(
        "-" * 112
    )

    http_result = (
        "PASS"
        if status_code == 200
        else
        "FAIL"
    )

    console(
        f"{'HTTP Response':<25}"
        f"{'POST /api/analyzeContour':<45}"
        f"{1:>8}"
        f"{total_seconds:>13.4f}s"
        f"{http_result:>12}"
    )

    console(
        "=" * 112
    )

    console(
        f"HTTP STATUS CODE     : {status_code}"
    )

    console(
        f"TOTAL REQUEST TIME   : {total_seconds:.4f} seconds"
    )

    console(
        f"POND CANDIDATE COUNT : {candidate_count}"
    )

    console(
        f"JSON RESPONSE SAVED  : {JSON_OUTPUT}"
    )

    console(
        f"RAW BACKEND LOG      : {RAW_BACKEND_LOG}"
    )

    console()

    # HTTP 200 is the most important request-level result.
    if status_code == 200:

        console(
            "FINAL API RESULT      : PASS"
        )

    else:

        console(
            "FINAL API RESULT      : FAIL"
        )

    if all_found:

        console(
            "PIPELINE VERIFICATION : PASS - all monitored stages executed."
        )

    else:

        console(
            "PIPELINE VERIFICATION : CHECK - one or more monitored "
            "modules were not executed."
        )

    console(
        "=" * 112
    )

    console()
    console(
        "NOTE:"
    )

    console(
        "API Endpoint and Analysis Service are wrapper timings and "
        "therefore include downstream processing."
    )

    console(
        "Do not add all timing rows together. Catchment/metrics may "
        "be called multiple times, and their displayed time is the "
        "cumulative runtime across those calls."
    )


# ============================================================
# MAIN TEST
# ============================================================

def main():

    global request_start_time
    global current_stage

    # --------------------------------------------------------
    # Validate sample file
    # --------------------------------------------------------

    if not CONTOUR_FILE.exists():

        console(
            f"ERROR: {CONTOUR_FILE} does not exist."
        )

        raise SystemExit(
            1
        )

    console()
    console(
        "=" * 90
    )

    console(
        "PHASE 2 REAL-TIME BACKEND PIPELINE TEST"
    )

    console(
        "=" * 90
    )

    console(
        f"Input file : {CONTOUR_FILE.name}"
    )

    console(
        "Endpoint   : POST /api/analyzeContour"
    )

    console(
        "Resolution : 10 m"
    )

    console(
        "Candidates : 20"
    )

    console(
        "Rainfall   : 5 years"
    )

    console()

    console(
        "Starting actual FastAPI endpoint..."
    )

    console()

    # --------------------------------------------------------
    # Progress thread
    # --------------------------------------------------------

    worker = threading.Thread(
        target=progress_worker,
        daemon=True,
    )

    worker.start()

    # --------------------------------------------------------
    # Enable Python profiler
    # --------------------------------------------------------

    sys.setprofile(
        backend_profiler
    )

    threading.setprofile(
        backend_profiler
    )

    client = TestClient(
        app
    )

    status_code = 0

    candidate_count = "N/A"

    response = None

    request_start_time = (
        time.perf_counter()
    )

    current_stage = (
        "API request starting"
    )

    request_active.set()

    try:

        # Keep normal backend print statements out of the clean
        # progress report. They remain available in this raw log.
        with RAW_BACKEND_LOG.open(
            "w",
            encoding="utf-8",
        ) as raw_log:

            with redirect_stdout(
                raw_log
            ), redirect_stderr(
                raw_log
            ):

                with CONTOUR_FILE.open(
                    "rb"
                ) as contour:

                    response = (
                        client.post(
                            "/api/analyzeContour",
                            files={
                                "file": (
                                    CONTOUR_FILE.name,
                                    contour,
                                    "application/vnd.google-earth.kml+xml",
                                )
                            },
                            data={
                                "resolution_m":
                                    "10",

                                "max_candidates":
                                    "20",

                                "rainfall_years":
                                    "5",

                                "runoff_coefficient":
                                    "0.30",

                                "pond_radius_m":
                                    "40",

                                "max_pond_depth_m":
                                    "3",
                            },
                        )
                    )

        status_code = (
            response.status_code
        )

    except Exception as exc:

        clear_live_line()

        console(
            f"TEST ERROR: {type(exc).__name__}: {exc}"
        )

    finally:

        total_seconds = (
            time.perf_counter()
            -
            request_start_time
        )

        request_active.clear()

        stop_progress.set()

        worker.join(
            timeout=1.0
        )

        sys.setprofile(
            None
        )

        threading.setprofile(
            None
        )

    # --------------------------------------------------------
    # SAVE / READ RESPONSE
    # --------------------------------------------------------

    if response is not None:

        try:

            response_data = (
                response.json()
            )

            JSON_OUTPUT.write_text(
                json.dumps(
                    response_data,
                    indent=2,
                ),
                encoding="utf-8",
            )

            candidates = (
                response_data.get(
                    "candidates",
                    []
                )
                if isinstance(
                    response_data,
                    dict,
                )
                else
                []
            )

            candidate_count = (
                len(
                    candidates
                )
                if isinstance(
                    candidates,
                    list,
                )
                else
                "N/A"
            )

        except Exception:

            JSON_OUTPUT.write_text(
                response.text,
                encoding="utf-8",
            )

    # --------------------------------------------------------
    # FINAL 100% BAR
    # --------------------------------------------------------

    clear_live_line()

    width = 38

    console(
        f"[{'#' * width}] "
        f"100%  "
        f"REQUEST COMPLETE  "
        f"Elapsed: {total_seconds:.2f}s"
    )

    # --------------------------------------------------------
    # FINAL RESULT TABLE
    # --------------------------------------------------------

    print_final_report(
        status_code=
            status_code,

        total_seconds=
            total_seconds,

        candidate_count=
            candidate_count,
    )


if __name__ == "__main__":
    main()
