# ConcurrentWitness2Test 

ConcurrentWitness2Test validates violation witnesses for the ConcurrencySafety category at [SV-COMP](https://sv-comp.sosy-lab.org/).

## Installation

Minimal necessary packages for Ubuntu 22.04 LTS:
* python3

## Contents of the Repository
```
CONTRIBUTORS.md  -- code contributors to the project
LICENSE          -- apache 2.0 license
README.md        -- this README
main.py          -- main python entrypoint
requirements.txt -- python dependencies (included in venv)
start.sh         -- script to start the validation process
svcomp.c         -- test harness
tweaks.py        -- additional source file
witness2ast.py   -- additional source file
```

## Usage
Run `./start.sh <preprocessed-c-file> <witnessfile>` to validate a violation witness. 
