# SkySensAI
**An AI-enabled traffic advisory and sequencing system for nontowered airports**

<img width="313" height="209" alt="SkySensAI-2" src="https://github.com/user-attachments/assets/e43ad80d-805a-4f56-b841-5e5c0a4e4ceb" />

SkySensAI is a prototype decision-support system designed to improve situational awareness, traffic sequencing, and runway safety at nontowered airports.

The system listens to pilot self-announcements on the Common Traffic Advisory Frequency (CTAF), converts the transmissions into structured aircraft information, tracks each aircraft through the airport traffic pattern, detects potential conflicts, and generates advisory messages for pilots.

The initial case study focuses on **San Martin Airport (E16)** in San Martin, California.


---

## Table of Contents

* [Overview](#overview)
* [Problem Statement](#problem-statement)
* [Project Objectives](#project-objectives)
* [System Architecture](#system-architecture)
* [How It Works](#how-it-works)
* [Aircraft State Machine](#aircraft-state-machine)
* [Conflict Detection](#conflict-detection)
* [Technology Stack](#technology-stack)
* [Installation](#installation)
* [Running the Application](#running-the-application)
* [Example Pilot Calls](#example-pilot-calls)
* [Project Structure](#project-structure)
* [Case Study: San Martin Airport](#case-study-san-martin-airport)
* [Current Limitations](#current-limitations)
* [Future Development](#future-development)
* [Safety Disclaimer](#safety-disclaimer)
* [Contributors](#contributors)
* [Acknowledgments](#acknowledgments)

---

## Overview

Nontowered airports do not have air traffic controllers actively directing aircraft. Instead, pilots communicate their positions and intentions over CTAF, visually identify nearby traffic, and sequence themselves into the traffic pattern.

Although this system generally works well, it depends heavily on:

* Clear and accurate radio communication
* Correct position reporting
* Pilot situational awareness
* Visual detection of other aircraft
* Proper traffic-pattern procedures
* Effective self-sequencing

SkySensAI explores how artificial intelligence could provide an additional advisory layer without replacing pilot authority or existing procedures.

The system is intended to function as a digital observer that interprets radio calls, maintains a shared traffic picture, and alerts pilots when it detects potentially unsafe conditions.

---

## Problem Statement

At nontowered airports, pilots must independently determine the location, intentions, and sequencing of nearby aircraft.

This process becomes more difficult when:

* Multiple aircraft transmit in rapid succession
* Radio calls are incomplete or unclear
* Aircraft use similar callsigns
* Pilots enter the pattern from different directions
* Aircraft operate on opposite runways
* A runway remains occupied while another aircraft is approaching
* Pilots lose awareness of aircraft that reported earlier
* Radio congestion prevents timely communication

SkySensAI investigates whether an AI-based advisory system can transform unstructured CTAF transmissions into a continuously updated representation of airport traffic and use that information to identify possible conflicts.

---

## Project Objectives

The primary objectives of SkySensAI are to:

1. Convert pilot radio transmissions into text.
2. Extract aircraft callsigns, positions, runways, and intentions.
3. Track each aircraft using a finite state machine.
4. Display aircraft locations within the airport traffic pattern.
5. Detect runway and traffic-pattern conflicts.
6. Generate clear, nonauthoritative safety advisories.
7. Demonstrate the concept through a browser-based simulation.

---

## System Architecture

SkySensAI uses the following processing pipeline:

```text
Pilot CTAF Transmission
          |
          v
Speech-to-Text Processing
          |
          v
Natural-Language Parser
          |
          v
Structured Aircraft Data
          |
          v
Aircraft State Machine
          |
          v
Traffic and Conflict Analysis
          |
          v
Visual Display and Voice Advisory
```

A pilot transmission such as:

```text
San Martin traffic, Cessna Five Six Tango entering left downwind Runway One Four, San Martin
```

may be converted into structured data similar to:

```json
{
  "callsign": "Cessna 56T",
  "airport": "E16",
  "runway": "14",
  "position": "DOWNWIND",
  "trigger": "report_downwind"
}
```

---

## How It Works

### 1. CTAF Input

The system receives a pilot transmission through either:

* Typed simulation input
* Recorded audio
* Live microphone input
* A future radio or receiver integration

### 2. Speech Recognition

Audio transmissions are converted into text using a speech-to-text model.

### 3. Natural-Language Parsing

The parser identifies important information from the transmission, including:

* Aircraft type
* Aircraft callsign
* Runway
* Traffic-pattern position
* Pilot intention
* Airport name
* State-transition trigger

The parser also normalizes common aviation speech patterns, including spoken numbers and phonetic letters.

Examples include:

```text
"five six tango" -> "56T"
"one four" -> "14"
"three two" -> "32"
"tee" -> "T"
"tango" -> "T"
```

### 4. Aircraft Tracking

Each detected aircraft is assigned an individual state machine. The state changes whenever the aircraft reports a new position or intention.

### 5. Conflict Detection

The system compares aircraft states, runway assignments, and relative pattern positions to identify potentially unsafe combinations.

### 6. Advisory Generation

When a possible conflict is detected, SkySensAI generates a visual or spoken advisory.

Example:

```text
Traffic advisory: Cessna 56T is on final Runway 14 while Diamond 23A is entering the runway.
```

SkySensAI advisories are informational only and do not represent air traffic control instructions.

---

## Aircraft State Machine

SkySensAI models aircraft operations using a finite state machine.

### Arrival States

```text
UNKNOWN
   |
   v
MANEUVERING_TO_ENTER
   |
   v
ENTERING_PATTERN
   |
   v
DOWNWIND
   |
   v
BASE
   |
   v
FINAL
   |
   v
SHORT_FINAL
   |
   v
LANDED_ROLLOUT
   |
   v
CLEAR_OF_RUNWAY
```

### Departure States

```text
TAXIING
   |
   v
HOLDING_SHORT
   |
   v
ENTERING_RUNWAY
   |
   v
DEPARTING
   |
   v
UPWIND
   |
   v
CROSSWIND
   |
   v
DOWNWIND
```

### Supported States

| State                  | Description                                                     |
| ---------------------- | --------------------------------------------------------------- |
| `UNKNOWN`              | Aircraft has been detected, but its position is not yet known   |
| `TAXIING`              | Aircraft is taxiing on the airport surface                      |
| `HOLDING_SHORT`        | Aircraft is waiting before entering the runway                  |
| `ENTERING_RUNWAY`      | Aircraft is entering or lining up on the runway                 |
| `DEPARTING`            | Aircraft is beginning its takeoff roll or departure             |
| `UPWIND`               | Aircraft is climbing along the runway heading                   |
| `CROSSWIND`            | Aircraft is flying the crosswind leg                            |
| `MANEUVERING_TO_ENTER` | Aircraft is approaching the traffic pattern                     |
| `ENTERING_PATTERN`     | Aircraft is entering the pattern, commonly on a 45-degree entry |
| `DOWNWIND`             | Aircraft is flying parallel to the runway                       |
| `BASE`                 | Aircraft is flying perpendicular to the runway before final     |
| `FINAL`                | Aircraft is aligned with the runway for landing                 |
| `SHORT_FINAL`          | Aircraft is close to the runway threshold                       |
| `LANDED_ROLLOUT`       | Aircraft has landed and remains on the runway                   |
| `CLEAR_OF_RUNWAY`      | Aircraft has exited the runway                                  |

---

## Conflict Detection

SkySensAI evaluates several types of potential conflicts.

### Runway Occupancy Conflict

Detected when an arriving aircraft is on final or short final while another aircraft is:

* Entering the runway
* Departing
* Conducting a takeoff roll
* Completing its landing rollout

### Opposite-Direction Conflict

Detected when two aircraft are operating on opposite ends of the same runway.

Example:

```text
Aircraft A: Final Runway 14
Aircraft B: Final Runway 32
```

### Pattern Sequencing Conflict

Detected when aircraft are positioned too closely within the same traffic-pattern sequence.

Example:

```text
Aircraft A: Short final
Aircraft B: Turning base
```

### Runway Entry Conflict

Detected when an aircraft begins entering the runway while another aircraft is approaching on final.

### Duplicate or Ambiguous Callsign

Detected when the parser cannot confidently distinguish between aircraft with similar callsigns.

### Incomplete Position Report

Detected when a transmission does not contain enough information to determine the aircraft’s current state.

---

## Technology Stack

The current prototype may use the following technologies:

* **Python** — system logic and backend processing
* **Flask** — local web application and API
* **HTML** — browser interface
* **CSS** — interface styling
* **JavaScript** — aircraft animation and interactive visualization
* **JSON** — structured aircraft data
* **Speech-to-Text** — conversion of CTAF audio into text
* **Text-to-Speech** — spoken traffic advisories
* **Finite State Machines** — aircraft state tracking

---

## Installation

### Prerequisites

Before running SkySensAI, install:

* Python 3.10 or newer
* `pip`
* Git
* A modern web browser

### Clone the Repository

```bash
git clone https://github.com/[YOUR-USERNAME]/SkySensAI.git
cd SkySensAI
```

### Create a Virtual Environment

#### macOS or Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

#### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Running the Application

Start the Flask server:

```bash
python app.py
```

Depending on the repository structure, the command may instead be:

```bash
python3 app.py
```

Open the following address in a browser:

```text
http://127.0.0.1:5000
```

Enter a simulated CTAF transmission into the input field and submit it to update the traffic display.

---

## Example Pilot Calls

### Pattern Entry

```text
San Martin traffic, Cessna Five Six Tango, five miles northwest, entering the left downwind Runway One Four, San Martin.
```

### Downwind

```text
San Martin traffic, Cessna Five Six Tango, left downwind Runway One Four, San Martin.
```

### Base

```text
San Martin traffic, Cessna Five Six Tango, turning left base Runway One Four, San Martin.
```

### Final

```text
San Martin traffic, Cessna Five Six Tango, final Runway One Four, San Martin.
```

### Holding Short

```text
San Martin traffic, Diamond Two Three Alpha, holding short Runway One Four, San Martin.
```

### Entering the Runway

```text
San Martin traffic, Diamond Two Three Alpha, entering Runway One Four for departure, San Martin.
```

### Clear of the Runway

```text
San Martin traffic, Cessna Five Six Tango, clear of Runway One Four, San Martin.
```

---

## Project Structure

A typical SkySensAI repository may use the following structure:

```text
SkySensAI/
|
├── app.py
├── requirements.txt
├── README.md
|
├── skysensai/
│   ├── __init__.py
│   ├── parser.py
│   ├── state_machine.py
│   ├── conflict_detection.py
│   ├── advisory_generator.py
│   └── aircraft.py
|
├── templates/
│   └── index.html
|
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── simulation.js
│   └── images/
|
├── tests/
│   ├── test_parser.py
│   ├── test_state_machine.py
│   └── test_conflicts.py
|
└── docs/
    ├── architecture/
    ├── diagrams/
    └── research/
```

The exact structure may differ depending on the current implementation.

---

## Case Study: San Martin Airport

SkySensAI is initially modeled around **San Martin Airport**, FAA identifier **E16**, a public-use nontowered airport in Santa Clara County, California.

The airport provides a useful case study because it represents the type of general aviation environment in which pilots depend on self-announced radio communication and visual separation.

### Airport Characteristics

| Characteristic    | Information                  |
| ----------------- | ---------------------------- |
| Airport           | San Martin Airport           |
| FAA Identifier    | E16                          |
| Airport Type      | Public, nontowered           |
| Primary Runway    | Runway 14/32                 |
| Runway Length     | Approximately 3,095 feet     |
| Runway Width      | Approximately 75 feet        |
| CTAF              | 122.3 MHz                    |
| Runway 14 Pattern | Left traffic                 |
| Runway 32 Pattern | Right traffic                |
| Pattern Altitude  | Approximately 1,300 feet MSL |

The browser simulation represents the runway, taxiways, traffic-pattern legs, aircraft positions, and sequencing advisories associated with this environment.

---

## Current Limitations

SkySensAI is currently a research prototype and simulation.

Known limitations include:

* Speech-recognition errors caused by radio noise
* Callsign misinterpretation
* Incomplete or nonstandard pilot transmissions
* Dependence on pilots making position reports
* Limited aircraft-position accuracy without surveillance data
* No direct control over aircraft
* Simplified aircraft movement and timing
* Limited handling of pattern deviations
* Limited weather and wind integration
* Limited support for simultaneous transmissions
* No certification for operational aviation use

The prototype should not be considered a replacement for pilot judgment, visual scanning, FAA procedures, or air traffic control services.

---

## Future Development

Potential future improvements include:

* Live CTAF audio processing
* ADS-B aircraft-position integration
* Improved aviation-specific speech recognition
* Confidence scores for parsed transmissions
* Aircraft trajectory prediction
* Estimated time-to-runway calculations
* Wake-turbulence-aware sequencing
* Weather and wind integration
* Go-around detection
* Pattern-entry recommendation generation
* Support for multiple airports and runway layouts
* Mobile and tablet interfaces
* Conflict severity classification
* Historical traffic playback
* Pilot workload evaluation
* Human-factors testing
* Machine-learning-based intent recognition
* Integration with airport cameras or acoustic sensors
* Testing with recorded real-world radio traffic

A future version could combine CTAF transmissions with ADS-B position data to improve state estimation and reduce dependence on verbal reports alone.

---

## Safety Disclaimer

> [!WARNING]
> SkySensAI is an experimental educational and research prototype. It is not certified by the Federal Aviation Administration or any other aviation authority.

The software must not be used for operational flight guidance, aircraft separation, navigation, or collision avoidance.

Pilots remain responsible for:

* Seeing and avoiding other aircraft
* Following applicable FAA regulations
* Using approved navigation and communication equipment
* Monitoring the appropriate radio frequency
* Making proper traffic advisories
* Maintaining safe aircraft separation
* Exercising pilot-in-command authority

SkySensAI advisories are nonauthoritative and must never be interpreted as air traffic control instructions or clearances.

---

## Contributors

SkySensAI was developed as part of the **NASA Ames Aviation Systems Division Concept Design Experience for High School Students**.

### Project Team

* Rishi Kutty
* [Team Member Name]
* [Team Member Name]
* [Team Member Name]

### Mentors

* Vishwanath “Vishwa” Bulusu — NASA Ames Research Center
* Steven D. Beard — NASA Ames Research Center

---

## Acknowledgments

The project team would like to thank:

* NASA Ames Research Center
* NASA Aviation Systems Division
* SkySensAI project mentors
* San Martin Airport and the general aviation community
* Researchers working in artificial intelligence, air traffic management, aviation safety, and human-machine teaming

---

## License

This project is intended for educational and research purposes.

Add the selected license to the repository in a separate `LICENSE` file.

Common options include:

* MIT License
* Apache License 2.0
* GNU General Public License
* All Rights Reserved

---

## Repository Status

```text
Project Status: Research Prototype
Operational Use: Not Approved
Primary Environment: Simulation
Case Study Airport: San Martin Airport (E16)
```
