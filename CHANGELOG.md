# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.9] - 2025-10-28

- Auto fleet import 

## [0.2.7] - 2025-10-28

- Fix permissions issue

## [0.2.3] - 2025-10-28

- Version Bump

## [0.2.2] - 2025-10-28

### Changed
- **Pyproject Syntax**: Fixed license syntax

## [0.2.0] - 2025-10-28

### Changed
- **Streamlined Fleet Creation**: Removed doctrine and location fields from fleet creation form
- **Auto Fleet Time**: Fleet time now automatically set to current time when creating a fleet (no longer requires manual input)
- **Smart Corp Share**: Corporation share now automatically calculated based on per-character payout:
  - 10% corp share if per-character payout exceeds 200,000 ISK
  - 0% corp share if per-character payout is 200,000 ISK or less
  - Removed manual corp share percentage input from loot pool creation and approval forms

### Added
- **Battle Report Field**: Added optional battle report URL field to fleet creation (for linking zkillboard, evetools, etc.)

### Removed
- Manual fleet time selection (now auto-set to current time)
- Doctrine field from fleet creation
- Location field from fleet creation
- Corporation share percentage input from loot pool forms (now auto-calculated)

## [0.1.1]

### Added Features
- Fleet management system
- Loot valuation with market pricing
- Payout calculation engine
- Payment tracking
- Comprehensive reporting

## [0.1.0] 

### Added
- Initial project structure
- Basic plugin framework
- Permission system setup
- Database models design
- Implementation plan documentation

### Changed
- Forked from aa-example-plugin
- Renamed to aa-payout

[Unreleased]: https://github.com/guarzo/aa-payout/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/guarzo/aa-payout/releases/tag/v0.1.0
