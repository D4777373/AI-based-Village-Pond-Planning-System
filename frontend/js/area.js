// =========================================================
// DRAWN AREA ANALYSIS
// =========================================================
//
// Behaviour:
//
// User draws any practical rectangle
//        ↓
// Browser sends only rectangle coordinates
//        ↓
// Backend temporarily downloads/processes DEM
//        ↓
// Backend returns analysis JSON
//        ↓
// Result is NOT automatically saved
//        ↓
// Browser keeps result temporarily in memory
//        ↓
// User chooses:
//      Save Result as JSON
//      OR
//      Don't Save
// =========================================================


// =========================================================
// ONLY MINIMUM SIZE IS CHECKED ON FRONTEND
// =========================================================
//
// Large-area resource management is handled by backend
// using adaptive analysis resolution.
// =========================================================

const AREA_MIN_SIDE_M = 300;


// =========================================================
// DRAWN AREA LAYER
// =========================================================

const selectedAreaLayer =
    L.featureGroup()
        .addTo(map);


layerControl.addOverlay(
    selectedAreaLayer,
    "Selected Analysis Rectangle"
);


let selectedAreaRectangle = null;


// =========================================================
// LAST RESULT
// =========================================================
//
// This lives only in browser memory.
//
// Refreshing/closing the page removes it unless the user
// explicitly clicks Save Result.
// =========================================================

let lastAreaResult = null;


// =========================================================
// LEAFLET DRAW
// =========================================================

const areaDrawControl =
    new L.Control.Draw({

        position:
            "topleft",

        draw: {

            polyline:
                false,

            polygon:
                false,

            circle:
                false,

            circlemarker:
                false,

            marker:
                false,

            rectangle: {

                shapeOptions: {

                    color:
                        "#7b1fa2",

                    weight:
                        3,

                    dashArray:
                        "8 5",

                    fillColor:
                        "#ab47bc",

                    fillOpacity:
                        0.10,
                },
            },
        },

        edit: {

            featureGroup:
                selectedAreaLayer,

            remove:
                true,
        },
    });


map.addControl(
    areaDrawControl
);


// =========================================================
// ELEMENT HELPERS
// =========================================================

function areaElement(id) {

    return document.getElementById(
        id
    );
}


// =========================================================
// GET BOUNDS
// =========================================================

function getSelectedAreaBounds() {

    if (
        !selectedAreaRectangle
    ) {

        return null;
    }


    const bounds =
        selectedAreaRectangle
            .getBounds();


    return {

        south:
            bounds.getSouth(),

        north:
            bounds.getNorth(),

        west:
            bounds.getWest(),

        east:
            bounds.getEast(),
    };
}


// =========================================================
// DIMENSIONS
// =========================================================

function calculateAreaDimensions(
    bounds
) {

    const centerLatitude =
        (
            bounds.south
            +
            bounds.north
        ) / 2;


    const centerLongitude =
        (
            bounds.west
            +
            bounds.east
        ) / 2;


    const westPoint =
        L.latLng(
            centerLatitude,
            bounds.west
        );


    const eastPoint =
        L.latLng(
            centerLatitude,
            bounds.east
        );


    const southPoint =
        L.latLng(
            bounds.south,
            centerLongitude
        );


    const northPoint =
        L.latLng(
            bounds.north,
            centerLongitude
        );


    const widthM =
        map.distance(
            westPoint,
            eastPoint
        );


    const heightM =
        map.distance(
            southPoint,
            northPoint
        );


    const areaM2 =
        widthM
        *
        heightM;


    return {

        centerLatitude,

        centerLongitude,

        widthM,

        heightM,

        areaM2,

        areaKm2:
            areaM2
            /
            1_000_000,

        areaHectares:
            areaM2
            /
            10_000,
    };
}


// =========================================================
// VALIDATION
// =========================================================

function validateSelectedArea(
    bounds
) {

    const dimensions =
        calculateAreaDimensions(
            bounds
        );


    if (
        dimensions.widthM
        <
        AREA_MIN_SIDE_M
        ||
        dimensions.heightM
        <
        AREA_MIN_SIDE_M
    ) {

        return {

            ok:
                false,

            message:
                (
                    "The selected rectangle is too small. "
                    +
                    `Each side must be at least `
                    +
                    `${AREA_MIN_SIDE_M} m.`
                ),

            dimensions,
        };
    }


    return {

        ok:
            true,

        message:
            "",

        dimensions,
    };
}


// =========================================================
// AREA INFORMATION
// =========================================================

function updateSelectedAreaPanel() {

    const info =
        areaElement(
            "areaInfo"
        );


    const analyzeButton =
        areaElement(
            "analyzeAreaBtn"
        );


    const bounds =
        getSelectedAreaBounds();


    if (!bounds) {

        info.innerHTML = `

            <p>

                No rectangle selected yet.

                Use the rectangle tool in the
                top-left corner of the map.

            </p>
        `;


        analyzeButton.disabled =
            true;


        return;
    }


    const validation =
        validateSelectedArea(
            bounds
        );


    const d =
        validation.dimensions;


    info.innerHTML = `

        <div
            class="
                area-summary
                ${
                    validation.ok
                        ?
                    ""
                        :
                    "area-summary-error"
                }
            "
        >

            <strong>
                Selected analysis area
            </strong>

            <br>

            Width:
            ${
                (
                    d.widthM
                    /
                    1000
                ).toFixed(2)
            } km

            <br>

            Height:
            ${
                (
                    d.heightM
                    /
                    1000
                ).toFixed(2)
            } km

            <br>

            Area:
            ${d.areaKm2.toFixed(2)} km²

            <br>

            Area:
            ${d.areaHectares.toFixed(2)} hectares

            <br>

            Centre:
            ${d.centerLatitude.toFixed(6)},
            ${d.centerLongitude.toFixed(6)}

            <br>

            Bounds:

            <br>

            South:
            ${bounds.south.toFixed(6)}

            <br>

            North:
            ${bounds.north.toFixed(6)}

            <br>

            West:
            ${bounds.west.toFixed(6)}

            <br>

            East:
            ${bounds.east.toFixed(6)}


            ${
                validation.ok
                    ?
                `
                    <div class="area-selection-note">

                        Larger selected areas are allowed.

                        The backend automatically uses
                        a coarser analysis grid when
                        necessary to control memory usage.

                    </div>
                `
                    :
                `
                    <div
                        class="area-validation-error"
                    >

                        ${validation.message}

                    </div>
                `
            }

        </div>
    `;


    analyzeButton.disabled =
        !validation.ok;
}


// =========================================================
// CLEAR SAVE CHOICE
// =========================================================

function hideAreaSaveChoice() {

    const panel =
        areaElement(
            "areaSavePanel"
        );


    if (panel) {

        panel.hidden =
            true;
    }
}


// =========================================================
// SHOW SAVE CHOICE
// =========================================================

function showAreaSaveChoice(
    data
) {

    lastAreaResult =
        data;


    const panel =
        areaElement(
            "areaSavePanel"
        );


    const text =
        areaElement(
            "areaSaveMessage"
        );


    if (
        !panel
        ||
        !text
    ) {

        return;
    }


    const area =
        data.area_selection;


    text.textContent =
        (
            "Analysis completed successfully. "
            +
            `Area: ${Number(area.area_km2).toFixed(2)} km² `
            +
            `(${Number(area.area_hectares).toFixed(2)} hectares). `
            +
            "The server has not saved this analysis. "
            +
            "Do you want to save the result as a JSON file?"
        );


    panel.hidden =
        false;
}


// =========================================================
// ANALYSIS SUMMARY
// =========================================================

function showAreaRuntimeSummary(
    data
) {

    const panel =
        areaElement(
            "areaGeneratedFiles"
        );


    const area =
        data.area_selection;


    const source =
        data.source_dem;


    const policy =
        data.storage_policy;


    if (
        !area
        ||
        !source
    ) {

        panel.innerHTML =
            "";

        return;
    }


    panel.innerHTML = `

        <div class="generated-summary">

            <strong>
                Analysis mode:
            </strong>

            Drawn rectangle

            <br>


            <strong>
                Area:
            </strong>

            ${Number(area.area_km2).toFixed(2)}
            km²

            (${Number(area.area_hectares).toFixed(2)}
            hectares)

            <br>


            <strong>
                Rectangle size:
            </strong>

            ${
                (
                    Number(area.width_m)
                    /
                    1000
                ).toFixed(2)
            } km

            ×

            ${
                (
                    Number(area.height_m)
                    /
                    1000
                ).toFixed(2)
            } km

            <br>


            <strong>
                DEM source:
            </strong>

            ${source.dataset}

            <br>


            <strong>
                Requested grid resolution:
            </strong>

            ${source.requested_analysis_resolution_m}
            m

            <br>


            <strong>
                Effective grid resolution:
            </strong>

            ${source.analysis_grid_resolution_m}
            m

            <br>


            <strong>
                Estimated analysis cells:
            </strong>

            ${Number(
                source.estimated_grid_cells
            ).toLocaleString()}

            <br>


            <strong>
                Automatic resolution adjustment:
            </strong>

            ${
                source.adaptive_resolution
                    ?
                "Yes"
                    :
                "No"
            }

            <br>


            <strong>
                Server persistence:
            </strong>

            ${
                policy?.server_result_saved
                    ?
                "Saved"
                    :
                "Not saved"
            }

            <br>


            <strong>
                Temporary processing:
            </strong>

            ${
                policy?.temporary_processing
                    ?
                "Yes"
                    :
                "No"
            }

        </div>
    `;
}


// =========================================================
// BUILD API REQUEST
// =========================================================

function buildAreaAnalysisForm(
    bounds
) {

    const form =
        new FormData();


    form.append(
        "south",
        bounds.south.toString()
    );


    form.append(
        "north",
        bounds.north.toString()
    );


    form.append(
        "west",
        bounds.west.toString()
    );


    form.append(
        "east",
        bounds.east.toString()
    );


    form.append(
        "contour_interval_m",
        areaElement(
            "areaContourInterval"
        ).value
        ||
        "5"
    );


    form.append(
        "resolution_m",
        areaElement(
            "resolution"
        ).value
        ||
        "30"
    );


    form.append(
        "max_candidates",
        areaElement(
            "maxCandidates"
        ).value
        ||
        "20"
    );


    form.append(
        "rainfall_years",
        areaElement(
            "rainfallYears"
        ).value
        ||
        "5"
    );


    form.append(
        "runoff_coefficient",
        areaElement(
            "runoffCoefficient"
        ).value
        ||
        "0.30"
    );


    form.append(
        "pond_radius_m",
        areaElement(
            "pondRadius"
        ).value
        ||
        "40"
    );


    form.append(
        "max_pond_depth_m",
        areaElement(
            "maxDepth"
        ).value
        ||
        "3"
    );


    return form;
}


// =========================================================
// RECTANGLE CREATED
// =========================================================

map.on(

    L.Draw.Event.CREATED,

    function (
        event
    ) {

        if (
            event.layerType
            !==
            "rectangle"
        ) {

            return;
        }


        selectedAreaLayer
            .clearLayers();


        selectedAreaRectangle =
            event.layer;


        selectedAreaRectangle
            .addTo(
                selectedAreaLayer
            );


        lastAreaResult =
            null;


        hideAreaSaveChoice();


        updateSelectedAreaPanel();
    }
);


// =========================================================
// RECTANGLE EDITED
// =========================================================

map.on(

    L.Draw.Event.EDITED,

    function () {

        const layers =
            selectedAreaLayer
                .getLayers();


        selectedAreaRectangle =
            layers.length
                ?
            layers[0]
                :
            null;


        lastAreaResult =
            null;


        hideAreaSaveChoice();


        updateSelectedAreaPanel();
    }
);


// =========================================================
// RECTANGLE DELETED
// =========================================================

map.on(

    L.Draw.Event.DELETED,

    function () {

        const layers =
            selectedAreaLayer
                .getLayers();


        selectedAreaRectangle =
            layers.length
                ?
            layers[0]
                :
            null;


        lastAreaResult =
            null;


        hideAreaSaveChoice();


        updateSelectedAreaPanel();
    }
);


// =========================================================
// CLEAR SELECTED AREA
// =========================================================

areaElement(
    "clearAreaBtn"
)
.addEventListener(

    "click",

    function () {

        selectedAreaLayer
            .clearLayers();


        selectedAreaRectangle =
            null;


        lastAreaResult =
            null;


        areaElement(
            "areaStatus"
        ).textContent =
            "";


        areaElement(
            "areaGeneratedFiles"
        ).innerHTML =
            "";


        hideAreaSaveChoice();


        updateSelectedAreaPanel();
    }
);


// =========================================================
// ANALYZE
// =========================================================

areaElement(
    "analyzeAreaBtn"
)
.addEventListener(

    "click",

    async function () {

        const status =
            areaElement(
                "areaStatus"
            );


        const bounds =
            getSelectedAreaBounds();


        if (!bounds) {

            status.textContent =
                "Draw a rectangle on the map first.";

            return;
        }


        const validation =
            validateSelectedArea(
                bounds
            );


        if (
            !validation.ok
        ) {

            status.textContent =
                validation.message;

            return;
        }


        lastAreaResult =
            null;


        hideAreaSaveChoice();


        areaElement(
            "areaGeneratedFiles"
        ).innerHTML =
            "";


        status.textContent =
            (
                "Analyzing selected area: "
                +
                "temporary DEM download → "
                +
                "contour generation → "
                +
                "hydrology → "
                +
                "land filtering → "
                +
                "rainfall → "
                +
                "pond ranking..."
            );


        try {

            const response =
                await fetch(

                    "/api/analyzeArea",

                    {

                        method:
                            "POST",

                        body:
                            buildAreaAnalysisForm(
                                bounds
                            ),
                    }
                );


            let data;


            try {

                data =
                    await response.json();

            }

            catch (
                error
            ) {

                throw new Error(
                    "Backend returned an invalid response."
                );
            }


            if (
                !response.ok
            ) {

                throw new Error(
                    data.detail
                    ||
                    "Rectangle analysis failed."
                );
            }


            // =============================================
            // GENERATED CONTOURS
            // =============================================

            if (
                data
                    .generated_contours
                    ?.geojson
            ) {

                drawGeneratedContours(
                    data
                        .generated_contours
                        .geojson
                );
            }


            // =============================================
            // EXISTING UI
            // =============================================

            showResults(
                data
            );


            drawAnalysis(
                data
            );


            renderCandidateTable(
                data
            );


            showAreaRuntimeSummary(
                data
            );


            if (
                selectedAreaRectangle
            ) {

                selectedAreaRectangle
                    .bringToFront();
            }


            const candidateCount =
                Array.isArray(
                    data.candidates
                )
                    ?
                data.candidates.length
                    :
                0;


            status.textContent =
                (
                    "Analysis completed successfully. "
                    +
                    `${candidateCount} candidate site(s) `
                    +
                    "were found. "
                    +
                    "Nothing has been saved automatically."
                );


            // =============================================
            // USER NOW DECIDES WHETHER TO SAVE
            // =============================================

            showAreaSaveChoice(
                data
            );

        }

        catch (
            error
        ) {

            console.error(
                error
            );


            lastAreaResult =
                null;


            hideAreaSaveChoice();


            status.textContent =
                (
                    "Error: "
                    +
                    error.message
                );
        }
    }
);


// =========================================================
// SAVE RESULT LOCALLY
// =========================================================
//
// No backend storage.
//
// Browser creates a JSON download only when user clicks.
// =========================================================

areaElement(
    "saveAreaResultBtn"
)
.addEventListener(

    "click",

    function () {

        if (
            !lastAreaResult
        ) {

            areaElement(
                "areaSaveMessage"
            ).textContent =
                (
                    "There is no rectangle "
                    +
                    "analysis result to save."
                );

            return;
        }


        const jsonText =
            JSON.stringify(
                lastAreaResult,
                null,
                2
            );


        const blob =
            new Blob(
                [
                    jsonText
                ],
                {
                    type:
                        "application/json",
                }
            );


        const url =
            URL.createObjectURL(
                blob
            );


        const link =
            document.createElement(
                "a"
            );


        const timestamp =
            new Date()
                .toISOString()
                .replace(
                    /[:.]/g,
                    "-"
                );


        link.href =
            url;


        link.download =
            (
                "pond-analysis-"
                +
                timestamp
                +
                ".json"
            );


        document.body
            .appendChild(
                link
            );


        link.click();


        link.remove();


        URL.revokeObjectURL(
            url
        );


        areaElement(
            "areaSaveMessage"
        ).textContent =
            (
                "Result downloaded successfully. "
                +
                "The backend still has not stored "
                +
                "the analysis result."
            );
    }
);


// =========================================================
// DON'T SAVE
// =========================================================

areaElement(
    "discardAreaResultBtn"
)
.addEventListener(

    "click",

    function () {

        lastAreaResult =
            null;


        hideAreaSaveChoice();


        areaElement(
            "areaStatus"
        ).textContent =
            (
                "Result was not saved. "
                +
                "The displayed map analysis remains "
                +
                "visible until another analysis or "
                +
                "page refresh."
            );
    }
);


// =========================================================
// INITIAL STATE
// =========================================================

hideAreaSaveChoice();

updateSelectedAreaPanel();

// =========================================================
// MAP PLACE SEARCH / AUTOCOMPLETE
// =========================================================
//
// Search source:
//
// Photon
//   ↓
// OpenStreetMap place index
//
// This is independent of the selected base map.
//
// Therefore it works while viewing:
//
// Street Map
// Satellite Map
//
// Search results are not stored by this application.
// =========================================================


// =========================================================
// SEARCH STATE
// =========================================================

let placeSearchTimer =
    null;


let placeSearchController =
    null;


let placeSearchMarker =
    null;


let currentPlaceSuggestions =
    [];


// Wait briefly after each keystroke before sending request.
//
// User:
//
// C
// Ch
// Cha
//
// produces approximately one request after the user pauses,
// rather than three immediate requests.
const PLACE_SEARCH_DEBOUNCE_MS =
    450;


// Require at least two characters.
const PLACE_SEARCH_MIN_LENGTH =
    2;


// =========================================================
// ELEMENTS
// =========================================================

const mapPlaceSearchInput =
    document.getElementById(
        "mapPlaceSearch"
    );


const mapPlaceSuggestions =
    document.getElementById(
        "mapPlaceSuggestions"
    );


const mapPlaceSearchStatus =
    document.getElementById(
        "mapPlaceSearchStatus"
    );


const clearMapPlaceSearchBtn =
    document.getElementById(
        "clearMapPlaceSearchBtn"
    );


// =========================================================
// REMOVE SUGGESTION LIST
// =========================================================

function clearPlaceSuggestions() {

    currentPlaceSuggestions =
        [];


    mapPlaceSuggestions
        .replaceChildren();


    mapPlaceSuggestions.hidden =
        true;
}


// =========================================================
// REMOVE SEARCH MARKER
// =========================================================

function removePlaceSearchMarker() {

    if (
        placeSearchMarker
    ) {

        map.removeLayer(
            placeSearchMarker
        );


        placeSearchMarker =
            null;
    }
}


// =========================================================
// BUILD ONE SUGGESTION
// =========================================================

function createPlaceSuggestion(
    place,
    index
) {

    const button =
        document.createElement(
            "button"
        );


    button.type =
        "button";


    button.className =
        "map-place-suggestion";


    button.setAttribute(
        "role",
        "option"
    );


    // -----------------------------------------------------
    // MAIN NAME
    // -----------------------------------------------------

    const title =
        document.createElement(
            "span"
        );


    title.className =
        "map-place-suggestion-name";


    title.textContent =
        (
            place.name
            ||
            place.label
        );


    // -----------------------------------------------------
    // FULL ADDRESS / LOCATION
    // -----------------------------------------------------

    const detail =
        document.createElement(
            "span"
        );


    detail.className =
        "map-place-suggestion-detail";


    detail.textContent =
        place.label;


    button.append(
        title,
        detail
    );


    // -----------------------------------------------------
    // SELECT
    // -----------------------------------------------------

    button.addEventListener(

        "click",

        function () {

            selectPlaceSuggestion(
                place
            );
        }
    );


    return button;
}


// =========================================================
// RENDER SUGGESTIONS
// =========================================================

function renderPlaceSuggestions(
    places
) {

    clearPlaceSuggestions();


    currentPlaceSuggestions =
        places;


    if (
        places.length === 0
    ) {

        mapPlaceSearchStatus
            .textContent =
                "No matching place found in India.";


        return;
    }


    const fragment =
        document.createDocumentFragment();


    places.forEach(

        function (
            place,
            index
        ) {

            fragment.appendChild(

                createPlaceSuggestion(
                    place,
                    index
                )
            );
        }
    );


    mapPlaceSuggestions
        .appendChild(
            fragment
        );


    mapPlaceSuggestions.hidden =
        false;


    mapPlaceSearchStatus
        .textContent =
            (
                `${places.length} `
                +
                "matching place(s) found."
            );
}


// =========================================================
// SELECT PLACE
// =========================================================

function selectPlaceSuggestion(
    place
) {

    clearPlaceSuggestions();


    mapPlaceSearchInput.value =
        place.label;


    removePlaceSearchMarker();


    const latitude =
        Number(
            place.latitude
        );


    const longitude =
        Number(
            place.longitude
        );


    // -----------------------------------------------------
    // ADD TEMPORARY SEARCH MARKER
    // -----------------------------------------------------

    placeSearchMarker =
        L.marker(
            [
                latitude,
                longitude,
            ]
        )
        .addTo(
            map
        );


    placeSearchMarker
        .bindPopup(

            `
                <div class="popup-content">

                    <strong>
                        ${escapePlaceText(
                            place.name
                            ||
                            place.label
                        )}
                    </strong>

                    <br>

                    ${escapePlaceText(
                        place.label
                    )}

                    <br><br>

                    Latitude:
                    ${latitude.toFixed(6)}

                    <br>

                    Longitude:
                    ${longitude.toFixed(6)}

                    <br><br>

                    Zoom or switch to satellite,
                    then draw the analysis rectangle.

                </div>
            `
        )
        .openPopup();


    // -----------------------------------------------------
    // IF RESULT HAS A FEATURE EXTENT
    // -----------------------------------------------------

    if (
        Array.isArray(
            place.extent
        )
        &&
        place.extent.length >= 4
    ) {

        const minLon =
            Number(
                place.extent[0]
            );


        const maxLat =
            Number(
                place.extent[1]
            );


        const maxLon =
            Number(
                place.extent[2]
            );


        const minLat =
            Number(
                place.extent[3]
            );


        if (
            Number.isFinite(
                minLon
            )
            &&
            Number.isFinite(
                maxLat
            )
            &&
            Number.isFinite(
                maxLon
            )
            &&
            Number.isFinite(
                minLat
            )
        ) {

            map.fitBounds(

                [
                    [
                        minLat,
                        minLon,
                    ],

                    [
                        maxLat,
                        maxLon,
                    ],
                ],

                {
                    padding:
                        [
                            40,
                            40,
                        ],

                    maxZoom:
                        16,
                }
            );
        }

        else {

            map.flyTo(
                [
                    latitude,
                    longitude,
                ],
                15
            );
        }
    }

    else {

        map.flyTo(
            [
                latitude,
                longitude,
            ],
            15
        );
    }


    mapPlaceSearchStatus
        .textContent =
            (
                `Map moved to ${place.label}. `
                +
                "Now draw the rectangle around "
                +
                "the terrain you want to analyze."
            );
}


// =========================================================
// BASIC HTML ESCAPE FOR POPUP
// =========================================================

function escapePlaceText(
    value
) {

    return String(
        value
        ??
        ""
    )

    .replace(
        /&/g,
        "&amp;"
    )

    .replace(
        /</g,
        "&lt;"
    )

    .replace(
        />/g,
        "&gt;"
    )

    .replace(
        /"/g,
        "&quot;"
    )

    .replace(
        /'/g,
        "&#039;"
    );
}


// =========================================================
// CALL BACKEND
// =========================================================

async function searchMapPlaces(
    query
) {

    // Abort an old request if the user has already
    // typed something else.
    if (
        placeSearchController
    ) {

        placeSearchController
            .abort();
    }


    placeSearchController =
        new AbortController();


    const center =
        map.getCenter();


    const zoom =
        Math.round(
            map.getZoom()
        );


    const params =
        new URLSearchParams({

            q:
                query,

            lat:
                center.lat
                    .toString(),

            lon:
                center.lng
                    .toString(),

            zoom:
                zoom
                    .toString(),
        });


    mapPlaceSearchStatus
        .textContent =
            "Searching mapped places...";


    try {

        const response =
            await fetch(

                (
                    "/api/searchPlaces?"
                    +
                    params.toString()
                ),

                {
                    signal:
                        placeSearchController
                            .signal,

                    cache:
                        "no-store",
                }
            );


        const data =
            await response.json();


        if (
            !response.ok
        ) {

            throw new Error(
                data.detail
                ||
                "Place search failed."
            );
        }


        renderPlaceSuggestions(
            Array.isArray(
                data.items
            )
                ?
            data.items
                :
            []
        );

    }

    catch (
        error
    ) {

        // Abort is normal when user keeps typing.
        if (
            error.name
            ===
            "AbortError"
        ) {

            return;
        }


        console.error(
            error
        );


        clearPlaceSuggestions();


        mapPlaceSearchStatus
            .textContent =
                (
                    "Place search error: "
                    +
                    error.message
                );
    }
}


// =========================================================
// SEARCH-AS-YOU-TYPE
// =========================================================

mapPlaceSearchInput
    .addEventListener(

        "input",

        function () {

            const query =
                mapPlaceSearchInput
                    .value
                    .trim();


            clearTimeout(
                placeSearchTimer
            );


            if (
                placeSearchController
            ) {

                placeSearchController
                    .abort();
            }


            if (
                query.length
                <
                PLACE_SEARCH_MIN_LENGTH
            ) {

                clearPlaceSuggestions();


                mapPlaceSearchStatus
                    .textContent =
                        (
                            query.length === 0
                                ?
                            ""
                                :
                            "Type at least 2 characters."
                        );


                return;
            }


            placeSearchTimer =
                setTimeout(

                    function () {

                        searchMapPlaces(
                            query
                        );
                    },

                    PLACE_SEARCH_DEBOUNCE_MS
                );
        }
    );


// =========================================================
// CLEAR BUTTON
// =========================================================

clearMapPlaceSearchBtn
    .addEventListener(

        "click",

        function () {

            clearTimeout(
                placeSearchTimer
            );


            if (
                placeSearchController
            ) {

                placeSearchController
                    .abort();
            }


            mapPlaceSearchInput.value =
                "";


            mapPlaceSearchStatus
                .textContent =
                    "";


            clearPlaceSuggestions();


            removePlaceSearchMarker();


            mapPlaceSearchInput
                .focus();
        }
    );


// =========================================================
// CLOSE SUGGESTIONS WHEN CLICKING ELSEWHERE
// =========================================================

document.addEventListener(

    "click",

    function (
        event
    ) {

        const searchContainer =
            document.querySelector(
                ".map-place-search"
            );


        if (
            searchContainer
            &&
            !searchContainer.contains(
                event.target
            )
        ) {

            clearPlaceSuggestions();
        }
    }
);


// =========================================================
// ESCAPE KEY
// =========================================================

mapPlaceSearchInput
    .addEventListener(

        "keydown",

        function (
            event
        ) {

            if (
                event.key
                ===
                "Escape"
            ) {

                clearPlaceSuggestions();
            }
        }
    );
