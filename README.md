[![Build-Test-Deploy](https://github.com/ftsrg/ConcurrentWitness2Test/actions/workflows/linux-build-test-deploy.yml/badge.svg)](https://github.com/ftsrg/ConcurrentWitness2Test/actions/workflows/linux-build-test-deploy.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=ftsrg_ConcurrentWitness2Test&metric=coverage)](https://sonarcloud.io/summary/new_code?id=ftsrg_ConcurrentWitness2Test)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=ftsrg_ConcurrentWitness2Test&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=ftsrg_ConcurrentWitness2Test)


# ConcurrentWitness2Test 

ConcurrentWitness2Test validates violation witnesses for the ConcurrencySafety category at [SV-COMP](https://sv-comp.sosy-lab.org/).

## Installation

Minimal necessary packages for Ubuntu 24.04 LTS:
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
Run `./start.sh <preprocessed-c-file> --witness <witnessfile> --mode <strict/normal/permissive>` to validate a violation witness. 

## Publications
For more information on how the validation works, check out our SV-COMP 2023 [tool paper](https://leventebajczi.com/publications/tacas24cwt.pdf) and [slides](https://leventebajczi.com/publications/slides/tacas24cwt.pdf).

## Tool Support

[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/bubaak/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/bubaak/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cbmc/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cbmc/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/coveriteam-verifier-algo-selection/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/coveriteam-verifier-algo-selection/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/coveriteam-verifier-parallel-portfolio/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/coveriteam-verifier-parallel-portfolio/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cpa-lockator/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cpa-lockator/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cpachecker/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cpachecker/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cseq/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cseq/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/dartagnan/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/dartagnan/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/deagle/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/deagle/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/divine/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/divine/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/ebf/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/ebf/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/esbmc-incr/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/esbmc-incr/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/esbmc-kind/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/esbmc-kind/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/goblint/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/goblint/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/graves-par/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/graves-par/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/graves/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/graves/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/infer/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/infer/)
[![](https://img.shields.io/badge/lazycseq-Unknown%20(0/0/0)-lightgrey)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/lazycseq/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/lf-checker/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/lf-checker/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/pesco/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/pesco/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/pichecker/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/pichecker/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/symbiotic/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/symbiotic/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/theta/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/theta/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/uautomizer/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/uautomizer/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/ugemcutter/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/ugemcutter/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/utaipan/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/utaipan/)
