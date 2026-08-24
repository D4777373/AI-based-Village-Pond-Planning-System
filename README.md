# -AI-based-Village-Pond-Planning-System
AI-Based Village Pond Planning System that uses geospatial, elevation, rainfall, and land data to identify suitable pond locations, estimate catchment area and runoff, recommend pond depth and storage capacity, and visualize results on an interactive map.

````markdown
# AI-Based Village Pond Planning System

> 🚧 **Project Status: Under Construction**
>
> This project is currently under active development and is not yet complete.  
> Some backend modules, APIs, datasets, frontend features, validation steps, and deployment components are still being implemented and refined.

---

## Overview

The **AI-Based Village Pond Planning System** is a geospatial web application designed to identify suitable locations for pond construction using terrain elevation, hydrology, rainfall, and land-availability information.

The system analyzes contour maps and terrain elevation data to estimate drainage behavior and identify possible pond locations.

The final goal is to recommend and rank suitable pond sites and visualize the analysis on an interactive real-world map.

---

## Problem Statement

Water conservation is an important challenge in rural areas.

One effective solution is the construction of ponds at suitable locations to collect and store surface runoff.

Selecting a pond location requires analysis of multiple factors such as:

- Terrain elevation
- Terrain slope
- Drainage direction
- Flow accumulation
- Catchment area
- Historical rainfall
- Estimated runoff
- Existing rivers and water bodies
- Roads and buildings
- Pond dimensions
- Approximate storage capacity

This project aims to automate these calculations and provide an interactive map-based interface for pond planning.

---

## Current Development Progress

The following components are currently implemented or under active development:

- KML/KMZ contour map parsing
- Contour elevation extraction
- Contour-to-DEM generation
- Terrain slope calculation
- DEM sink/depression filling
- D8 flow-direction calculation
- Flow-accumulation analysis
- Catchment delineation
- Multiple pond-candidate identification
- Pond suitability ranking
- Historical rainfall integration
- Runoff estimation
- Pond depth estimation
- Pond storage-capacity estimation
- River and water-body exclusion
- Road and building exclusion using OpenStreetMap
- Interactive Leaflet map
- Street-map visualization
- Satellite-map visualization
- Original contour-map overlay
- Contour elevation display in metres AMSL
- Catchment visualization
- Candidate-site visualization
- Automatic location-based DEM download using OpenTopography
- Automatic contour generation from downloaded DEM data

---

## Planned / Ongoing Work

The project is still being extended with features such as:

- India State → District → Sub-District → Village selection
- Integration of official Local Government Directory (LGD) data
- Improved village geolocation
- All-India village dataset integration
- Better free-land identification
- Government-land verification using official datasets
- Improved terrain validation
- Improved hydrological validation
- Higher-resolution elevation-data support
- Improved pond candidate scoring
- Soil-data integration
- Land-cover-based runoff coefficients
- Better map controls
- Automated testing
- API documentation
- Deployment
- Final technical report
- Final project documentation

---

## Technology Stack

### Backend

- Python
- FastAPI
- Uvicorn
- NumPy
- SciPy
- Rasterio
- Shapely
- PyProj
- scikit-image
- HTTPX
- python-dotenv
- python-multipart

### Frontend

- HTML
- CSS
- JavaScript
- Leaflet.js

### External Data Sources

- OpenTopography
- Copernicus DEM
- OpenStreetMap
- Overpass API
- Open-Meteo
- Nominatim
- Government of India Local Government Directory datasets

---

## Current System Workflow

```text
Contour Map / Location Name
        ↓
Terrain Elevation Data
        ↓
DEM Generation
        ↓
Slope Analysis
        ↓
Hydrological Conditioning
        ↓
D8 Flow Direction
        ↓
Flow Accumulation
        ↓
Catchment Delineation
        ↓
Land / Water Exclusion
        ↓
Rainfall Analysis
        ↓
Runoff Estimation
        ↓
Pond Candidate Detection
        ↓
Pond Depth / Capacity Estimation
        ↓
Suitability Ranking
        ↓
Interactive Map Visualization
````

---

## Contour Map Analysis

The system can analyze an uploaded terrain contour file.

Supported formats currently include:

```text
.kml
.kmz
```

The contour file contains elevation information represented using contour lines.

For example:

```text
274 m
275 m
276 m
277 m
```

These elevation values are used to reconstruct a continuous Digital Elevation Model.

---

## Digital Elevation Model Generation

The uploaded contour lines are converted into elevation samples.

The terrain-processing flow is approximately:

```text
Contour Lines
      ↓
Elevation Values
      ↓
Coordinate Projection
      ↓
Interpolation
      ↓
Regular DEM Grid
```

The generated DEM is then used for terrain and hydrological calculations.

---

## Terrain Slope Analysis

Terrain slope is calculated from the DEM.

Slope is important because very steep locations may not be suitable for pond construction.

The slope information is also used during candidate ranking.

---

## Hydrological Conditioning

Interpolation and DEM generation may produce artificial depressions.

These depressions can incorrectly trap simulated surface runoff.

The system therefore performs DEM depression filling before calculating drainage behavior.

```text
Raw DEM
   ↓
Artificial Depressions
   ↓
Sink Filling
   ↓
Hydrologically Conditioned DEM
```

---

## D8 Flow Direction

The system uses the **D8 Flow Direction Algorithm**.

For each DEM cell, the algorithm examines the eight surrounding cells:

```text
NW    N    NE
  \   |   /
W --- X --- E
  /   |   \
SW    S    SE
```

Water is routed toward the steepest downhill neighbouring cell.

This creates the drainage network used for further hydrological analysis.

---

## Flow Accumulation

Flow accumulation represents the number of upstream terrain cells contributing runoff to a given location.

A high flow-accumulation value indicates that runoff from a larger upstream area passes through that cell.

Flow accumulation does **not** directly represent stored water.

It is used as one of the main indicators when identifying suitable pond locations.

---

## Catchment Delineation

For each pond candidate, the system traces the drainage network upstream.

All cells whose runoff eventually reaches the candidate location are considered part of its catchment.

Catchment area is approximately calculated using:

```text
Catchment Area
=
Number of Catchment Cells
×
Area of Each DEM Cell
```

For example, with a 10 m × 10 m DEM cell:

```text
Cell Area = 100 m²
```

If the catchment contains:

```text
37,861 cells
```

then:

```text
Catchment Area
=
37,861 × 100
=
3,786,100 m²
```

or approximately:

```text
378.61 hectares
```

---

## Pond Candidate Detection

Potential pond locations are identified using terrain and hydrological characteristics.

Factors currently considered include:

* Flow accumulation
* Terrain slope
* Elevation
* Candidate spacing
* Valid terrain availability
* Existing water features
* Roads
* Buildings

The system generates multiple candidate sites and ranks them according to suitability.

---

## Land Suitability Filtering

A hydrologically suitable location may still be unsuitable if a river, road, building, or water body already exists there.

To address this, the system obtains mapped features from OpenStreetMap through the Overpass API.

Currently excluded features include:

* Rivers
* Streams
* Canals
* Drains
* Ditches
* Lakes
* Reservoirs
* Wetlands
* Roads
* Buildings

A safety buffer is also applied around these features.

---

## Important Hydrology Design Decision

Existing rivers are **not removed from the hydrological calculation**.

They remain part of the natural drainage system.

The processing is therefore:

```text
Complete Terrain
      ↓
Flow Direction
      ↓
Flow Accumulation
      ↓
Catchment Analysis
```

After hydrology is calculated:

```text
Candidate Search
      ↓
Apply Land Exclusion Mask
      ↓
Remove Rivers / Roads / Buildings
      ↓
Select Suitable Pond Sites
```

This ensures that natural drainage remains correct while preventing pond recommendations inside existing rivers.

---

## Historical Rainfall Analysis

Historical rainfall data is used to estimate how much runoff may enter a proposed pond catchment.

Rainfall information is retrieved for the analysis area and aggregated into annual rainfall statistics.

---

## Runoff Estimation

Approximate runoff is estimated using:

```text
V = P × A × C
```

where:

```text
V = Estimated Runoff Volume
P = Rainfall
A = Catchment Area
C = Runoff Coefficient
```

The runoff coefficient depends on terrain and land-cover characteristics.

The current implementation allows this value to be configured.

---

## Pond Storage Estimation

For each candidate location, the system estimates:

* Pond footprint
* Pond area
* Recommended depth
* Approximate storage capacity
* Annual runoff
* Runoff-to-storage ratio

These estimates are currently intended for preliminary planning purposes.

---

## Automatic Location Analysis

The system is also being extended to analyze a real-world location without requiring the user to manually provide a contour file.

For example:

```text
IIT Bhilai, Kutelabhata, Chhattisgarh, India
```

The automatic workflow is:

```text
Location Name
      ↓
Geocoding
      ↓
Latitude / Longitude
      ↓
Analysis Bounding Box
      ↓
OpenTopography
      ↓
Copernicus COP30 DEM
      ↓
Automatic Contour Generation
      ↓
Hydrological Analysis
      ↓
Pond Candidate Detection
```

The generated terrain files may include:

```text
source_dem.tif
generated_contours.kml
generated_contours.geojson
```

---

## Original Contour Overlay

The system can overlay the original contour map directly on the real-world map.

Contour lines are displayed together with their elevation values.

Example:

```text
274 m AMSL
275 m AMSL
276 m AMSL
```

AMSL means:

```text
Above Mean Sea Level
```

This helps visually compare the calculated catchment with the original terrain data.

---

## Interactive Map

The frontend uses Leaflet.js.

The map can display:

* OpenStreetMap street map
* Satellite imagery
* Original contour lines
* Generated contour lines
* Contour elevation labels
* Analysis boundary
* Catchment area
* Excluded land
* Best pond candidate
* Additional pond candidates

---

## Map Legend

Current map interpretation:

```text
Brown Lines
→ Original / generated contour lines

Blue Dashed Boundary
→ Contour-map / analysis extent

Light Blue Area
→ Calculated catchment area

Red Area
→ Excluded water / road / building area

Green Marker
→ Top recommended pond candidate

Blue Markers
→ Other possible pond candidates
```

---

## Project Structure

```text
AI-based-Village-Pond-Planning-System/
│
├── backend/
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── contour_routes.py
│   │   └── location_routes.py
│   │
│   ├── hydrology/
│   │   ├── __init__.py
│   │   ├── catchment.py
│   │   ├── flow_accumulation.py
│   │   ├── flow_direction.py
│   │   └── sink_fill.py
│   │
│   ├── pond/
│   │   ├── __init__.py
│   │   ├── candidate.py
│   │   └── metrics.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── response.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── analysis_service.py
│   │   ├── contour_generation_service.py
│   │   ├── geocoding_service.py
│   │   ├── kml_service.py
│   │   ├── land_service.py
│   │   ├── opentopography_service.py
│   │   └── rainfall_service.py
│   │
│   ├── terrain/
│   │   ├── __init__.py
│   │   ├── dem_generator.py
│   │   └── slope.py
│   │
│   ├── __init__.py
│   └── main.py
│
├── frontend/
│   │
│   ├── css/
│   │   └── style.css
│   │
│   ├── js/
│   │   ├── app.js
│   │   └── location.js
│   │
│   └── index.html
│
├── data/
│   ├── cache/
│   └── generated/
│
├── contours_1m.kml
├── requirements.txt
├── .gitignore
└── README.md
```

---

# Running the Project

> ⚠️ The project setup is still evolving.
> These instructions represent the current development setup.

## 1. Clone the Repository

```bash
git clone https://github.com/D4777373/AI-based-Village-Pond-Planning-System.git
```

Move into the project directory:

```bash
cd AI-based-Village-Pond-Planning-System
```

---

## 2. Create a Python Virtual Environment

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

---

## 3. Install Dependencies

```bash
pip install --upgrade pip
```

Then:

```bash
pip install -r requirements.txt
```

---

## 4. Configure Environment Variables

Create a `.env` file:

```bash
nano .env
```

Add:

```text
OPEN_TOPOGRAPHY_API_KEY=YOUR_OPENTOPOGRAPHY_API_KEY
```

Additional API configuration may be added as development continues.

> Never commit `.env` or API keys to GitHub.

---

## 5. Start the Application

Activate the virtual environment if required:

```bash
source .venv/bin/activate
```

Start FastAPI:

```bash
uvicorn backend.main:app --reload
```

The server should start at:

```text
http://127.0.0.1:8000
```

---

## Application URLs

### Main Web Application

```text
http://127.0.0.1:8000
```

### FastAPI Swagger Documentation

```text
http://127.0.0.1:8000/docs
```

### Health Check

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "healthy"
}
```

---

## Manual Contour Analysis

Open:

```text
http://127.0.0.1:8000
```

Select:

```text
Upload Existing Contour Map
```

Upload a KML/KMZ contour file.

Example:

```text
contours_1m.kml
```

Recommended initial values:

```text
DEM Resolution:          10 m
Maximum Candidates:      20
Rainfall History:         5 years
Runoff Coefficient:       0.30
Pond Search Radius:      40 m
Maximum Pond Depth:       3 m
```

Click:

```text
Analyze Contour
```

The application will perform:

```text
Contour Parsing
→ DEM Generation
→ Terrain Analysis
→ Hydrological Analysis
→ Catchment Analysis
→ Land Filtering
→ Rainfall Analysis
→ Pond Candidate Ranking
```

---

## API Endpoint

### Contour Analysis

```text
POST /api/analyzeContour
```

Example:

```bash
curl -X POST \
  -F "file=@contours_1m.kml" \
  -F "resolution_m=10" \
  -F "max_candidates=20" \
  -F "rainfall_years=5" \
  -F "runoff_coefficient=0.30" \
  -F "pond_radius_m=40" \
  -F "max_pond_depth_m=3" \
  http://127.0.0.1:8000/api/analyzeContour
```

---

## Automatic Location Analysis

The automatic location workflow is currently under development.

The intended workflow is:

```text
Location Selection
      ↓
Geocoding
      ↓
OpenTopography DEM
      ↓
Contour Generation
      ↓
Terrain Analysis
      ↓
Catchment Analysis
      ↓
Pond Recommendation
```

---

## Development Validation

Check Python files for syntax errors:

```bash
python3 -m compileall backend
```

Run the backend without auto-reload:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## Important Limitations

This project is currently intended for:

* Academic use
* Demonstration
* Preliminary geospatial planning
* Algorithm development

It should **not currently be used as a final civil-engineering decision system**.

Final pond construction would require additional validation such as:

* Field survey
* High-resolution topographic survey
* Soil testing
* Geotechnical investigation
* Official government land records
* Property ownership verification
* Environmental assessment
* Drainage verification
* Civil-engineering design
* Regulatory approval

---

## Elevation Data Limitation

Copernicus COP30 has approximately 30 m nominal horizontal resolution.

Therefore automatically generated contours from this DEM should be considered suitable for preliminary terrain analysis rather than survey-grade engineering.

The detailed contour map supplied for the assignment may contain significantly finer local elevation information.

---

## Land Availability Limitation

The current OpenStreetMap-based land filter can identify mapped:

* Rivers
* Streams
* Water bodies
* Roads
* Buildings

However:

```text
Feature-clear land
```

does **not automatically mean**:

```text
Government-owned land
```

or:

```text
Legally available land
```

Official cadastral and land-ownership datasets are required for that validation.

---

## Future Improvements

Planned improvements currently include:

* Official India LGD location hierarchy
* State-wise village selection
* All-India village database
* Better village geolocation
* Government-land dataset integration
* Soil information
* Land-cover information
* Dynamic runoff coefficients
* Higher-resolution DEM support
* Improved hydrological algorithms
* Improved pond scoring
* Multiple catchment visualization
* PostgreSQL/PostGIS integration
* Automated tests
* Better API validation
* Cloud deployment
* Final technical documentation

---

## Project Status

```text
Status: 🚧 UNDER ACTIVE DEVELOPMENT
```

The repository is being developed incrementally.

Backend hydrology, geospatial processing, external data integrations, frontend visualization, location services, village selection, and validation are being implemented and improved step by step.

The project should therefore be considered a **work in progress**, not a finished production system.

---

## Academic Context

This project is being developed as part of the:

**AI-Based Village Pond Planning System**

assignment.

The purpose is to explore geospatial terrain analysis, hydrological modelling, external public datasets, web APIs, and interactive map-based decision support.

---

## License

This project is currently intended primarily for academic and educational purposes.

Licensing information may be updated as development progresses.

```
```

