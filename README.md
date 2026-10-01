# MATSim Urban Policy Assessment Framework

**Author:** Michael Andreas\
**Master's Thesis:** An Agent-Based Approach to Urban Policy Assessment: Processing Disaggregated MATSim Outputs for Transport Policy Evaluation\
**Institution:** Technical University of Munich (TUM)

## Overview
This repository contains the analytical framework developed to bridge the gap between highly disaggregated Multi-Agent Transport Simulation (MATSim) outputs and the macro-level insights required for evidence-based policymaking.

Built around Object-Oriented Programming (OOP) principles, this Python and Java-based toolset processes raw MATSim event logs and extension outputs, systematically aggregating them across **spatial** (multi-resolution grids and administrative boundaries) and **socio-demographic** (age and gender) dimensions. To enable direct comparability, all evaluated indicators are monetized and unified into a single net welfare metric.

The framework was applied and validated using the *Altstadt für alle* urban transport policy in Munich as the primary case study.

## Key Indicators
* Accessibility
* Accidents (Road-based)
* Emissions (Road-based)
* Noise (Road-based)

## Requirements
* Windows users must install **gdal and rasterio wheel** locally